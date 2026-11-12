"""Source-factual private witness tests; actual stores, no models or network."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.provider import AGENT_IDS, OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore, RehearsalError, RehearsalConflict
from core.runtime.rehearsal.witness import WitnessStore
from tests.test_rehearsal_provider import Response, manifest


class EnvironmentalWitnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = RehearsalStore(self.root / "runs")
        self.run_id = self.store.prepare(manifest())["run_id"]
        self.path = self.store.run_path(self.run_id)
        self.db = self.path / "witness.sqlite3"
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def controller(self, http, store=None, run_id=None):
        return RehearsalController(store or self.store, run_id or self.run_id,
                                   transport=OpenRouterTransport("scripted-offline", http_post=http))

    def test_missing_reads_no_files_no_ddl_and_explicit_status(self):
        before = sorted(str(p) for p in self.root.rglob("*"))
        witness = WitnessStore(self.db)
        self.assertEqual(witness.list_accounts("tempest"), {"status": "missing", "accounts": [], "total": 0})
        self.assertIsNone(witness.get_account(str(uuid4()), "tempest"))
        snapshot = self.store.get_witness_snapshot(self.run_id)
        self.assertEqual(snapshot["run"]["prepared_owners"], list(AGENT_IDS))
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))
        self.assertFalse(self.db.exists())

    def test_scope_validation_precedes_io_and_never_redirects_filenames(self):
        witness = WitnessStore(self.db)
        with patch.object(witness, "_connection", side_effect=AssertionError("no file access")):
            for scope in ("../siren", "community", "peer", None, [], "TEMPEST"):
                with self.subTest(scope=scope), self.assertRaises(RehearsalError):
                    witness.list_accounts(scope)
                with self.assertRaises(RehearsalError):
                    witness.get_account(str(uuid4()), scope)
        with patch.object(self.store, "_connection", side_effect=AssertionError("no control access")):
            for owner in ("../siren", "steward", [], "peer"):
                with self.assertRaises(RehearsalError):
                    self.store.get_witness_snapshot(self.run_id, owner)
        for name in ("control.sqlite3", "siren.sqlite3", "other.sqlite3", "../witness.sqlite3"):
            with self.assertRaises(RehearsalError):
                WitnessStore(self.path / name)
        for bad in (True, 0, 21, "3"):
            with self.assertRaises(RehearsalError):
                witness.list_accounts("tempest", limit=bad)

    def test_snapshot_owner_filters_and_private_fields_never_read(self):
        token = self.store.begin(self.run_id)
        for owner in AGENT_IDS:
            wake = owner + "-r1"
            self.store.claim_job(self.run_id, wake, token)
            self.store.commit_choice(self.run_id, wake, token, {"action": "library", "query": "RAW-PRIVATE-QUERY-" + owner})
            self.store.commit_output(self.run_id, wake, token, "PRIVATE-OUTPUT-" + owner)
            self.store.finish_job(self.run_id, wake, token, record_refs=[{"kind": "journal", "id": 1}])
        original = self.store._connection
        accesses = []
        @contextmanager
        def guarded(run_id, **kwargs):
            with original(run_id, **kwargs) as conn:
                def authorize(action, table, column, db, trigger):
                    if action == sqlite3.SQLITE_READ:
                        accesses.append((table, column))
                        if (table == "jobs" and column in ("output", "private_context")) or table == "request_inputs":
                            return sqlite3.SQLITE_DENY
                    if action in (sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_ALTER_TABLE, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                conn.set_authorizer(authorize)
                yield conn
        before = (self.path / "control.sqlite3").read_bytes()
        with patch.object(self.store, "_connection", guarded):
            own = self.store.get_witness_snapshot(self.run_id, "tempest")
            broad = self.store.get_witness_snapshot(self.run_id)
        self.assertEqual(before, (self.path / "control.sqlite3").read_bytes())
        self.assertEqual({j["agent_id"] for j in own["jobs"]}, {"tempest"})
        self.assertEqual(own["run"]["prepared_owners"], ["tempest"])
        self.assertEqual(len(broad["jobs"]), 14)
        literal = json.dumps([own, broad])
        for forbidden in ("RAW-PRIVATE-QUERY-", "PRIVATE-OUTPUT-", "private_context", "innermost", token):
            self.assertNotIn(forbidden, literal)
        witness = WitnessStore(self.db)
        account = witness.record(own, scope="tempest", operation_key="own")
        self.assertNotIn("RAW-PRIVATE-QUERY-", account["content"])
        self.assertNotIn("PRIVATE-OUTPUT-", account["content"])
        self.assertIsNone(witness.get_account(account["id"], "siren"))
        self.assertIsNone(witness.get_account(account["id"], "steward"))
        self.assertEqual(witness.list_accounts("siren")["accounts"], [])
        with self.assertRaises(RehearsalError):
            witness.record(broad, scope="tempest", operation_key="foreign")
        with self.assertRaises(RehearsalError):
            witness.record(own, scope="steward", operation_key="foreign")

    def test_snapshot_uses_one_consistent_control_read_transaction(self):
        control = self.path / "control.sqlite3"
        with sqlite3.connect(control) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        original = self.store._connection
        changed = []
        class Probe:
            def __init__(self, conn):
                self.conn = conn
            def execute(inner, query, values=()):
                cursor = inner.conn.execute(query, values)
                if query.startswith("SELECT run_id,status,created_at"):
                    self.assertTrue(inner.conn.in_transaction)
                    # WAL permits an intervening committed writer. All following
                    # witness job/request facts must still use the earlier view.
                    with sqlite3.connect(control) as other:
                        other.execute("UPDATE jobs SET status='failed',failure_code='intervening_writer' WHERE wake_id='siren-r1'")
                    changed.append(True)
                return cursor
        @contextmanager
        def probe(run_id, **kwargs):
            with original(run_id, **kwargs) as conn:
                yield Probe(conn)
        with patch.object(self.store, "_connection", probe):
            snapshot = self.store.get_witness_snapshot(self.run_id)
        self.assertEqual(changed, [True])
        siren = next(j for j in snapshot["jobs"] if j["wake_id"] == "siren-r1")
        self.assertEqual(siren["status"], "pending")
        self.assertIsNone(siren["failure_code"])
        current = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertEqual(current["status"], "failed")

    def test_exact_repeat_idempotent_changed_source_or_scope_conflicts_append_only(self):
        witness = WitnessStore(self.db)
        snapshot = self.store.get_witness_snapshot(self.run_id)
        first = witness.record(snapshot, operation_key="wake:outcome:source-fingerprint")
        repeat = witness.record(deepcopy(snapshot), operation_key="wake:outcome:source-fingerprint")
        self.assertEqual(first, repeat)
        self.assertEqual(str(UUID(first["id"])), first["id"])
        self.assertEqual(first["author"], "witness")
        self.assertEqual(first["method"], "mechanical")
        self.assertEqual(len(first["source_digest"]), 64)
        changed = deepcopy(snapshot)
        changed["jobs"][0]["status"] = "uncertain"
        changed["jobs"][0]["failure_code"] = "unconfirmed"
        with self.assertRaises(RehearsalConflict):
            witness.record(changed, operation_key="wake:outcome:source-fingerprint")
        with self.assertRaises(RehearsalConflict):
            witness.record(self.store.get_witness_snapshot(self.run_id, "tempest"),
                           scope="tempest", operation_key="wake:outcome:source-fingerprint")
        self.assertEqual(witness.list_accounts("steward")["total"], 1)
        with sqlite3.connect(self.db) as conn:
            for sql in ("UPDATE accounts SET content='altered'", "DELETE FROM accounts"):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)
        self.assertEqual(self.store.safe_run_file(self.run_id, "witness.sqlite3"), self.db)

    def test_shared_writers_initialize_once_under_seven_owner_concurrency(self):
        snapshots = {owner: self.store.get_witness_snapshot(self.run_id, owner) for owner in AGENT_IDS}
        def record(owner):
            # Separate objects must share initialization/writer serialization.
            return WitnessStore(self.db).record(snapshots[owner], scope=owner, operation_key="owner:" + owner)
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(record, list(AGENT_IDS) * 4))
        witness = WitnessStore(self.db)
        self.assertEqual(len({a["id"] for a in results}), 7)
        for owner in AGENT_IDS:
            self.assertEqual(witness.list_accounts(owner)["total"], 1)
        self.assertEqual(witness.list_accounts("steward")["total"], 0)

    def test_private_read_does_not_modify_existing_schema_bytes_or_files(self):
        witness = WitnessStore(self.db)
        account = witness.record(self.store.get_witness_snapshot(self.run_id, "siren"),
                                 scope="siren", operation_key="read-check")
        before, files = self.db.read_bytes(), sorted(str(p) for p in self.root.rglob("*"))
        self.assertEqual(witness.get_account(account["id"], "siren"), account)
        self.assertEqual(witness.list_accounts("siren")["accounts"], [account])
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(files, sorted(str(p) for p in self.root.rglob("*")))
        # A legacy/empty SQLite file is missing, not a migration invitation.
        other = self.root / "legacy" / "witness.sqlite3"
        other.parent.mkdir()
        with sqlite3.connect(other) as conn:
            conn.execute("CREATE TABLE legacy (id INTEGER)")
        before = other.read_bytes()
        self.assertEqual(WitnessStore(other).list_accounts("steward")["status"], "missing")
        self.assertEqual(before, other.read_bytes())

    def test_fixed_db_and_all_sqlite_sidecar_symlinks_rejected_no_external_write(self):
        external = self.root / "private-external"
        external.write_text("external original")
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = Path(str(self.db) + suffix)
            path.symlink_to(external)
            with self.subTest(suffix=suffix), self.assertRaises(RehearsalError):
                WitnessStore(self.db)
            with self.assertRaises(RehearsalError):
                self.store.safe_run_file(self.run_id, "witness.sqlite3")
            self.assertEqual(external.read_text(), "external original")
            path.unlink()
        directory = self.root / "redirect"
        directory.symlink_to(self.path, target_is_directory=True)
        with self.assertRaises(RehearsalError):
            WitnessStore(directory / "witness.sqlite3")

    def test_disappearing_transient_sidecar_not_rejected_and_writer_secures_own_db(self):
        sidecar = Path(str(self.db) + "-journal")
        original = Path.lstat
        calls = []
        def disappearing(path):
            if path == sidecar:
                calls.append(True)
                raise FileNotFoundError()
            return original(path)
        with patch.object(Path, "lstat", disappearing):
            witness = WitnessStore(self.db)
            self.assertEqual(witness.list_accounts("steward")["status"], "missing")
            witness.record(self.store.get_witness_snapshot(self.run_id), operation_key="transient")
        self.assertTrue(calls)
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)

    def test_broad_counts_prepared_vs_actually_began_vs_both_completed_not_invented_rest(self):
        raw = manifest()
        raw["limits"]["max_parallelism"] = 1
        raw["limits"]["max_requests"] = 1
        store = RehearsalStore(self.root / "limited")
        run_id = store.prepare(raw)["run_id"]
        calls = []
        def http(_url, **kwargs):
            calls.append(kwargs)
            return Response(content='{"action":"journal","journal_mode":"compost"}', model=kwargs["json"]["model"])
        controller = self.controller(http, store, run_id)
        self.assertEqual(controller.run()["status"], "partial")
        self.assertEqual(len(calls), 1)
        witness = WitnessStore(store.run_path(run_id) / "witness.sqlite3")
        broad = witness.list_accounts("steward")["accounts"][0]
        self.assertIn("Prepared owners: 7", broad["content"])
        self.assertIn("actually began): 1", broad["content"])
        self.assertIn("both wakes completed: 0", broad["content"])
        self.assertIn("No committed choice recorded for 13 wakes; this is not evidence of rest", broad["content"])
        self.assertIn("failed=14", broad["content"])
        self.assertIn("Journal modes (wake counts): compost=1", broad["content"])
        self.assertIn("Journal submodes offered: note, compost, distill, witness", broad["content"])
        self.assertIn("Distinct attached source references: 0", broad["content"])
        self.assertLessEqual(len(broad["content"]), 1200)
        self.assertEqual(len(broad["source_facts"]["jobs"]), 14)
        self.assertEqual({ref["id"] for ref in broad["source_refs"] if ref["kind"] == "request"},
                         {r["request_id"] for r in store.list_requests(run_id)["events"]})
        self.assertEqual(controller.witness_errors, [])
        for owner in AGENT_IDS:
            own = witness.list_accounts(owner)
            self.assertEqual(own["total"], 2)
            self.assertTrue(all(a["scope"] == owner for a in own["accounts"]))

    def test_all_seven_completed_both_and_factual_refs_no_private_quotes(self):
        from core.runtime.rehearsal.examples import ScriptedHTTP
        controller = self.controller(ScriptedHTTP())
        self.assertEqual(controller.run()["status"], "completed")
        self.assertEqual(controller.witness_errors, [])
        witness = WitnessStore(self.db)
        account = witness.list_accounts("steward")["accounts"][0]
        self.assertIn("Prepared owners: 7", account["content"])
        self.assertIn("actually began): 7", account["content"])
        self.assertIn("both wakes completed: 7", account["content"])
        self.assertLessEqual(len(account["content"]), 1200)
        self.assertEqual(len(account["source_facts"]["jobs"]), 14)
        for forbidden in ("scripted private", "distrustful", "enthusiastic", "therapist", "FIRST-NOTE"):
            self.assertNotIn(forbidden, account["content"])
        expected = {(j["agent_id"], r["kind"], r["id"])
                    for j in self.store.list_jobs(self.run_id) for r in j["record_refs"]}
        actual = {(r["agent_id"], r["kind"], r["id"]) for r in account["source_refs"]
                  if r["kind"] not in ("run", "wake", "request")}
        self.assertEqual(actual, expected)
        for owner in AGENT_IDS:
            accounts = witness.list_accounts(owner)["accounts"]
            self.assertEqual(len(accounts), 2)
            self.assertTrue(all(all(r.get("agent_id", owner) == owner for r in a["source_refs"])
                                for a in accounts))

    def test_reporting_failure_never_changes_terminal_status_or_replays_calls(self):
        calls = []
        def http(_url, **kwargs):
            calls.append(kwargs)
            return Response(model=kwargs["json"]["model"])
        controller = self.controller(http)
        with patch.object(WitnessStore, "record", side_effect=RuntimeError("RAW PRIVATE EXCEPTION")):
            result = controller.run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_count"], 14)
        self.assertEqual(len(calls), 14)
        self.assertTrue(all(j["status"] == "completed" for j in self.store.list_jobs(self.run_id)))
        self.assertEqual(len(controller.witness_errors), 15)
        self.assertNotIn("RAW PRIVATE EXCEPTION", json.dumps(controller.witness_errors))
        self.assertFalse(self.db.exists())
        with self.assertRaises(RehearsalConflict):
            self.controller(http).run(resume=True)
        self.assertEqual(len(calls), 14)

    def test_witness_uuid_reference_contract_rejects_int_or_non_uuid(self):
        token = self.store.begin(self.run_id)
        self.store.claim_job(self.run_id, "tempest-r1", token)
        for ident in (1, True, "not-a-uuid", "../witness"):
            with self.assertRaises(RehearsalError):
                self.store.finish_job(self.run_id, "tempest-r1", token,
                                      record_refs=[{"kind": "witness", "id": ident}])
        ident = str(uuid4())
        self.store.finish_job(self.run_id, "tempest-r1", token,
                              record_refs=[{"kind": "witness", "id": ident}])
        self.assertEqual(self.store.list_jobs(self.run_id)[0]["record_refs"], [{"kind": "witness", "id": ident}])

    def test_legacy_offer_absence_remains_unknown_with_no_read_migration(self):
        control = self.path / "control.sqlite3"
        with sqlite3.connect(control) as conn:
            for name in ("immutable_decision_metadata", "immutable_private_context", "no_delete_decision_context"):
                conn.execute(f"DROP TRIGGER {name}")
            conn.execute("ALTER TABLE jobs DROP COLUMN decision_metadata")
            conn.execute("ALTER TABLE jobs DROP COLUMN private_context")
        before = control.read_bytes()
        snapshot = self.store.get_witness_snapshot(self.run_id)
        self.assertTrue(all(j["decision_context"] is None for j in snapshot["jobs"]))
        self.assertEqual(before, control.read_bytes())
        account = WitnessStore(self.db).record(snapshot, operation_key="legacy")
        self.assertIn("unknown (no historical offer snapshot) for 14 wakes", account["content"])
        self.assertNotIn("Journal submodes offered", account["content"])


if __name__ == "__main__":
    unittest.main()
