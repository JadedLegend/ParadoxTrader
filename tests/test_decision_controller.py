"""Decision continuity integration: actual private stores and injected HTTP only."""
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.memory.engine import ThresholdMemory
from core.runtime.rehearsal.continuity import (
    MAX_CHARS, MAX_REFS, clip_continuity, owner_continuity, public_coverage,
)
from core.runtime.rehearsal.controller import (
    RehearsalController, _memory_effect, decision_metadata, snapshot_profiles,
)
from core.runtime.rehearsal.provider import (
    AGENT_IDS, CAPABILITIES, OpenRouterTransport, ProviderError, bounded_input,
)
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_rehearsal_provider import Response, manifest

REPO = Path(__file__).resolve().parents[1]


class DecisionControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RehearsalStore(Path(self.temp.name) / "runs")
        raw = manifest()
        raw["limits"]["max_parallelism"] = 1
        self.run_id = self.store.prepare(raw)["run_id"]
        self.path = self.store.run_path(self.run_id)
        self.calls = []
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def controller(self, http, store=None, run_id=None):
        return RehearsalController(
            store or self.store, run_id or self.run_id,
            transport=OpenRouterTransport("scripted-offline", http_post=http),
        )

    def current(self, kwargs):
        owner = kwargs["json"]["model"].split("/", 1)[1]
        return next(j for j in self.store.list_jobs(self.run_id)
                    if j["agent_id"] == owner and j["status"] == "running")

    @staticmethod
    def text(kwargs):
        return "\n".join(m["content"] for m in kwargs["json"]["messages"])

    def test_first_journal_reaches_second_choice_and_activity_without_foreign_or_innermost(self):
        def effect(memory, wake_id, action, output, library_refs=None):
            refs = _memory_effect(memory, wake_id, action, output, library_refs)
            if wake_id.endswith("r1"):
                with sqlite3.connect(memory.db_path) as conn:
                    conn.execute("INSERT INTO journal(content,mood,phase,is_private,created_at) "
                                 "VALUES ('UNLINKED PRIVATE NOTE','neutral','symmetry',1,'now')")
                    # A separate innermost sentinel must never enter continuity.
                    columns = {r[1] for r in conn.execute("PRAGMA table_info(innermost)")}
                    if "content" in columns:
                        conn.execute("INSERT INTO innermost(content,created_at) VALUES ('INNERMOST SECRET','now')")
            return refs

        def http(_url, **kwargs):
            job = self.current(kwargs)
            self.calls.append((deepcopy(job), deepcopy(kwargs)))
            text = self.text(kwargs)
            details = self.store.get_decision_details(self.run_id, job["wake_id"])
            self.assertIsNotNone(details)  # Persisted before the picker dispatch.
            self.assertEqual(details["metadata"]["offered_actions"], list(CAPABILITIES))
            self.assertLessEqual(bounded_input(kwargs["json"]["messages"]), 24000)
            if job["round"] == 2:
                self.assertIn("FIRST-NOTE-" + job["agent_id"], text)
                for foreign in set(AGENT_IDS) - {job["agent_id"]}:
                    self.assertNotIn("FIRST-NOTE-" + foreign, text)
                self.assertNotIn("UNLINKED PRIVATE NOTE", text)
                self.assertNotIn("INNERMOST SECRET", text)
                self.assertIn("You may leave this material alone", text)
                self.assertIn("UNTRUSTED USER DATA", text)
                coverage = details["metadata"]["continuity"]
                self.assertEqual(coverage["status"], "available")
                self.assertEqual(len(coverage["refs"]), 1)
                self.assertEqual(coverage["refs"][0]["wake_id"], job["agent_id"] + "-r1")
                self.assertNotIn("FIRST-NOTE-", json.dumps(coverage))
            content = ('{"action":"journal"}' if "REHEARSAL CHOICE" in text else
                       ("FIRST-NOTE-" if job["round"] == 1 else "SECOND-NOTE-") + job["agent_id"])
            return Response(content=content, model=kwargs["json"]["model"])

        with patch("core.runtime.rehearsal.controller._memory_effect", side_effect=effect):
            result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.calls), 28)
        jobs = self.store.list_jobs(self.run_id)
        self.assertEqual(len(jobs), 14)
        self.assertTrue(all(j["selection_origin"] == "model" for j in jobs))
        self.assertNotIn("FIRST-NOTE-", json.dumps(jobs))
        self.assertNotIn("FIRST-NOTE-", json.dumps(self.store.list_requests(self.run_id)))
        for job, kwargs in self.calls:
            details = self.store.get_decision_details(self.run_id, job["wake_id"])
            activity = "choice" if "REHEARSAL CHOICE" in self.text(kwargs) else "journal"
            captured = next(row for row in details["requests"] if row["activity"] == activity)
            literal = json.dumps(kwargs["json"]["messages"], ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"))
            self.assertEqual(captured["messages"], kwargs["json"]["messages"])
            self.assertEqual(captured["input_sha256"], hashlib.sha256(literal.encode("utf-8")).hexdigest())
            self.assertEqual(captured["input_coverage"], "complete")

    def test_second_inquiry_can_append_first_uuid_available_before_choice(self):
        first_ids = {}

        def http(_url, **kwargs):
            job = self.current(kwargs)
            self.calls.append(kwargs)
            text = self.text(kwargs)
            if job["round"] == 2:
                first = next(j for j in self.store.list_jobs(self.run_id)
                             if j["wake_id"] == job["agent_id"] + "-r1")
                ident = first["record_refs"][0]["id"]
                self.assertIn(ident, text)
                self.assertIn("FIRST-QUESTION-" + job["agent_id"], text)
                first_ids[job["agent_id"]] = ident
            if "REHEARSAL CHOICE" in text:
                content = '{"action":"inquire"}'
            elif job["round"] == 1:
                content = json.dumps({"operation": "start", "title": "FIRST-QUESTION-" + job["agent_id"],
                                      "observation": "Original owned observation"})
            else:
                content = json.dumps({"operation": "append", "inquiry_id": first_ids[job["agent_id"]],
                                      "kind": "observation", "content": "Later owned observation"})
            return Response(content=content, model=kwargs["json"]["model"])

        self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertEqual(len(self.calls), 28)
        with sqlite3.connect(self.path / "trade_queue.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_inquiries").fetchone()[0], 7)
            for owner, ident in first_ids.items():
                rows = conn.execute("SELECT content FROM lineage_entries WHERE agent_id=? AND inquiry_id=? "
                                    "ORDER BY created_at,entry_id", (owner, ident)).fetchall()
                self.assertEqual([r[0] for r in rows], ["Original owned observation", "Later owned observation"])

    def test_inquiry_none_and_rest_do_not_force_records(self):
        def http(_url, **kwargs):
            job = self.current(kwargs)
            self.calls.append(kwargs)
            text = self.text(kwargs)
            content = ('{"action":"inquire"}' if job["round"] == 1 else '{"action":"rest"}')
            if "REHEARSAL CHOICE" not in text:
                content = '{"operation":"none"}'
            return Response(content=content, model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertEqual(len(self.calls), 21)
        self.assertTrue(all(not j["record_refs"] for j in self.store.list_jobs(self.run_id)))
        self.assertFalse(list((self.path / "memory").glob("*.sqlite3")))
        with sqlite3.connect(self.path / "trade_queue.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_inquiries").fetchone()[0], 0)

    def test_malformed_first_round_still_allows_second_round_rest_with_no_fallback(self):
        def http(_url, **kwargs):
            job = self.current(kwargs)
            self.calls.append(kwargs)
            if job["round"] == 2:
                self.assertTrue(all(j["status"] == "failed" for j in self.store.list_jobs(self.run_id)
                                    if j["round"] == 1))
            return Response(content='{"action":"invalid"}' if job["round"] == 1 else '{"action":"rest"}',
                            model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run()["status"], "partial")
        self.assertEqual(len(self.calls), 14)
        for job in self.store.list_jobs(self.run_id):
            self.assertEqual(job["action"], None if job["round"] == 1 else "rest")
            self.assertEqual(job["selection_origin"], "none" if job["round"] == 1 else "model")
            self.assertIsNotNone(job["decision_context"])

    def test_offers_are_not_filtered_when_chosen_activity_admission_is_denied(self):
        raw = manifest()
        raw["limits"]["max_parallelism"] = 1
        raw["limits"]["budget_usd"] = "0.1"
        for row in raw["catalog_snapshot"]["models"]:
            row["pricing"] = {"prompt": "0", "completion": "0", "request": "0.1"}
        store = RehearsalStore(Path(self.temp.name) / "denied")
        run_id = store.prepare(raw)["run_id"]
        calls = []
        def http(_url, **kwargs):
            calls.append(kwargs)
            return Response(content='{"action":"journal"}', model=kwargs["json"]["model"])
        self.controller(http, store, run_id).run()
        self.assertEqual(len(calls), 1)
        jobs = store.list_jobs(run_id)
        chosen = next(j for j in jobs if j["action"] == "journal")
        self.assertEqual(chosen["status"], "failed")
        self.assertEqual(chosen["failure_code"], "admission_budget_exceeded")
        self.assertEqual(chosen["selection_origin"], "model")
        for job in jobs:
            metadata = job["decision_context"]
            self.assertEqual(metadata["offered_actions"], list(CAPABILITIES))
            self.assertEqual(len(metadata["action_costs"]), 5)
            self.assertFalse(metadata["admission_snapshot"]["is_reservation"])
        self.assertFalse(list((store.run_path(run_id) / "memory").glob("*.sqlite3")))

    def test_catalog_upper_bounds_include_picker_and_fee_not_hrv(self):
        raw = manifest()
        for row in raw["catalog_snapshot"]["models"]:
            row["pricing"] = {"prompt": "0.000001", "completion": "0.000002", "request": "0.003"}
        job = {"agent_id": "siren"}
        continuity = {"status": "empty", "refs": [], "truncated": False, "chars": 0}
        with localcontext() as context:
            context.prec = 3
            metadata = decision_metadata(raw, job, {"reserved_usd": "0.1", "request_count": 1}, continuity)
        with localcontext() as context:
            context.prec = 100
            ceiling = (Decimal("0.000001") * raw["limits"]["max_input_bytes"]
                       + Decimal("0.000002") * raw["limits"]["max_output_tokens"] + Decimal("0.003"))
            for cost in metadata["action_costs"]:
                count = 1 if cost["action"] == "rest" else 2
                self.assertEqual(cost["max_requests"], count)
                self.assertEqual(Decimal(cost["reservation_ceiling_usd"]), ceiling * count)
        self.assertNotIn("hrv", json.dumps(metadata).lower())

    def test_recovery_reuses_context_without_new_ledger_observation(self):
        controller = self.controller(lambda _url, **kwargs: Response(model=kwargs["json"]["model"]))
        controller.prepare_profiles()
        controller._token = self.store.begin(self.run_id)
        job = self.store.claim_job(self.run_id, "siren-r1", controller._token)
        details = controller._decision_details(job, new_picker=True)
        frozen = deepcopy(details)
        messages = controller._choice_messages(details["metadata"], details["private_context"])
        other = self.store.claim_job(self.run_id, "tempest-r1", controller._token)
        request = self.store.reserve_request(
            self.run_id, other["wake_id"], controller._token, agent_id=other["agent_id"],
            activity="choice", model=other["requested_model"], input_bytes=1000,
            max_output_tokens=1024, reserved_usd="0.25")
        self.store.finish_request(self.run_id, request, outcome="not_sent", failure_code="interrupted")
        self.store.finish_job(self.run_id, other["wake_id"], controller._token,
                              status="failed", failure_code="interrupted")
        self.assertNotEqual(self.store.get_run(self.run_id)["reserved_usd"],
                            frozen["metadata"]["admission_snapshot"]["reserved_usd"])
        self.store.recover(self.run_id)
        controller._token = None
        seen = []
        def http(_url, **kwargs):
            current = self.current(kwargs)
            if current["wake_id"] == "siren-r1":
                seen.append(kwargs)
                self.assertEqual(kwargs["json"]["messages"][1:], messages)
                self.assertEqual(self.store.get_decision_details(self.run_id, "siren-r1")["metadata"],
                                 frozen["metadata"])
            return Response(model=kwargs["json"]["model"])
        # A targeted wrapper retains the actual implementation for all new wakes.
        original = RehearsalController._new_decision_context
        def guard(obj, item):
            if item["wake_id"] == "siren-r1":
                raise AssertionError("regenerated frozen context")
            return original(obj, item)
        with patch.object(RehearsalController, "_new_decision_context", guard):
            self.assertEqual(self.controller(http).run(resume=True)["status"], "partial")
        self.assertEqual(len(seen), 1)
        self.assertIsNone(self.store.get_decision_context(self.run_id, other["wake_id"]))

    def test_legacy_staged_output_has_unknown_context_not_fabricated_offers(self):
        snapshot_profiles(self.store, self.run_id, REPO)
        token = self.store.begin(self.run_id)
        self.store.claim_job(self.run_id, "siren-r1", token)
        self.store.commit_choice(self.run_id, "siren-r1", token, {"action": "journal"})
        self.store.commit_output(self.run_id, "siren-r1", token, "Legacy literal note")
        self.store.recover(self.run_id)
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            return Response(model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run(resume=True)["status"], "completed")
        self.assertEqual(len(self.calls), 13)
        self.assertIsNone(self.store.get_decision_details(self.run_id, "siren-r1"))
        self.assertIsNone(self.store.get_decision_context(self.run_id, "siren-r1"))
        second = self.store.get_decision_details(self.run_id, "siren-r2")
        self.assertIn("Legacy literal note", json.dumps(second["private_context"]))

    def test_legacy_partial_request_without_context_does_not_invent_offers_or_resend_picker(self):
        controller = self.controller(lambda _url, **kwargs: Response(model=kwargs["json"]["model"]))
        controller.prepare_profiles()
        token = self.store.begin(self.run_id)
        job = self.store.claim_job(self.run_id, "siren-r1", token)
        request = self.store.reserve_request(
            self.run_id, job["wake_id"], token, agent_id=job["agent_id"], activity="choice",
            model=job["requested_model"], input_bytes=1000, max_output_tokens=1024, reserved_usd="0")
        self.store.finish_request(self.run_id, request, outcome="not_sent", failure_code="interrupted")
        self.store.recover(self.run_id)
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            return Response(model=kwargs["json"]["model"])
        self.assertEqual(self.controller(http).run(resume=True)["status"], "partial")
        first = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertIsNone(first["action"])
        self.assertIsNone(first["decision_context"])
        self.assertEqual(first["failure_code"], "decision_context_unavailable")
        self.assertIsNone(first["selection_origin"])  # Legacy context/provenance is unknown.
        self.assertEqual(len(self.calls), 13)

    def test_missing_prior_database_reads_do_not_create_empty_files(self):
        prior = {"agent_id": "siren", "round": 1, "wake_id": "siren-r1",
                 "record_refs": [{"kind": "journal", "id": 1}]}
        with patch.object(self.store, "list_jobs", return_value=[prior]):
            context = owner_continuity(self.store, self.run_id,
                                       {"agent_id": "siren", "round": 2})
        self.assertEqual(context["status"], "unavailable")
        self.assertEqual(context["refs"], [])
        self.assertFalse((self.path / "memory" / "siren.sqlite3").exists())

    def test_four_refs_and_4000_chars_with_accurate_clipped_refs_and_unchanged_source(self):
        memory_path = self.path / "memory" / "siren.sqlite3"
        memory = ThresholdMemory(str(memory_path))
        refs = []
        for index in range(6):
            refs.extend(_memory_effect(memory, "source-" + str(index), "journal", "界" * 2000))
        original = hashlib.sha256(memory_path.read_bytes()).hexdigest()
        rows = [{"agent_id": "siren", "round": 1, "wake_id": "siren-r1", "record_refs": refs},
                {"agent_id": "tempest", "round": 1, "wake_id": "tempest-r1", "record_refs": refs},
                {"agent_id": "siren", "round": 2, "wake_id": "siren-r2", "record_refs": refs}]
        with patch.object(self.store, "list_jobs", return_value=rows):
            context = owner_continuity(self.store, self.run_id, {"agent_id": "siren", "round": 2})
        self.assertEqual(len(context["refs"]), MAX_REFS)
        self.assertLessEqual(context["chars"], MAX_CHARS)
        self.assertTrue(context["truncated"])
        self.assertTrue(all(ref["wake_id"] == "siren-r1" for ref in context["refs"]))
        clipped = clip_continuity(context, 25)
        self.assertEqual(clipped["chars"], 25)
        self.assertEqual(len(clipped["refs"]), 1)
        self.assertNotIn("界", json.dumps(public_coverage(clipped), ensure_ascii=False))
        self.assertEqual(hashlib.sha256(memory_path.read_bytes()).hexdigest(), original)

    def test_partial_missing_sources_do_not_claim_complete_coverage(self):
        memory = ThresholdMemory(str(self.path / "memory" / "siren.sqlite3"))
        refs = _memory_effect(memory, "siren-r1", "journal", "Literal linked source")
        rows = [{"agent_id": "siren", "round": 1, "wake_id": "siren-r1",
                 "record_refs": refs + [{"kind": "journal", "id": 999999}]}]
        with patch.object(self.store, "list_jobs", return_value=rows):
            context = owner_continuity(self.store, self.run_id, {"agent_id": "siren", "round": 2})
        self.assertEqual(context["status"], "truncated")
        self.assertTrue(context["truncated"])
        self.assertTrue(context["unavailable"])
        self.assertEqual([r["id"] for r in context["refs"]], [refs[0]["id"]])

    def test_choice_fits_with_mandatory_metadata_and_marks_context_before_commit(self):
        controller = self.controller(lambda _url, **kwargs: Response(model=kwargs["json"]["model"]))
        controller.prepare_profiles()
        job = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r2")
        context = {"status": "available", "refs": [{"kind": "journal", "id": 1, "wake_id": "siren-r1"}],
                   "truncated": False, "chars": 4000, "unavailable": False,
                   "excerpts": [{"kind": "journal", "id": 1, "wake_id": "siren-r1",
                                 "body": "界" * 4000, "source": "agent", "body_truncated": False}]}
        # Set a cap that fits all structural offers, but not the entire excerpt.
        controller.manifest["limits"]["max_input_bytes"] = 18600
        with patch("core.runtime.rehearsal.controller.owner_continuity", return_value=context):
            metadata, private = controller._new_decision_context(job)
        messages = controller._choice_messages(metadata, private)
        self.assertTrue(private["include_metadata"])
        self.assertEqual(metadata["continuity"], public_coverage(private["continuity"]))
        self.assertLessEqual(controller._input_size(job, messages), 18600)
        self.assertTrue(metadata["continuity"]["truncated"])
        self.assertEqual(context["chars"], 4000)
        controller.manifest["limits"]["max_input_bytes"] = 1000
        with patch("core.runtime.rehearsal.controller.owner_continuity", return_value=context):
            with self.assertRaisesRegex(ProviderError, "input_bound_exceeded"):
                controller._new_decision_context(job)


if __name__ == "__main__":
    unittest.main()
