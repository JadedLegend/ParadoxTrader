"""Offline optional inquiry contracts. Never import api.app or provider runtime."""
import ast
import json
import sqlite3
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from core.runtime import inquiry
from core.trading.lineage import LineageAccessError, LineageConflict, LineageError, LineageStore


class InquiryReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory(prefix="inquiry-test-"))
        self.db = Path(self.temp) / "nested" / "trade_queue.sqlite3"
        self.store = LineageStore(self.db)
        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex", "urllib.request.urlopen"):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError("network forbidden")))
            self.addCleanup(guard.assert_not_called)

    def run_command(self, command, operation_id="op", agent_id="tempest", phase=0, evidence=None):
        model = mock.Mock(return_value=json.dumps(command))
        result = inquiry.run_inquiry(agent_id, operation_id, db_path=self.db, phase=phase,
                                     model_call=model, evidence=evidence)
        return result, model

    def detail(self, inquiry_id, agent_id="tempest"):
        return self.store.get_inquiry(inquiry_id, viewer_agent_id=agent_id)

    def assert_no_trading(self):
        with sqlite3.connect(self.db) as conn:
            for table in ("trade_queue", "lineage_proposals", "lineage_orders", "lineage_fills", "lineage_positions"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_constructor_and_receipt_reader_are_lazy_without_default_configuration(self):
        with mock.patch("sqlite3.connect", side_effect=AssertionError("DB access forbidden")):
            adapter = inquiry.InquiryReceiptStore(self.db)
            self.assertEqual(adapter.db_path, str(self.db))
            self.assertIsNone(inquiry.get_inquiry_receipt("tempest", "absent", db_path=self.db))
        self.assertFalse(self.db.exists())
        self.db.parent.mkdir()
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE unrelated (id INTEGER)")
        original = self.db.read_bytes()
        self.assertIsNone(inquiry.get_inquiry_receipt("tempest", "absent", db_path=self.db))
        self.assertEqual(self.db.read_bytes(), original)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("unrelated",)])

    def test_receipt_reader_does_not_treat_corrupt_database_as_missing(self):
        self.db.parent.mkdir()
        self.db.write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError):
            inquiry.get_inquiry_receipt("tempest", "op", db_path=self.db)
        self.assertEqual(self.db.read_bytes(), b"not a sqlite database")

    def test_durable_path_is_explicit_and_never_in_memory(self):
        with mock.patch("sqlite3.connect", side_effect=AssertionError("no SQLite on invalid path")):
            for path in (None, "", " ", ":memory:"):
                with self.subTest(path=path), self.assertRaises(LineageError):
                    inquiry.InquiryReceiptStore(path)
                with self.subTest(read_path=path), self.assertRaises(LineageError):
                    inquiry.get_inquiry_receipt("tempest", "op", db_path=path)

    def test_none_is_legitimate_no_source_writes_and_replay_never_calls_model(self):
        result, model = self.run_command({"operation": "none"})
        self.assertEqual(result["status"], "no_change")
        self.assertFalse(result["replayed"])
        model.assert_called_once()
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        receipt = inquiry.get_inquiry_receipt("tempest", "op", db_path=self.db)
        self.assertEqual(receipt["status"], "complete")
        self.assertFalse(receipt["resumable"])
        forbidden = mock.Mock(side_effect=AssertionError("second model forbidden"))
        replay = inquiry.run_inquiry("tempest", "op", db_path=self.db, model_call=forbidden)
        self.assertEqual({k: v for k, v in replay.items() if k != "replayed"},
                         {k: v for k, v in result.items() if k != "replayed"})
        self.assertTrue(replay["replayed"])
        forbidden.assert_not_called()
        with sqlite3.connect(self.db) as conn:
            for table in ("lineage_inquiries", "lineage_entries", "lineage_reviews", "lineage_events", "lineage_operations"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assert_no_trading()

    def test_start_records_distinct_accounts_source_agent_phase_and_private_visibility(self):
        result, model = self.run_command({"operation": "start", "title": "A question",
                                          "observation": "A supplied quote moved.", "interpretation": "It might mean nothing."}, phase=3)
        self.assertEqual(result["status"], "applied")
        detail = self.detail(result["inquiry_id"])
        self.assertEqual((detail["inquiry"]["phase"], detail["inquiry"]["visibility"]), (3, "owner"))
        self.assertEqual({entry["kind"] for entry in detail["entries"]}, {"observation", "interpretation"})
        self.assertEqual({entry["source"] for entry in detail["entries"]}, {"agent"})
        self.assertEqual(len(result["entry_ids"]), 2)
        self.assert_no_trading()
        model.assert_called_once()

    def test_optional_append_pause_abandon_revisit_and_later_review(self):
        result, _ = self.run_command({"operation": "start", "title": "A question"})
        iid = result["inquiry_id"]
        commands = [
            {"operation": "append", "inquiry_id": iid, "kind": "observation", "content": "Explicit account"},
            {"operation": "append", "inquiry_id": iid, "kind": "interpretation", "content": "Tentative view"},
            {"operation": "state", "inquiry_id": iid, "state": "paused", "reason": "Leave it alone"},
            {"operation": "state", "inquiry_id": iid, "state": "abandoned"},
            {"operation": "state", "inquiry_id": iid, "state": "open", "reason": "Revisit voluntarily"},
            {"operation": "review", "inquiry_id": iid, "content": "A later explicit account"},
        ]
        for index, command in enumerate(commands):
            result, _ = self.run_command(command, operation_id=f"step-{index}")
            self.assertEqual(result["status"], "applied")
        detail = self.detail(iid)
        self.assertEqual(detail["inquiry"]["state"], "open")
        self.assertEqual(len(detail["entries"]), 2)
        self.assertEqual(len(detail["reviews"]), 1)
        self.assertEqual(detail["reviews"][0]["proposal_id"], None)
        self.assertIn("inquiry_revisited", [event["kind"] for event in detail["events"]])
        self.assert_no_trading()

    def test_all_seven_same_operation_strings_are_independent_and_private(self):
        ids = []
        for agent_id in inquiry.AGENT_IDS:
            result, _ = self.run_command({"operation": "start", "title": f"Private {agent_id}"},
                                         agent_id=agent_id, operation_id="same-operation")
            ids.append(result["inquiry_id"])
            receipt = inquiry.get_inquiry_receipt(agent_id, "same-operation", db_path=self.db)
            self.assertEqual(receipt["agent_id"], agent_id)
        self.assertEqual(len(set(ids)), 7)
        for owner, iid in zip(inquiry.AGENT_IDS, ids):
            for viewer in inquiry.AGENT_IDS:
                if viewer == owner:
                    self.assertEqual(self.detail(iid, viewer)["inquiry"]["visibility"], "owner")
                else:
                    with self.assertRaises(LineageAccessError):
                        self.store.get_inquiry(iid, viewer_agent_id=viewer, phase=3)
        self.assert_no_trading()

    def test_owner_and_phase_validation_fail_before_database_or_model(self):
        model = mock.Mock()
        for owner in ("unknown", "", None, [], "Tempest"):
            with self.subTest(owner=owner), self.assertRaises(LineageError):
                inquiry.run_inquiry(owner, "op", db_path=self.db, model_call=model)
        for phase in (None, True, False, 1.0, "0", -1, 4):
            with self.subTest(phase=phase), self.assertRaises(LineageError):
                inquiry.run_inquiry("tempest", "op", db_path=self.db, phase=phase, model_call=model)
        for operation in (None, "", " ", "x" * 201):
            with self.subTest(operation=operation), self.assertRaises(LineageError):
                inquiry.run_inquiry("tempest", operation, db_path=self.db, model_call=model)
        model.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_phase_reuse_conflicts_but_refreshed_observation_timestamps_do_not(self):
        result, _ = self.run_command({"operation": "start", "title": "Same choice"}, phase=1,
                                     evidence={"market_data": {"status": "ok", "price": 10, "observed_at": "old"}})
        model = mock.Mock(side_effect=AssertionError("no replay model"))
        replay = inquiry.run_inquiry("tempest", "op", db_path=self.db, phase=1, model_call=model,
                                     evidence={"market_data": {"status": "ok", "price": 11, "observed_at": "new"}})
        self.assertEqual(replay["inquiry_id"], result["inquiry_id"])
        with self.assertRaises(LineageConflict):
            inquiry.run_inquiry("tempest", "op", db_path=self.db, phase=2, model_call=model)
        model.assert_not_called()
        # A changed owner is a new scoped operation, never access to the old one.
        self.assertIsNone(inquiry.get_inquiry_receipt("siren", "op", db_path=self.db))

    def test_strict_json_rejects_duplicate_keys_fences_unknown_fields_and_bad_shapes(self):
        iid = str(uuid.uuid4())
        invalid = [
            '```json\n{"operation":"none"}\n```', 'prefix {"operation":"none"}',
            '{"operation":"none","operation":"start","title":"sneaked"}',
            '{"operation":"none","value":NaN}', '[]', 'null', '"none"', '{}',
            '{"operation":"none"} {"operation":"start","title":"hidden"}',
            json.dumps({"operation": "none", "source": "operator"}),
            json.dumps({"operation": "start", "title": "Q", "owner": "siren"}),
            json.dumps({"operation": "start", "title": "Q", "phase": 3}),
            json.dumps({"operation": "start", "title": "Q", "visibility": "community"}),
            json.dumps({"operation": "start", "title": "Q", "operator": True}),
            json.dumps({"operation": "prepare_order", "inquiry_id": iid}),
            json.dumps({"operation": "proposal", "title": "Trade"}),
            json.dumps({"operation": "start", "title": ""}),
            json.dumps({"operation": "start", "title": "x" * 201}),
            json.dumps({"operation": "start", "title": "\ud800"}),
            json.dumps({"operation": "start", "title": "Q", "observation": " "}),
            json.dumps({"operation": "start", "title": "Q", "interpretation": "x" * 2001}),
            json.dumps({"operation": "start", "title": {"journal": "private"}}),
            json.dumps({"operation": "append", "inquiry_id": iid.upper(), "kind": "observation", "content": "A"}),
            json.dumps({"operation": "append", "inquiry_id": iid, "kind": "journal", "content": "A"}),
            json.dumps({"operation": "append", "inquiry_id": iid, "kind": "observation", "content": "x" * 2001}),
            json.dumps({"operation": "state", "inquiry_id": iid, "state": "done"}),
            json.dumps({"operation": "state", "inquiry_id": iid, "state": "open", "reason": ""}),
            json.dumps({"operation": "state", "inquiry_id": iid, "state": "open", "reason": "x" * 1001}),
            json.dumps({"operation": "review", "inquiry_id": iid, "content": " "}),
            ' ' * (inquiry.MAX_RESPONSE_CHARS + 1), 123, None,
        ]
        for index, raw in enumerate(invalid):
            with self.subTest(index=index):
                result = inquiry.run_inquiry("tempest", f"invalid-{index}", db_path=self.db,
                                             model_call=mock.Mock(return_value=raw))
                self.assertEqual(result["status"], "invalid")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_commands").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_inquiries").fetchone()[0], 0)
        self.assert_no_trading()

    def test_cross_owner_target_even_community_visible_is_rejected_before_command_commit(self):
        foreign = self.store.create_inquiry("siren", "Not yours", phase=1, visibility="community", operation_key="foreign")
        for index, command in enumerate((
            {"operation": "append", "inquiry_id": foreign, "kind": "observation", "content": "No"},
            {"operation": "state", "inquiry_id": foreign, "state": "paused"},
            {"operation": "review", "inquiry_id": foreign, "content": "No"},
            {"operation": "review", "inquiry_id": str(uuid.uuid4()), "content": "Absent"},
        )):
            result, _ = self.run_command(command, operation_id=f"foreign-{index}", phase=3)
            self.assertEqual(result["status"], "invalid")
        detail = self.detail(foreign, "siren")
        self.assertEqual(detail["entries"], [])
        self.assertEqual(detail["reviews"], [])
        self.assertEqual(detail["inquiry"]["state"], "open")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_commands").fetchone()[0], 0)

    def test_command_commits_before_source_and_sqlite_failure_resumes_partial_sequence_once(self):
        # Initialize receipt schema with a legitimate no-op, then inject a real SQLite failure.
        self.run_command({"operation": "none"}, operation_id="initialize")
        with sqlite3.connect(self.db) as conn:
            conn.execute("""CREATE TRIGGER proof_before_inquiry BEFORE INSERT ON lineage_inquiries
                WHEN NOT EXISTS (SELECT 1 FROM inquiry_commands WHERE agent_id=NEW.agent_id AND operation_id='recover')
                BEGIN SELECT RAISE(ABORT,'command must commit first'); END""")
            conn.execute("""CREATE TRIGGER fail_interpretation BEFORE INSERT ON lineage_entries
                WHEN NEW.kind='interpretation' BEGIN SELECT RAISE(ABORT,'injected SQLite fault'); END""")
        command = {"operation": "start", "title": "Recoverable", "observation": "First account", "interpretation": "Same interpretation"}
        failed, model = self.run_command(command, operation_id="recover")
        self.assertEqual(failed["status"], "unavailable")
        self.assertTrue(failed["resumable"])
        with sqlite3.connect(self.db) as conn:
            iid = conn.execute("SELECT inquiry_id FROM lineage_inquiries").fetchone()[0]
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_entries").fetchone()[0], 1)
            self.assertEqual(json.loads(conn.execute("SELECT command FROM inquiry_commands WHERE operation_id='recover'").fetchone()[0]), command)
            conn.execute("DROP TRIGGER fail_interpretation")
        forbidden = mock.Mock(side_effect=AssertionError("resumption cannot reinterpret"))
        recovered = inquiry.run_inquiry("tempest", "recover", db_path=self.db, model_call=forbidden)
        self.assertEqual(recovered["status"], "applied")
        self.assertTrue(recovered["replayed"])
        self.assertEqual(recovered["inquiry_id"], iid)
        detail = self.detail(iid)
        self.assertEqual(len(detail["entries"]), 2)
        self.assertEqual(len(detail["events"]), 3)
        self.assertEqual({entry["content"] for entry in detail["entries"]}, {"First account", "Same interpretation"})
        replay = inquiry.run_inquiry("tempest", "recover", db_path=self.db, model_call=forbidden)
        self.assertEqual(recovered, replay)
        model.assert_called_once()
        forbidden.assert_not_called()
        self.assert_no_trading()

    def test_sqlite_failure_after_all_source_writes_replays_stable_ids(self):
        self.run_command({"operation": "none"}, operation_id="initialize")
        with sqlite3.connect(self.db) as conn:
            conn.execute("""CREATE TRIGGER fail_result BEFORE INSERT ON inquiry_results
                WHEN NEW.operation_id='finish-fault' BEGIN SELECT RAISE(ABORT,'injected finish fault'); END""")
        failed, _ = self.run_command({"operation": "start", "title": "Already committed", "observation": "One account"},
                                     operation_id="finish-fault")
        self.assertEqual(failed["status"], "unavailable")
        with sqlite3.connect(self.db) as conn:
            iid = conn.execute("SELECT inquiry_id FROM lineage_inquiries").fetchone()[0]
            eid = conn.execute("SELECT entry_id FROM lineage_entries").fetchone()[0]
            conn.execute("DROP TRIGGER fail_result")
        forbidden = mock.Mock(side_effect=AssertionError("no model retry"))
        result = inquiry.run_inquiry("tempest", "finish-fault", db_path=self.db, model_call=forbidden)
        self.assertEqual((result["inquiry_id"], result["entry_ids"]), (iid, [eid]))
        self.assertEqual(len(self.detail(iid)["events"]), 2)
        forbidden.assert_not_called()

    def test_failure_before_source_application_resumes_committed_payload(self):
        adapter = inquiry.InquiryReceiptStore(self.db)
        command = {"operation": "start", "title": "Committed plan"}
        model = mock.Mock(return_value=json.dumps(command))
        with mock.patch.object(adapter, "_apply", side_effect=sqlite3.OperationalError("secret raw error")):
            failed = adapter.run("tempest", "plan-only", model_call=model)
        self.assertEqual(failed["failure_code"], "application_unavailable")
        forbidden = mock.Mock(side_effect=AssertionError("no reinterpretation"))
        result = inquiry.run_inquiry("tempest", "plan-only", db_path=self.db, model_call=forbidden)
        self.assertEqual(result["status"], "applied")
        forbidden.assert_not_called()
        self.assertEqual(self.detail(result["inquiry_id"])["inquiry"]["title"], command["title"])

    def test_concurrent_same_receipt_has_one_model_choice_and_one_source_sequence(self):
        entered, release = threading.Event(), threading.Event()
        def generate(messages):
            entered.set()
            if not release.wait(10):
                raise AssertionError("test release timeout")
            return '{"operation":"start","title":"Concurrent question","observation":"Single account"}'
        model = mock.Mock(side_effect=generate)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(inquiry.run_inquiry, "tempest", "concurrent", db_path=self.db, model_call=model)
            self.assertTrue(entered.wait(10))
            second = pool.submit(inquiry.run_inquiry, "tempest", "concurrent", db_path=self.db, model_call=model)
            try:
                pending = second.result(timeout=10)
                self.assertEqual(pending["status"], "in_progress")
                self.assertTrue(pending["replayed"])
            finally:
                release.set()
            done = first.result(timeout=10)
        self.assertEqual(done["status"], "applied")
        model.assert_called_once()
        self.assertEqual(len(self.detail(done["inquiry_id"])["entries"]), 1)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT attempts FROM inquiry_operations WHERE operation_id='concurrent'").fetchone()[0], 1)

    def test_expired_claim_can_resume_committed_plan_without_model(self):
        now = [1000.0]
        adapter = inquiry.InquiryReceiptStore(self.db, clock=lambda: now[0], lease_seconds=10)
        token, _, _ = adapter._claim("tempest", "crashed", 0)
        command = {"operation": "start", "title": "Persisted before death"}
        self.assertTrue(adapter._persist_command("tempest", "crashed", token, command))
        forbidden = mock.Mock(side_effect=AssertionError("no regenerated payload"))
        self.assertEqual(adapter.run("tempest", "crashed", model_call=forbidden)["status"], "in_progress")
        now[0] += 11
        result = adapter.run("tempest", "crashed", model_call=forbidden)
        self.assertEqual(result["status"], "applied")
        self.assertTrue(result["replayed"])
        forbidden.assert_not_called()

    def test_concurrent_all_seven_same_operation_string_stays_owner_scoped(self):
        def run_owner(agent_id):
            return self.run_command({"operation": "start", "title": f"Owned by {agent_id}"},
                                    operation_id="shared-operation", agent_id=agent_id)[0]
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(run_owner, inquiry.AGENT_IDS))
        self.assertEqual({result["status"] for result in results}, {"applied"})
        self.assertEqual(len({result["inquiry_id"] for result in results}), 7)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_commands WHERE operation_id='shared-operation'").fetchone()[0], 7)
        self.assert_no_trading()

    def test_expired_generation_is_fenced_and_external_billing_is_not_exactly_once(self):
        now = [1000.0]
        adapter = inquiry.InquiryReceiptStore(self.db, clock=lambda: now[0], lease_seconds=10)
        old_token, _, _ = adapter._claim("tempest", "generation-death", 0)
        now[0] += 11
        new_token, _, command = adapter._claim("tempest", "generation-death", 0)
        self.assertIsNone(command)
        self.assertNotEqual(old_token, new_token)
        self.assertFalse(adapter._persist_command("tempest", "generation-death", old_token,
                                                 {"operation": "start", "title": "Stale choice"}))
        self.assertTrue(adapter._persist_command("tempest", "generation-death", new_token, {"operation": "none"}))
        adapter._release("tempest", "generation-death", new_token, "test_process_exit")
        model = mock.Mock(side_effect=AssertionError("no extra model"))
        result = adapter.run("tempest", "generation-death", model_call=model)
        self.assertEqual(result["status"], "no_change")
        model.assert_not_called()

    def test_provider_failure_is_safe_terminal_receipt_no_raw_response_or_error(self):
        secret = "provider-key-SECRET private raw error"
        model = mock.Mock(side_effect=RuntimeError(secret))
        result = inquiry.run_inquiry("tempest", "failed-model", db_path=self.db, model_call=model)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["resumable"])
        replay = inquiry.run_inquiry("tempest", "failed-model", db_path=self.db, model_call=model)
        self.assertTrue(replay["replayed"])
        model.assert_called_once()
        with sqlite3.connect(self.db) as conn:
            dump = "\n".join(conn.iterdump())
        self.assertNotIn(secret, dump)
        self.assertNotIn(secret, json.dumps(result))
        self.assert_no_trading()

    def test_invalid_response_replays_without_storing_raw_private_content(self):
        raw = 'Private hidden reasoning SECRET followed by {"operation":"none"}'
        model = mock.Mock(return_value=raw)
        result = inquiry.run_inquiry("tempest", "invalid", db_path=self.db, model_call=model)
        self.assertEqual(result["status"], "invalid")
        replay = inquiry.run_inquiry("tempest", "invalid", db_path=self.db, model_call=model)
        self.assertTrue(replay["replayed"])
        model.assert_called_once()
        with sqlite3.connect(self.db) as conn:
            self.assertNotIn("SECRET", "\n".join(conn.iterdump()))

    def test_command_result_and_identity_are_sqlite_immutable(self):
        self.run_command({"operation": "none"})
        with sqlite3.connect(self.db) as conn:
            statements = [
                "UPDATE inquiry_commands SET command='{}'", "DELETE FROM inquiry_commands",
                "UPDATE inquiry_results SET result='{}'", "DELETE FROM inquiry_results",
                "UPDATE inquiry_operations SET phase=1", "UPDATE inquiry_operations SET agent_id='siren'",
                "UPDATE inquiry_operations SET operation_id='different'", "UPDATE inquiry_operations SET fingerprint='different'",
                "DELETE FROM inquiry_operations",
                "INSERT OR REPLACE INTO inquiry_commands VALUES ('tempest','op','{}')",
                "INSERT OR REPLACE INTO inquiry_results VALUES ('tempest','op','{}')",
                "INSERT OR REPLACE INTO inquiry_operations (agent_id,operation_id,phase,fingerprint,status) VALUES ('tempest','op',0,'new','generating')",
            ]
            for statement in statements:
                with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(statement)

    def test_prompt_owned_recent_bounded_history_quoted_data_and_evidence_allowlist(self):
        for number in range(7):
            iid = self.store.create_inquiry("tempest", f"Owned-{number}", operation_key=f"owned-{number}")
            for entry in range(9):
                self.store.add_entry(iid, "tempest", "observation", f"Recent-{entry}" + "x" * 800,
                                     operation_key=f"entry-{number}-{entry}")
        foreign = self.store.create_inquiry("siren", "PEER_SECRET", phase=2, visibility="community", operation_key="peer")
        self.store.add_entry(foreign, "siren", "interpretation", "PEER_INTERPRETATION", operation_key="peer-entry")
        evidence = {
            "market_data": {"status": "ok", "price": 12, "symbol": "DEMO", "timestamp": "volatile", "messages": ["PRIVATE_MESSAGE"]},
            "own_positions": {"status": "ok", "positions": [{"symbol": "DEMO", "qty": 1, "journal": "PRIVATE_JOURNAL"}]},
            "indicators": [{"name": "rsi", "value": 55, "memory": "PRIVATE_MEMORY"}],
            "stage_invitation": "You may leave this alone.",
            "peer_positions": {"siren": "PEER_HOLDINGS"}, "messages": "PRIVATE_MESSAGE",
            "journal": "PRIVATE_JOURNAL", "innermost": "PRIVATE_INNERMOST", "memory": "PRIVATE_MEMORY",
        }
        _, model = self.run_command({"operation": "none"}, phase=3, evidence=evidence)
        messages = model.call_args.args[0]
        self.assertTrue(all(message["role"] == "user" for message in messages))
        prompt = json.dumps(messages)
        for secret in ("PEER_SECRET", "PEER_INTERPRETATION", "PEER_HOLDINGS", "PRIVATE_MESSAGE", "PRIVATE_JOURNAL", "PRIVATE_INNERMOST", "PRIVATE_MEMORY", "volatile"):
            self.assertNotIn(secret, prompt)
        history_json = messages[1]["content"].split("\n", 1)[1]
        self.assertLessEqual(len(history_json), inquiry.MAX_HISTORY_CHARS)
        history = json.loads(history_json)
        self.assertEqual(len(history["inquiries"]), 5)
        self.assertEqual({row["title"] for row in history["inquiries"]}, {f"Owned-{n}" for n in range(2, 7)})
        self.assertLessEqual(len(history["details"]), 2)
        for detail in history["details"]:
            self.assertLessEqual(len(detail["entries"]), 5)
            for entry in detail["entries"]:
                self.assertNotIn(entry["content"].split("x")[0], [f"Recent-{n}" for n in range(4)])
        selected = json.loads(messages[2]["content"].split("\n", 1)[1])
        self.assertEqual(selected["market_data"]["price"], 12)
        self.assertEqual(selected["own_positions"]["positions"][0], {"qty": 1, "symbol": "DEMO"})
        self.assertIn("optional", messages[0]["content"])
        self.assertIn('{"operation":"none"}', messages[0]["content"])
        with sqlite3.connect(self.db) as conn:
            dump = "\n".join(conn.iterdump())
        self.assertNotIn("PRIVATE_MESSAGE", dump)
        self.assertNotIn("You may leave this alone.", dump)

    def test_history_and_evidence_bounds_hold_for_large_existing_accounts(self):
        iid = self.store.create_inquiry("tempest", "Q" * 500, operation_key="large")
        for number in range(6):
            self.store.add_entry(iid, "tempest", "interpretation", "X" * 20000, operation_key=f"large-{number}")
            self.store.add_review(iid, "tempest", "R" * 20000, operation_key=f"review-{number}")
        _, model = self.run_command({"operation": "none"}, evidence={
            "market_data": [{key: "x" * 10000 for key in inquiry._EVIDENCE_FIELDS}] * 100,
            "own_positions": [{"symbol": "D" * 1000, "qty": 1}] * 100,
            "stage_invitation": "I" * 10000,
        })
        messages = model.call_args.args[0]
        self.assertLessEqual(len(messages[1]["content"].split("\n", 1)[1]), inquiry.MAX_HISTORY_CHARS)
        selected = messages[2]["content"].split("\n", 1)[1]
        self.assertLessEqual(len(selected), inquiry.MAX_EVIDENCE_CHARS)
        json.loads(selected)

    def test_modules_have_no_provider_broker_journal_or_config_imports(self):
        source = Path(inquiry.__file__).read_text()
        tree = ast.parse(source)
        imports = []
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
        for name in imports:
            self.assertFalse(any(part in name for part in ("api.app", "alpaca", "broker", "memory", "agent_loop", "config", "llm", "hrv")), name)
        for forbidden in ("prepare_order", "create_proposal", "submit_order", "enqueue", "store_episode", "write_journal", "perform"):
            self.assertNotIn(forbidden, calls)


if __name__ == "__main__":
    unittest.main()
