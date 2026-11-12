"""Actual temporary private stores, injected HTTP, structurally blocked network."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.controller import (
    RehearsalController, _memory_effect, snapshot_profiles, validate_choice,
)
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.provider import OpenRouterTransport, CAPABILITIES
from core.runtime.rehearsal.store import RehearsalStore, RehearsalError, RehearsalConflict
from core.memory.engine import ThresholdMemory
from tests.test_rehearsal_provider import manifest, Response

REPO = Path(__file__).resolve().parents[1]


class Crash(BaseException):
    pass


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RehearsalStore(Path(self.temp.name) / "runs")
        self.run_id = self.store.prepare(manifest())["run_id"]
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.path = self.store.run_path(self.run_id)
        self.calls = []

    def controller(self, post=None, run_id=None, store=None, repo_root=None):
        return RehearsalController(store or self.store, run_id or self.run_id,
                                   transport=OpenRouterTransport("scripted-offline", http_post=post or ScriptedHTTP()),
                                   repo_root=repo_root)

    def rest_http(self, url, **kwargs):
        self.calls.append(kwargs)
        return Response(model=kwargs["json"]["model"])

    def test_rest_all_seven_two_rounds_no_forced_records(self):
        result = self.controller(self.rest_http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_count"], 14)
        jobs = self.store.list_jobs(self.run_id)
        self.assertEqual(len(jobs), 14)
        self.assertEqual({j["action"] for j in jobs}, {"rest"})
        self.assertTrue(all(j["record_refs"] == [] for j in jobs))
        self.assertEqual(list((self.path / "memory").glob("*.sqlite3")), [])
        with sqlite3.connect(self.path / "trade_queue.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohort_wakes").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(DISTINCT arrival_at) FROM inquiry_cohort_wakes").fetchone()[0], 0)
        self.assertTrue(all("REHEARSAL CHOICE" in call["json"]["messages"][-1]["content"] for call in self.calls))
        with self.assertRaises(RehearsalConflict):
            self.controller(self.rest_http).run(resume=True)
        self.assertEqual(len(self.calls), 14)

    def test_scripted_all_allowed_actions_receipt_owner_and_private_records(self):
        http = ScriptedHTTP()
        result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_count"], http.calls)
        self.assertLessEqual(http.calls, 28)
        jobs = self.store.list_jobs(self.run_id)
        self.assertEqual({j["action"] for j in jobs}, set(CAPABILITIES))
        self.assertTrue(all(j["status"] == "completed" for j in jobs))
        self.assertNotIn("scripted private", json.dumps(jobs))
        with sqlite3.connect(self.path / "trade_queue.sqlite3") as conn:
            receipts = conn.execute("SELECT agent_id,operation_id,status FROM inquiry_operations").fetchall()
            self.assertTrue(receipts)
            for owner, operation, status in receipts:
                self.assertTrue(operation.startswith(owner + "-r"))
                self.assertEqual(status, "complete")
        for owner in ("siren", "paradox_hunter", "oracle", "weaver"):
            with sqlite3.connect(self.path / "memory" / f"{owner}.sqlite3") as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM innermost").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM episodes WHERE delta_coherence IS NOT NULL OR effort IS NOT NULL").fetchone()[0], 0)
        requests = self.store.list_requests(self.run_id)["events"]
        self.assertTrue(any(e["cost_status"] == "unknown" for e in requests))
        self.assertNotIn("private example", json.dumps(requests))

    def test_optional_empty_journal_no_record(self):
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            text = "\n".join(m["content"] for m in kwargs["json"]["messages"])
            return Response(content='{"action":"journal"}' if "REHEARSAL CHOICE" in text else "", model=kwargs["json"]["model"])
        result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["request_count"], 28)
        for memory_path in (self.path / "memory").glob("*.sqlite3"):
            with sqlite3.connect(memory_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0], 0)
        self.assertTrue(all(j["record_refs"] == [] for j in self.store.list_jobs(self.run_id)))

    def test_concurrency_and_round_barrier(self):
        lock = threading.Lock()
        active, maximum = 0, 0
        rounds = []
        def http(_url, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                events = self.store.list_requests(self.run_id)["events"]
                last = max(events, key=lambda event: event["created_at"])
                if last["wake_id"].endswith("r2"):
                    self.assertTrue(all(j["status"] == "completed" for j in self.store.list_jobs(self.run_id) if j["round"] == 1))
                time.sleep(0.015)
                return Response(model=kwargs["json"]["model"])
            finally:
                with lock:
                    active -= 1
        self.assertEqual(self.controller(http).run()["status"], "completed")
        self.assertGreaterEqual(maximum, 2)
        self.assertLessEqual(maximum, 3)

    def test_stop_blocks_future_dispatch_and_records_inflight_result(self):
        raw = manifest(); raw["limits"]["max_parallelism"] = 1
        store = RehearsalStore(Path(self.temp.name) / "stop")
        run_id = store.prepare(raw)["run_id"]
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            store.request_stop(run_id)
            return Response(model=kwargs["json"]["model"], usage={"cost": "0.003"})
        result = self.controller(http, run_id=run_id, store=store).run()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["known_cost_usd"], "0.003")
        self.assertEqual(store.list_requests(run_id)["events"][0]["outcome"], "success")

    def test_stop_during_activity_preserves_returned_output_without_resend(self):
        raw = manifest(); raw["limits"]["max_parallelism"] = 1
        store = RehearsalStore(Path(self.temp.name) / "stop-activity")
        run_id = store.prepare(raw)["run_id"]
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                content = '{"action":"journal"}'
            else:
                store.request_stop(run_id)
                content = "Returned after stop, retained privately."
            return Response(content=content, model=kwargs["json"]["model"])
        result = self.controller(http, run_id=run_id, store=store).run()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 2)
        job = store.list_jobs(run_id)[0]
        self.assertEqual(job["status"], "completed")
        self.assertEqual(store.get_output(run_id, job["wake_id"]), "Returned after stop, retained privately.")
        self.assertEqual(len(job["record_refs"]), 1)
        self.controller(self.rest_http, run_id=run_id, store=store).run(resume=True)
        self.assertEqual(len(self.calls), 15)

    def test_request_limit_is_finite_even_for_journal_everywhere(self):
        raw = manifest(); raw["limits"]["max_requests"] = 1; raw["limits"]["max_parallelism"] = 1
        store = RehearsalStore(Path(self.temp.name) / "bounded")
        run_id = store.prepare(raw)["run_id"]
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            return Response(content='{"action":"journal"}', model=kwargs["json"]["model"])
        result = self.controller(http, run_id=run_id, store=store).run()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result["request_count"], 1)
        self.assertTrue(all(j["status"] == "failed" for j in store.list_jobs(run_id)))

    def test_deadline_prevents_admission(self):
        controller = self.controller(self.rest_http)
        controller.prepare_profiles()
        token = self.store.begin(self.run_id)
        with sqlite3.connect(self.path / "control.sqlite3") as conn:
            conn.execute("UPDATE runs SET deadline=?", (time.time() - 1,))
        self.store.end(self.run_id, token)
        with self.assertRaises(RehearsalError):
            controller.run(resume=True)
        self.assertEqual(self.calls, [])

    def test_invalid_choice_safe_failure_no_guess_no_second_call(self):
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            return Response(content='{"action":"trade"}', model=kwargs["json"]["model"])
        result = self.controller(http).run()
        self.assertEqual(result["request_count"], 14)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(all(j["status"] == "failed" and j["action"] is None for j in self.store.list_jobs(self.run_id)))
        self.assertEqual(list((self.path / "memory").glob("*.sqlite3")), [])

    def test_real_requires_prepared_snapshots_and_explicit_live_object(self):
        raw = manifest("real")
        store = RehearsalStore(Path(self.temp.name) / "real")
        run_id = store.prepare(raw)["run_id"]
        with self.assertRaisesRegex(RehearsalError, "transport_mode_mismatch"):
            self.controller(self.rest_http, run_id=run_id, store=store)
        transport = OpenRouterTransport("fake-test-only", http_post=self.rest_http, is_live=True)
        controller = RehearsalController(store, run_id, transport=transport)
        with self.assertRaisesRegex(RehearsalError, "prepare_profiles_before_real_start"):
            controller.run()
        self.assertEqual(self.calls, [])
        with self.assertRaisesRegex(RehearsalError, "explicit_transport_required"):
            RehearsalController(store, run_id, transport=None)

    def test_snapshots_preserve_originals_and_dispatch_does_not_read_live_profiles(self):
        repo = Path(self.temp.name) / "repo"
        shutil.copytree(REPO / "agents", repo / "agents")
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo / "agents").glob("*/*.json")}
        marker = snapshot_profiles(self.store, self.run_id, repo)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
        for source in (repo / "agents").glob("*/*.json"):
            source.unlink()
        self.assertEqual(snapshot_profiles(self.store, self.run_id, repo), marker)
        self.assertEqual(self.controller(self.rest_http, repo_root=repo).run()["status"], "completed")
        prompt = self.calls[0]["json"]["messages"][0]["content"]
        self.assertIn("AUTHORITATIVE CURRENT REHEARSAL CAPABILITIES", prompt)
        self.assertIn("There is no\nportfolio, paper portfolio", prompt)
        self.assertIn("Other owners' journals", prompt)

    def test_memory_bridge_replay_is_same_transaction_without_doublewrites(self):
        path = self.path / "memory" / "siren.sqlite3"
        memory = ThresholdMemory(str(path))
        refs = _memory_effect(memory, "siren-r1", "journal", "Chosen note")
        self.assertEqual(refs, _memory_effect(memory, "siren-r1", "journal", "Chosen note"))
        with sqlite3.connect(path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rehearsal_effects").fetchone()[0], 1)
        with self.assertRaises(RehearsalError):
            _memory_effect(memory, "siren-r1", "journal", "Conflicting text")

    def stage(self, *, output=None, paid_request=False, effect=False, action="journal"):
        snapshot_profiles(self.store, self.run_id, REPO)
        token = self.store.begin(self.run_id)
        job = self.store.claim_job(self.run_id, "siren-r1", token)
        self.store.commit_choice(self.run_id, job["wake_id"], token, {"action": action})
        if paid_request:
            request_id = self.store.reserve_request(self.run_id, job["wake_id"], token, agent_id="siren", activity=action,
                                                     model=job["requested_model"], input_bytes=3000,
                                                     max_output_tokens=1024, reserved_usd="0")
            self.store.mark_dispatched(self.run_id, request_id, token)
        if output is not None:
            self.store.commit_output(self.run_id, job["wake_id"], token, output)
        if effect:
            memory = ThresholdMemory(str(self.path / "memory" / "siren.sqlite3"))
            _memory_effect(memory, job["wake_id"], action, output)
        return token

    def test_restart_last_persisted_output_local_effect_not_resent(self):
        self.stage(output="Last persisted owner note")
        self.store.recover(self.run_id)
        result = self.controller(self.rest_http).run(resume=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.calls), 13)
        with sqlite3.connect(self.path / "memory" / "siren.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT content FROM journal").fetchall(), [("Last persisted owner note",)])

    def test_restart_after_effect_before_finish_dedupes(self):
        self.stage(output="Already applied", effect=True)
        self.store.recover(self.run_id)
        self.assertEqual(self.controller(self.rest_http).run(resume=True)["status"], "completed")
        with sqlite3.connect(self.path / "memory" / "siren.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0], 1)
        self.assertEqual(len(self.calls), 13)

    def test_process_death_unconfirmed_request_needs_review_no_resend(self):
        self.stage(paid_request=True)
        self.store.recover(self.run_id)
        result = self.controller(self.rest_http).run(resume=True)
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(len(self.calls), 13)
        siren = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertEqual(siren["status"], "uncertain")
        self.assertEqual(siren["failure_code"], "interrupted")

    def test_inquiry_staged_command_replays_receipt_without_model(self):
        self.stage(output='{"operation":"start","title":"Persisted question"}', action="inquire")
        self.store.recover(self.run_id)
        self.assertEqual(self.controller(self.rest_http).run(resume=True)["status"], "completed")
        self.assertEqual(len(self.calls), 13)
        with sqlite3.connect(self.path / "trade_queue.sqlite3") as conn:
            self.assertEqual(conn.execute("SELECT agent_id,title FROM lineage_inquiries").fetchall(), [("siren", "Persisted question")])

    def test_library_output_recovery_preserves_staged_citation_refs(self):
        self.stage(output="Persisted source note", action="library")
        sources = self.controller()._library("contradiction")
        refs = [{"kind": "library", "id": row["section_id"]} for row in sources["results"]]
        citation_file = self.path / "memory" / "siren-siren-r1-library.json"
        citation_file.write_text(json.dumps(refs), encoding="utf-8")
        self.store.recover(self.run_id)
        self.assertEqual(self.controller(self.rest_http).run(resume=True)["status"], "completed")
        job = next(j for j in self.store.list_jobs(self.run_id) if j["wake_id"] == "siren-r1")
        self.assertTrue(refs)
        self.assertEqual([r for r in job["record_refs"] if r["kind"] == "library"], refs)
        self.assertEqual(len(self.calls), 13)

    def test_library_passages_only_user_data_and_citations(self):
        calls = []
        def http(_url, **kwargs):
            calls.append(kwargs)
            text = "\n".join(m["content"] for m in kwargs["json"]["messages"])
            content = '{"action":"library","query":"contradiction"}' if "REHEARSAL CHOICE" in text else "An optional source note."
            return Response(content=content, model=kwargs["json"]["model"])
        result = self.controller(http).run()
        self.assertEqual(result["status"], "completed")
        activities = [c for c in calls if "REHEARSAL ACTIVITY: library" in c["json"]["messages"][1]["content"]]
        self.assertEqual(len(activities), 14)
        for call in activities:
            message = call["json"]["messages"][-1]
            self.assertEqual(message["role"], "user")
            self.assertIn("UNTRUSTED USER DATA", message["content"])
            self.assertLessEqual(len(message["content"].encode("utf-8")), 12000)
        self.assertTrue(any(ref["kind"] == "library" for j in self.store.list_jobs(self.run_id) for ref in j["record_refs"]))

    def test_strict_duplicate_unknown_fenced_choices(self):
        for raw in ('{"action":"rest","action":"journal"}', '{"action":"rest","query":"x"}',
                    '{"action":"library","query":""}', '{"action":"rest","owner":"siren"}',
                    'rest', '```{"action":"rest"}```', '[{"action":"rest"}]', '{"action":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_choice(raw)


if __name__ == "__main__":
    unittest.main()
