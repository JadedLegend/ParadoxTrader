"""Decision evidence tests use actual private temporary stores, never transport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import importlib.abc
import json
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from uuid import uuid4

from core.runtime.rehearsal.store import (
    AGENT_IDS, CAPABILITIES, DEFAULT_LIMITS, RehearsalStore,
    RehearsalError, RehearsalConflict, RehearsalBudgetExceeded, RehearsalStopped,
)


def manifest(**limits):
    models = {owner: f"synthetic/{owner}" for owner in AGENT_IDS}
    return {"schema_version": 1, "mode": "offline", "agent_models": models,
            "limits": {**DEFAULT_LIMITS, "budget_usd": "0", **limits},
            "capabilities": list(CAPABILITIES),
            "catalog_snapshot": {"source": "synthetic", "models": [
                {"id": model, "context_length": 65536, "max_completion_tokens": 1024,
                 "supported_parameters": ["max_tokens"],
                 "pricing": {"prompt": "0", "completion": "0", "request": "0"}}
                for model in models.values()]}}


def encoded_messages(messages):
    normalized = [{"role": item["role"], "content": item["content"]} for item in messages]
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def input_size(messages):
    return len(encoded_messages(messages)) + 2048 + 128 * len(messages)


class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"core.runtime.rehearsal.provider", "core.runtime.rehearsal.controller",
                        "core.runtime.scheduler", "core.runtime.llm", "requests", "httpx"}:
            raise AssertionError("forbidden import")
        return None


class DecisionStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private" / "runs"
        self.store = RehearsalStore(self.root)
        guard = ImportGuard()
        sys.meta_path.insert(0, guard)
        self.addCleanup(lambda: sys.meta_path.remove(guard))
        for name in ("socket", "create_connection", "getaddrinfo"):
            patcher = mock.patch.object(socket, name, side_effect=AssertionError("network blocked"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.run = self.store.prepare(manifest())["run_id"]
        self.token = self.store.begin(self.run)
        self.wake = "tempest-r1"
        self.store.claim_job(self.run, self.wake, self.token)
        self.db = self.store.safe_run_file(self.run, "control.sqlite3")

    def metadata(self, **coverage):
        return {"schema_version": 1, "offered_actions": list(CAPABILITIES),
                "action_costs": [{"action": action, "max_requests": 1 if action == "rest" else 2,
                                  "reservation_ceiling_usd": "0", "basis": "catalog_upper_bound"}
                                 for action in CAPABILITIES],
                "constraints": self.store.get_manifest(self.run)["limits"],
                "admission_snapshot": {"reserved_usd": "0", "remaining_budget_usd": "0",
                                       "request_count": 0, "remaining_requests": 28,
                                       "is_reservation": False},
                "model": {"requested_model": "synthetic/tempest", "context_length": 65536,
                          "max_completion_tokens": 1024, "catalog_source": "synthetic"},
                "continuity": {"status": "empty", "refs": [], "truncated": False,
                               "chars": 0, **coverage}}

    def private(self):
        return {"continuity": {"status": "empty", "refs": [], "truncated": False,
                               "chars": 0, "excerpts": [], "unavailable": False},
                "include_metadata": True, "include_continuity": True}

    def commit(self, metadata=None, private=None, wake=None, token=None):
        self.store.commit_decision_context(self.run, wake or self.wake, token or self.token,
                                           metadata=self.metadata() if metadata is None else metadata,
                                           private_context=self.private() if private is None else private)

    def reserve(self, messages, wake=None, **overrides):
        options = {"agent_id": "tempest", "activity": "choice", "model": "synthetic/tempest",
                   "input_bytes": input_size(messages), "max_output_tokens": 1024,
                   "reserved_usd": "0", **overrides}
        return self.store.reserve_request(self.run, wake or self.wake, self.token, **options)

    def legacy_schema(self):
        with sqlite3.connect(self.db) as conn:
            for name in ("immutable_decision_metadata", "immutable_private_context",
                         "immutable_request_inputs", "no_delete_request_inputs", "no_delete_decision_context"):
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            conn.execute("DROP TABLE request_inputs")
            conn.execute("ALTER TABLE jobs DROP COLUMN decision_metadata")
            conn.execute("ALTER TABLE jobs DROP COLUMN private_context")
            conn.execute("ALTER TABLE requests DROP COLUMN finish_reason")

    def test_context_exact_copy_isolated_and_public_metadata_only(self):
        meta, private = self.metadata(), self.private()
        private["quoted_note"] = "PRIVATE_CONTEXT_SENTINEL"
        self.commit(meta, private)
        self.commit(deepcopy(meta), deepcopy(private))
        private["quoted_note"] = "changed"
        returned = self.store.get_decision_details(self.run, self.wake)
        self.assertEqual(returned["requests"], [])
        self.assertEqual(returned["private_context"]["quoted_note"], "PRIVATE_CONTEXT_SENTINEL")
        returned["metadata"]["model"]["requested_model"] = "changed"
        self.assertEqual(self.store.get_decision_context(self.run, self.wake), meta)
        public = json.dumps([self.store.list_jobs(self.run), self.store.get_run(self.run),
                             self.store.list_requests(self.run), self.store.list_runs()])
        self.assertNotIn("PRIVATE_CONTEXT_SENTINEL", public)
        self.assertNotIn(self.token, public)
        self.assertNotIn("private_context", public)
        with self.assertRaises(RehearsalConflict):
            self.commit(private={"changed": True})

    def test_selection_origin_offer_choice_failure_and_legacy_are_distinct(self):
        self.assertIsNone(self.store.list_jobs(self.run)[0]["selection_origin"])
        self.commit()
        self.assertEqual(self.store.list_jobs(self.run)[0]["selection_origin"], "none")
        with self.assertRaises(RehearsalError):
            self.store.commit_choice(self.run, self.wake, self.token, {"action": "trade"})
        self.assertEqual(self.store.list_jobs(self.run)[0]["selection_origin"], "none")
        self.store.commit_choice(self.run, self.wake, self.token, {"action": "rest"})
        self.store.finish_job(self.run, self.wake, self.token, status="failed", failure_code="admission_denied")
        self.assertEqual(self.store.list_jobs(self.run)[0]["selection_origin"], "model")
        self.store.claim_job(self.run, "siren-r1", self.token)
        self.store.commit_choice(self.run, "siren-r1", self.token, {"action": "rest"})
        self.assertIsNone(self.store.list_jobs(self.run)[1]["selection_origin"])

    def test_unclaimed_stale_token_and_historical_offers_rejected(self):
        with self.assertRaises(RehearsalConflict):
            self.commit(wake="tempest-r2")
        with self.assertRaises(RehearsalConflict):
            self.commit(token=str(uuid4()))
        self.store.commit_choice(self.run, self.wake, self.token, {"action": "rest"})
        with self.assertRaises(RehearsalConflict):
            self.commit()
        self.assertIsNone(self.store.get_decision_context(self.run, self.wake))

    def test_metadata_strict_bounded_schema_and_frozen_model(self):
        mutations = [lambda m: m.update(extra="private"),
                     lambda m: m.update(schema_version=True),
                     lambda m: m.update(offered_actions=["rest"]),
                     lambda m: m["action_costs"][0].update(max_requests=True),
                     lambda m: m["action_costs"][0].update(reservation_ceiling_usd="NaN"),
                     lambda m: m["constraints"].update(max_input_bytes=24001),
                     lambda m: m["admission_snapshot"].update(is_reservation=True),
                     lambda m: m["model"].update(requested_model="synthetic/shadow"),
                     lambda m: m["continuity"].update(chars=True),
                     lambda m: m["continuity"].update(refs=[{"kind": "innermost", "id": 1}])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                meta = self.metadata()
                mutate(meta)
                with self.assertRaises(RehearsalError):
                    self.commit(metadata=meta)
        self.assertIsNone(self.store.get_decision_details(self.run, self.wake))

    def test_private_strict_json_size_and_disallowed_fields(self):
        cyclic = {}
        cyclic["self"] = cyclic
        for private in (["not a dict"], {"text": "x" * 8000}, {"n": float("nan")},
                        {"n": float("inf")}, {1: "key"}, {"tuple": (1, 2)},
                        {"bad": "\ud800"}, cyclic, {"headers": {"Authorization": "secret"}},
                        {"reasoning": "hidden"}, {"innermost": "hidden"}):
            with self.subTest(type=type(private)):
                with self.assertRaises(RehearsalError):
                    self.commit(private=private)
        self.assertIsNone(self.store.get_decision_context(self.run, self.wake))

    def test_second_wake_refs_require_prior_exact_owner_links(self):
        ref = {"kind": "journal", "id": 1}
        self.store.finish_job(self.run, self.wake, self.token, record_refs=[ref])
        self.store.claim_job(self.run, "tempest-r2", self.token)
        meta = self.metadata(status="included", refs=[{**ref, "wake_id": self.wake}], chars=4)
        private = {"continuity": {**meta["continuity"], "excerpts": [
            {**ref, "wake_id": self.wake, "body": "note", "source": "agent"}]}}
        for bad_ref in ({**ref, "wake_id": "siren-r1"}, {**ref, "agent_id": "shadow"},
                        {"kind": "journal", "id": 2}, {**ref, "wake_id": "tempest-r2"}):
            bad = deepcopy(meta)
            bad["continuity"]["refs"] = [bad_ref]
            with self.assertRaises(RehearsalConflict):
                self.commit(metadata=bad, private=private, wake="tempest-r2")
        foreign = deepcopy(private)
        foreign["continuity"]["excerpts"][0]["agent_id"] = "siren"
        with self.assertRaises(RehearsalConflict):
            self.commit(metadata=meta, private=foreign, wake="tempest-r2")
        self.commit(metadata=meta, private=private, wake="tempest-r2")
        self.assertEqual(self.store.get_decision_details(self.run, "tempest-r2")["private_context"], private)

    def test_request_snapshot_exact_hash_replay_conflict_and_redaction(self):
        self.commit()
        messages = [{"role": "system", "content": "identity"},
                    {"content": "PRIVATE_INPUT_SENTINEL \u03a9", "role": "user"}]
        request = self.reserve(messages)
        self.store.commit_request_context(self.run, request, self.token, messages)
        self.store.commit_request_context(self.run, request, self.token, deepcopy(messages))
        with self.assertRaises(RehearsalConflict):
            self.store.commit_request_context(self.run, request, self.token,
                                              [{"role": "user", "content": "different"}])
        snapshot = self.store.get_decision_details(self.run, self.wake)["requests"][0]
        self.assertEqual(snapshot["messages"], messages)
        self.assertEqual(snapshot["input_sha256"], hashlib.sha256(encoded_messages(messages)).hexdigest())
        self.assertEqual(snapshot["input_bytes"], input_size(messages))
        self.assertEqual(snapshot["input_coverage"], "complete")
        self.assertNotIn("PRIVATE_INPUT_SENTINEL", json.dumps(self.store.list_requests(self.run)))
        self.store.mark_dispatched(self.run, request, self.token)
        self.store.finish_request(self.run, request, outcome="success", finish_reason="stop")
        self.store.commit_request_context(self.run, request, self.token, messages)
        self.assertEqual(self.store.list_requests(self.run)["events"][0]["finish_reason"], "stop")

    def test_request_input_protocol_overhead_exact_boundary_and_invalid_shapes(self):
        messages = [{"role": "user", "content": ""}]
        messages[0]["content"] = "x" * (24000 - input_size(messages))
        self.assertEqual(input_size(messages), 24000)
        request = self.reserve(messages)
        for invalid in ([], [{"role": "tool", "content": "x"}],
                        [{"role": "user", "content": "x", "headers": {}}],
                        [{"role": "user", "content": "\ud800"}],
                        [{"role": "user", "content": "\u754c" * 8000}],
                        messages + [{"role": "user", "content": ""}]):
            with self.assertRaises(RehearsalError):
                self.store.commit_request_context(self.run, request, self.token, invalid)
        self.store.commit_request_context(self.run, request, self.token, messages)

    def test_request_capture_requires_matching_size_and_undispatched_owned_request(self):
        self.commit()
        messages = [{"role": "user", "content": "literal"}]
        request = self.reserve(messages, input_bytes=100)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_request_context(self.run, request, self.token, messages)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_request_context(self.run, request, str(uuid4()), messages)
        self.store.mark_dispatched(self.run, request, self.token)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_request_context(self.run, request, self.token, messages)
        self.assertEqual(self.store.get_decision_details(self.run, self.wake)["requests"], [])

    def test_context_and_request_input_sql_triggers_are_immutable(self):
        self.commit()
        messages = [{"role": "user", "content": "literal"}]
        request = self.reserve(messages)
        self.store.commit_request_context(self.run, request, self.token, messages)
        with sqlite3.connect(self.db) as conn:
            for sql in ("UPDATE jobs SET decision_metadata='{}' WHERE decision_metadata IS NOT NULL",
                        "UPDATE jobs SET private_context=NULL WHERE private_context IS NOT NULL",
                        "DELETE FROM jobs WHERE decision_metadata IS NOT NULL",
                        "UPDATE request_inputs SET messages='[]'", "DELETE FROM request_inputs"):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql)

    def test_request_details_filter_exact_owner_and_wake(self):
        self.commit()
        own = [{"role": "user", "content": "own literal"}]
        request = self.reserve(own)
        self.store.commit_request_context(self.run, request, self.token, own)
        self.store.finish_request(self.run, request, outcome="http_error")
        for owner, wake in (("siren", "siren-r1"), ("tempest", "tempest-r2")):
            self.store.claim_job(self.run, wake, self.token)
            foreign = [{"role": "user", "content": "FOREIGN_WAKE_SENTINEL"}]
            other = self.reserve(foreign, wake=wake, agent_id=owner, model=f"synthetic/{owner}")
            self.store.commit_request_context(self.run, other, self.token, foreign)
            self.store.finish_request(self.run, other, outcome="http_error")
        details = self.store.get_decision_details(self.run, self.wake)
        self.assertEqual([item["request_id"] for item in details["requests"]], [request])
        self.assertNotIn("FOREIGN_WAKE_SENTINEL", json.dumps(details))

    def test_legacy_read_is_schema_and_file_unchanged_then_explicit_write_migrates(self):
        self.legacy_schema()
        before = self.db.read_bytes()
        files = sorted(str(path) for path in self.root.rglob("*"))
        with mock.patch.object(RehearsalStore, "_context_schema", side_effect=AssertionError("read DDL")):
            self.assertIsNone(self.store.get_decision_context(self.run, self.wake))
            self.assertIsNone(self.store.get_decision_details(self.run, self.wake))
            self.assertIsNone(self.store.list_jobs(self.run)[0]["decision_context"])
            self.store.list_requests(self.run)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(files, sorted(str(path) for path in self.root.rglob("*")))
        self.commit()
        self.assertIsNotNone(self.store.get_decision_context(self.run, self.wake))
        self.assertIsNone(self.store.get_decision_context(self.run, "siren-r1"))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM request_inputs").fetchone()[0], 0)
            self.assertIn("finish_reason", [row[1] for row in conn.execute("PRAGMA table_info(requests)")])

    def test_legacy_prior_choice_and_request_cannot_fabricate_context(self):
        self.legacy_schema()
        messages = [{"role": "user", "content": "prior"}]
        request = self.reserve(messages)
        with self.assertRaises(RehearsalConflict):
            self.commit()
        self.store.mark_dispatched(self.run, request, self.token)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_request_context(self.run, request, self.token, messages)
        self.store.finish_request(self.run, request, outcome="success", finish_reason="length")
        self.assertEqual(self.store.list_requests(self.run)["events"][0]["finish_reason"], "length")
        self.assertIsNone(self.store.get_decision_details(self.run, self.wake))

    def test_recovery_preserves_context_and_revokes_stale_replays(self):
        self.commit()
        original = self.store.get_decision_details(self.run, self.wake)
        old_token = self.token
        self.store.recover(self.run)
        self.token = self.store.begin(self.run, resume=True)
        self.store.claim_job(self.run, self.wake, self.token)
        with self.assertRaises(RehearsalConflict):
            self.commit(token=old_token)
        self.commit()
        self.assertEqual(original, self.store.get_decision_details(self.run, self.wake))
        self.store.request_stop(self.run)
        self.commit()  # No new dispatch; unchanged replay remains harmless.
        self.assertEqual(original, self.store.get_decision_details(self.run, self.wake))

    def test_finish_reasons_normalized_optional_and_write_once(self):
        for index, reason in enumerate((None, "stop", "length", "tool_calls", "content_filter", "other", {"secret": "key"})):
            owner = AGENT_IDS[index]
            wake = f"{owner}-r1"
            if wake != self.wake:
                self.store.claim_job(self.run, wake, self.token)
            request = self.store.reserve_request(self.run, wake, self.token, agent_id=owner,
                activity="choice", model=f"synthetic/{owner}", input_bytes=0,
                max_output_tokens=1, reserved_usd="0")
            self.store.finish_request(self.run, request, outcome="invalid_response", finish_reason=reason)
            self.store.finish_request(self.run, request, outcome="invalid_response", finish_reason=reason)
            event = self.store.list_requests(self.run, agent_id=owner)["events"][0]
            expected = reason if reason is None or (isinstance(reason, str) and reason != "other") else "unknown"
            self.assertEqual(event["finish_reason"], expected)
            with self.assertRaises(RehearsalConflict):
                self.store.finish_request(self.run, request, outcome="invalid_response", finish_reason="stop" if expected != "stop" else "length")
        self.assertNotIn("secret", json.dumps(self.store.list_requests(self.run)))

    def test_concurrent_identical_and_conflicting_context_commits(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.commit(), range(4)))
        self.assertEqual(self.store.get_decision_context(self.run, self.wake), self.metadata())
        with self.assertRaises(RehearsalConflict):
            self.commit(private={"different": True})


if __name__ == "__main__":
    unittest.main()
