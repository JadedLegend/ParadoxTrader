"""Private temporary stores only: no network, provider, scheduler or credentials."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
import importlib.abc
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from uuid import uuid4

from core.runtime.rehearsal.store import (
    AGENT_IDS, CAPABILITIES, DEFAULT_LIMITS, RehearsalStore, RehearsalError,
    RehearsalConflict, RehearsalStopped, RehearsalBudgetExceeded,
)


def synthetic_manifest(**limit_overrides):
    """Explicit synthetic catalog; no assertion about any real available model."""
    models = {owner: f"synthetic/{owner}" for owner in AGENT_IDS}
    return {"schema_version": 1, "mode": "offline", "agent_models": models,
            "limits": {**DEFAULT_LIMITS, "budget_usd": "1", **limit_overrides},
            "capabilities": list(CAPABILITIES),
            "catalog_snapshot": {"source": "synthetic", "models": [
                {"id": model, "context_length": 65536, "max_completion_tokens": 1024,
                 "supported_parameters": ["max_tokens"],
                 "pricing": {"prompt": "0", "completion": "0", "request": "0"}}
                for model in models.values()]}}


class ForbiddenImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"core.runtime.rehearsal.provider", "core.runtime.rehearsal.controller",
                        "core.runtime.scheduler", "core.runtime.agent_loop", "core.runtime.llm",
                        "requests", "httpx", "alpaca"} or fullname.startswith("alpaca."):
            raise AssertionError(f"forbidden import: {fullname}")
        return None


class RehearsalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private" / "runs"
        self.store = RehearsalStore(self.root)
        self.guard = ForbiddenImports()
        sys.meta_path.insert(0, self.guard)
        self.addCleanup(lambda: sys.meta_path.remove(self.guard))
        for name in ("socket", "create_connection", "getaddrinfo"):
            patcher = mock.patch.object(socket, name, side_effect=AssertionError("network forbidden"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.run_id = None
        self.token = None

    def prepare(self, **limits):
        summary = self.store.prepare(synthetic_manifest(**limits))
        self.run_id = summary["run_id"]
        return summary

    def begin(self, **limits):
        self.prepare(**limits)
        self.token = self.store.begin(self.run_id)
        return self.token

    def claim(self, index=0):
        job = self.store.list_jobs(self.run_id)[index]
        self.assertIsNotNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        return job

    def reserve(self, job, **overrides):
        options = {"agent_id": job["agent_id"], "activity": "choice", "model": job["requested_model"],
                   "input_bytes": 100, "max_output_tokens": 1024, "reserved_usd": "0.1", **overrides}
        return self.store.reserve_request(self.run_id, job["wake_id"], self.token, **options)

    def finish(self, request_id, **overrides):
        self.store.finish_request(self.run_id, request_id, **{"outcome": "success", **overrides})

    def job(self, wake_id):
        return next(job for job in self.store.list_jobs(self.run_id) if job["wake_id"] == wake_id)

    def test_construction_and_missing_reads_do_not_create_root(self):
        self.assertFalse(self.root.exists())
        self.assertEqual(self.store.list_runs(), {"runs": [], "total": 0, "limit": 20, "offset": 0})
        absent = str(uuid4())
        self.assertEqual(self.store.run_path(absent), self.root / absent)
        for reader in (self.store.get_run, self.store.get_manifest, self.store.list_jobs, self.store.list_requests):
            with self.assertRaises(RehearsalError):
                reader(absent)
        self.assertFalse(self.root.exists())

    def test_import_and_construction_have_no_database_network_or_provider_side_effects(self):
        code = '''
import sys
from unittest import mock
import importlib.abc
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname in {'core.runtime.rehearsal.provider','core.runtime.rehearsal.controller','core.runtime.scheduler','core.runtime.agent_loop','requests','httpx','core.data_dir'}:
   raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
with mock.patch('os.mkdir',side_effect=AssertionError('mkdir')), mock.patch('sqlite3.connect',side_effect=AssertionError('sqlite')), mock.patch('socket.socket',side_effect=AssertionError('network')):
 from core.runtime.rehearsal.store import RehearsalStore
 s=RehearsalStore('/tmp/nonexistent-rehearsal-import-test')
 assert s.list_runs()['total']==0
'''
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[1], timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_permissions_and_exact_stable_jobs(self):
        self.prepare()
        self.assertEqual(len(self.store.list_jobs(self.run_id)), 14)
        self.assertEqual([(job["agent_id"], job["round"]) for job in self.store.list_jobs(self.run_id)],
                         [(owner, round_number) for round_number in (1, 2) for owner in AGENT_IDS])
        original = self.store.list_jobs(self.run_id)
        other = RehearsalStore(self.root)
        self.assertEqual(original, other.list_jobs(self.run_id))
        for path in [self.root, *self.store.run_path(self.run_id).rglob("*")]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        self.assertEqual(self.root.parent.stat().st_mode & 0o777, 0o700)

    def test_manifest_and_job_definitions_are_immutable_and_copy_isolated(self):
        manifest = synthetic_manifest()
        summary = self.store.prepare(manifest)
        self.run_id = summary["run_id"]
        original = self.store.get_manifest(self.run_id)
        manifest["agent_models"]["tempest"] = "modified/model"
        summary["limits"]["budget_usd"] = "999"
        altered = self.store.get_manifest(self.run_id)
        altered["limits"]["budget_usd"] = "999"
        self.assertEqual(original, self.store.get_manifest(self.run_id))
        with self.assertRaises(RehearsalConflict):
            self.store.prepare(synthetic_manifest(), run_id=self.run_id)
        with sqlite3.connect(self.store.run_path(self.run_id) / "control.sqlite3") as connection:
            for sql in ("UPDATE runs SET manifest='{}'", "UPDATE jobs SET round=9", "UPDATE jobs SET agent_id='other'"):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql)

    def test_invalid_manifest_never_creates_root(self):
        invalid = []
        for key in DEFAULT_LIMITS:
            manifest = synthetic_manifest()
            manifest["limits"][key] = DEFAULT_LIMITS[key] + 1
            invalid.append(manifest)
            boolean = synthetic_manifest()
            boolean["limits"][key] = True
            invalid.append(boolean)
        one_round = synthetic_manifest(wakes_per_agent=1)
        invalid.append(one_round)
        for change in (lambda m: m.update(mode="real"),
                       lambda m: m["agent_models"].pop("tempest"),
                       lambda m: m["agent_models"].update(tempest="../bad model"),
                       lambda m: m["capabilities"].append("trade"),
                       lambda m: m["catalog_snapshot"].pop("source"),
                       lambda m: m["catalog_snapshot"]["models"].pop(),
                       lambda m: m["catalog_snapshot"]["models"][0]["pricing"].update(image="0.1"),
                       lambda m: m["catalog_snapshot"]["models"][0]["pricing"].update(prompt="1001"),
                       lambda m: m["catalog_snapshot"]["models"][0].update(context_length=100),
                       lambda m: m["catalog_snapshot"]["models"][0].update(max_completion_tokens=1),
                       lambda m: m["catalog_snapshot"]["models"][0].update(supported_parameters=["tools"]),
                       lambda m: m["catalog_snapshot"]["models"][0].update(headers={"Authorization": "private"}),
                       lambda m: m.update(unexpected="private")):
            manifest = synthetic_manifest()
            change(manifest)
            invalid.append(manifest)
        for manifest in invalid:
            with self.subTest(manifest=manifest):
                with self.assertRaises(RehearsalError):
                    self.store.prepare(manifest)
                self.assertFalse(self.root.exists())

    def test_real_manifest_requires_positive_budget_and_non_synthetic_catalog(self):
        manifest = synthetic_manifest(budget_usd="0")
        manifest.update(mode="real")
        manifest["catalog_snapshot"]["source"] = "openrouter"
        with self.assertRaises(RehearsalError):
            self.store.prepare(manifest)
        manifest["limits"]["budget_usd"] = "0.5"
        summary = self.store.prepare(manifest)
        self.assertEqual(summary["mode"], "real")
        self.assertEqual(summary["status"], "prepared")

    def test_explicit_single_controller_and_no_timeout_takeover(self):
        self.begin()
        for resume in (False, True):
            with self.assertRaises(RehearsalConflict):
                self.store.begin(self.run_id, resume=resume)
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=10**12):
            with self.assertRaises(RehearsalConflict):
                self.store.begin(self.run_id, resume=True)
            with self.assertRaises(RehearsalStopped):
                self.store.assert_active(self.run_id, self.token)
        with self.assertRaises(RehearsalConflict):
            self.store.assert_active(self.run_id, str(uuid4()))
        self.store.assert_active(self.run_id, self.token)

    def test_begin_race_has_exactly_one_winner(self):
        self.prepare()
        barrier = threading.Barrier(8)
        def start(_):
            barrier.wait()
            try:
                return self.store.begin(self.run_id)
            except RehearsalConflict:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(start, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_claim_is_atomic_and_terminal_jobs_never_reissued(self):
        self.begin()
        wake_id = self.store.list_jobs(self.run_id)[0]["wake_id"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.store.claim_job(self.run_id, wake_id, self.token), range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.store.commit_choice(self.run_id, wake_id, self.token, {"action": "rest"})
        self.store.finish_job(self.run_id, wake_id, self.token, action="rest")
        self.assertIsNone(self.store.claim_job(self.run_id, wake_id, self.token))
        with self.assertRaises(RehearsalConflict):
            self.store.finish_job(self.run_id, wake_id, self.token, status="failed")
        self.store.end(self.run_id, self.token)
        self.token = self.store.begin(self.run_id, resume=True)
        self.assertIsNone(self.store.claim_job(self.run_id, wake_id, self.token))

    def test_write_once_private_choice_output_and_summary_redaction(self):
        self.begin()
        job = self.claim()
        wake_id = job["wake_id"]
        choice = {"action": "library", "query": "PRIVATE_QUERY_SENTINEL"}
        self.store.commit_choice(self.run_id, wake_id, self.token, choice)
        self.store.commit_choice(self.run_id, wake_id, self.token, choice)
        returned = self.store.get_choice(self.run_id, wake_id)
        returned["query"] = "changed"
        self.assertEqual(self.store.get_choice(self.run_id, wake_id), choice)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_choice(self.run_id, wake_id, self.token, {"action": "rest"})
        self.store.commit_output(self.run_id, wake_id, self.token, "PRIVATE_OUTPUT_SENTINEL")
        self.store.commit_output(self.run_id, wake_id, self.token, "PRIVATE_OUTPUT_SENTINEL")
        with self.assertRaises(RehearsalConflict):
            self.store.commit_output(self.run_id, wake_id, self.token, "replacement")
        self.store.finish_job(self.run_id, wake_id, self.token, record_refs=[{"kind": "library", "id": "local-1"}])
        summaries = json.dumps([self.store.get_run(self.run_id), self.store.list_jobs(self.run_id), self.store.list_requests(self.run_id), self.store.list_runs()])
        for secret in ("PRIVATE_QUERY_SENTINEL", "PRIVATE_OUTPUT_SENTINEL"):
            self.assertNotIn(secret, summaries)
        self.assertEqual(self.store.get_output(self.run_id, wake_id), "PRIVATE_OUTPUT_SENTINEL")
        with sqlite3.connect(self.store.run_path(self.run_id) / "control.sqlite3") as connection:
            for sql in ("UPDATE jobs SET choice='{}' WHERE choice IS NOT NULL", "UPDATE jobs SET output='other' WHERE output IS NOT NULL"):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql)

    def test_choice_and_output_are_strict_and_token_required(self):
        self.begin()
        job = self.claim()
        for choice in ({"action": "trade"}, {"action": "rest", "query": "bad"},
                       {"action": "journal", "reasoning": "hidden"}, {"action": "library", "query": ""},
                       {"action": "library", "query": "x" * 2001}, "```json {} ```"):
            with self.assertRaises(RehearsalError):
                self.store.commit_choice(self.run_id, job["wake_id"], self.token, choice)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_output(self.run_id, job["wake_id"], self.token, "before-choice")
        self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "journal"})
        for content in (None, {}, "x" * 65537, "\ud800"):
            with self.assertRaises(RehearsalError):
                self.store.commit_output(self.run_id, job["wake_id"], self.token, content)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_output(self.run_id, job["wake_id"], str(uuid4()), "not allowed")
        with self.assertRaises(RehearsalConflict):
            self.store.finish_job(self.run_id, job["wake_id"], str(uuid4()))
        with self.assertRaises(RehearsalConflict):
            self.store.finish_job(self.run_id, job["wake_id"], self.token, action="rest")

    def test_request_identity_bounds_and_failed_validation_are_atomic(self):
        self.begin()
        job = self.claim()
        for overrides in ({"agent_id": "shadow"}, {"model": "synthetic/other"}, {"activity": "trade"},
                          {"input_bytes": 24001}, {"input_bytes": True}, {"input_bytes": -1},
                          {"max_output_tokens": 1025}, {"max_output_tokens": 0},
                          {"reserved_usd": "NaN"}, {"reserved_usd": "-1"}):
            with self.assertRaises(RehearsalError):
                self.reserve(job, **overrides)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 0)
        self.assertEqual(self.job(job["wake_id"])["request_count"], 0)
        pending = self.store.list_jobs(self.run_id)[1]
        with self.assertRaises(RehearsalConflict):
            self.reserve(pending)

    def test_request_input_output_lower_manifest_caps_enforced(self):
        self.begin(max_input_bytes=99, max_output_tokens=100)
        job = self.claim()
        with self.assertRaises(RehearsalBudgetExceeded):
            self.reserve(job, max_output_tokens=100)
        with self.assertRaises(RehearsalBudgetExceeded):
            self.reserve(job, input_bytes=99)
        request = self.reserve(job, input_bytes=99, max_output_tokens=100)
        self.assertIsNotNone(request)

    def test_attempts_cap_two_per_wake_and_twenty_eight_total(self):
        self.begin(budget_usd="0")
        for index in range(14):
            job = self.claim(index)
            for _ in range(2):
                request = self.reserve(job, reserved_usd="0")
                self.finish(request, outcome="http_error")
            with self.assertRaises(RehearsalBudgetExceeded):
                self.reserve(job, reserved_usd="0")
        summary = self.store.get_run(self.run_id)
        self.assertEqual(summary["request_count"], 28)
        self.assertEqual(summary["unknown_cost_requests"], 28)
        self.assertEqual(summary["reserved_usd"], "0")

    def test_atomic_budget_race_and_never_release_failure_or_unknown(self):
        self.begin(budget_usd="0.15")
        jobs = [self.claim(index) for index in range(7)]
        barrier = threading.Barrier(7)
        def reserve(job):
            barrier.wait()
            try:
                return self.reserve(job)
            except RehearsalBudgetExceeded:
                return None
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(reserve, jobs))
        requests = [value for value in results if value]
        self.assertEqual(len(requests), 1)
        self.finish(requests[0], outcome="http_error", usage={"provider_cost_usd": "0"})
        with self.assertRaises(RehearsalBudgetExceeded):
            self.reserve(jobs[0], reserved_usd="0.06")
        self.assertEqual(self.store.get_run(self.run_id)["reserved_usd"], "0.1")

    def test_atomic_attempt_limit_race(self):
        self.begin(max_requests=1)
        jobs = [self.claim(index) for index in range(7)]
        def reserve(job):
            try:
                return self.reserve(job)
            except RehearsalBudgetExceeded:
                return None
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(reserve, jobs))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 1)

    def test_atomic_parallelism_limit_and_no_same_wake_resend(self):
        self.begin()
        jobs = [self.claim(index) for index in range(7)]
        def reserve(job):
            try:
                return self.reserve(job)
            except RehearsalConflict:
                return None
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(reserve, jobs))
        self.assertEqual(sum(value is not None for value in results), 3)
        for job, request in zip(jobs, results):
            if request:
                with self.assertRaises(RehearsalConflict):
                    self.reserve(job)
                self.finish(request)
        for job, request in zip(jobs, results):
            if request is None:
                self.reserve(job)
                break

    def test_decimal_budget_pathologies_are_bounded_and_exact_under_small_context(self):
        for budget in ("1e999999999", "1e-101", "9" * 300, "NaN", "Infinity", "-1", True, 1, "1e1000000000000000000000000000000000"):
            with self.subTest(budget=budget):
                with self.assertRaises(RehearsalError):
                    self.store.prepare(synthetic_manifest(budget_usd=budget))
        self.assertFalse(self.root.exists())
        with localcontext() as context:
            context.prec = 2
            context.Emax = 1
            context.Emin = -1
            self.begin(budget_usd="1e100")
            jobs = [self.claim(index) for index in range(3)]
            for job, amount in zip(jobs, ("1e99", "0.000000000000000000001", "0.123456789012345678901")):
                request = self.reserve(job, reserved_usd=amount)
                self.finish(request, usage={"provider_cost_usd": amount})
            summary = self.store.get_run(self.run_id)
        expected = Decimal("1" + "0" * 99 + ".123456789012345678902")
        self.assertEqual(Decimal(summary["reserved_usd"]), expected)
        self.assertEqual(Decimal(summary["known_cost_usd"]), expected)

    def test_mark_dispatched_is_atomic_and_one_shot(self):
        self.begin()
        request = self.reserve(self.claim())
        db = self.store.safe_run_file(self.run_id, "control.sqlite3")
        with sqlite3.connect(db) as connection:
            self.assertEqual(connection.execute("SELECT dispatched FROM requests").fetchone()[0], 0)
        barrier = threading.Barrier(8)
        def dispatch(_):
            barrier.wait()
            try:
                self.store.mark_dispatched(self.run_id, request, self.token)
                return True
            except RehearsalConflict:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(dispatch, range(8))), 1)
        with sqlite3.connect(db) as connection:
            self.assertEqual(connection.execute("SELECT dispatched FROM requests").fetchone()[0], 1)
        with self.assertRaises(RehearsalConflict):
            self.finish(request, outcome="not_sent", failure_code="admission_stopped")
        self.finish(request)
        with self.assertRaises(RehearsalConflict):
            self.store.mark_dispatched(self.run_id, request, self.token)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 1)

    def test_mark_dispatched_requires_current_token_owned_unfinished_request(self):
        self.begin()
        request = self.reserve(self.claim())
        for bad_id in ("../escape", None, 1):
            with self.assertRaises(RehearsalError):
                self.store.mark_dispatched(self.run_id, bad_id, self.token)
        with self.assertRaises(RehearsalError):
            self.store.mark_dispatched(self.run_id, str(uuid4()), self.token)
        with self.assertRaises(RehearsalConflict):
            self.store.mark_dispatched(self.run_id, request, str(uuid4()))
        other = self.store.prepare(synthetic_manifest())["run_id"]
        other_token = self.store.begin(other)
        with self.assertRaises(RehearsalError):
            self.store.mark_dispatched(other, request, other_token)
        # Bare finish remains compatible with store-only synthetic fixtures.
        self.finish(request)
        with self.assertRaises(RehearsalConflict):
            self.store.mark_dispatched(self.run_id, request, self.token)
        events = self.store.list_requests(self.run_id)["events"]
        self.assertNotIn(self.token, json.dumps(events))

    def test_reserved_then_stopped_dispatch_denied_and_not_sent_retains_budget(self):
        self.begin()
        job = self.claim()
        request = self.reserve(job)
        self.store.request_stop(self.run_id)
        with self.assertRaises(RehearsalStopped):
            self.store.mark_dispatched(self.run_id, request, self.token)
        self.finish(request, outcome="not_sent", failure_code="admission_stopped")
        self.finish(request, outcome="not_sent", failure_code="admission_stopped")
        with self.assertRaises(RehearsalStopped):
            self.reserve(job)
        summary = self.store.end(self.run_id, self.token)
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["reserved_usd"], "0.1")
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertEqual((event["outcome"], event["failure_code"]), ("not_sent", "admission_stopped"))
        self.assertTrue(all(agent["stopped"] == 2 and agent["pending"] == 0 for agent in summary["agents"]))

    def test_dispatch_deadline_denied_and_end_preserves_stopped_progress(self):
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1000):
            self.begin(max_runtime_seconds=10)
            request = self.reserve(self.claim())
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1010):
            with self.assertRaises(RehearsalStopped):
                self.store.mark_dispatched(self.run_id, request, self.token)
            summary = self.store.end(self.run_id, self.token)
            self.assertEqual(summary["status"], "stopped")
            self.assertTrue(all(agent["stopped"] == 2 for agent in summary["agents"]))
            self.assertEqual(self.store.recover(self.run_id)["agents"], summary["agents"])
            with self.assertRaises(RehearsalStopped):
                self.store.begin(self.run_id, resume=True)
        self.assertEqual(self.store.list_requests(self.run_id)["events"][0]["outcome"], "not_sent")
        with sqlite3.connect(self.store.safe_run_file(self.run_id, "control.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT deadline FROM runs").fetchone()[0], 1010)

    def test_stop_end_recover_preserves_terminals_and_only_explicit_resume_unstops_safe_jobs(self):
        self.begin()
        staged, completed, failed, paid = [self.claim(index) for index in range(4)]
        self.store.commit_choice(self.run_id, staged["wake_id"], self.token, {"action": "journal"})
        self.store.commit_output(self.run_id, staged["wake_id"], self.token, "PRIVATE_STAGED_OUTPUT")
        self.store.commit_choice(self.run_id, completed["wake_id"], self.token, {"action": "rest"})
        self.store.finish_job(self.run_id, completed["wake_id"], self.token)
        self.store.finish_job(self.run_id, failed["wake_id"], self.token, status="failed", failure_code="bounded_failure")
        request = self.reserve(paid)
        self.store.mark_dispatched(self.run_id, request, self.token)
        self.store.request_stop(self.run_id)
        ended = self.store.end(self.run_id, self.token)
        self.assertEqual(self.job(staged["wake_id"])["status"], "stopped")
        self.assertEqual(self.job(completed["wake_id"])["status"], "completed")
        self.assertEqual(self.job(failed["wake_id"])["status"], "failed")
        self.assertEqual(self.job(paid["wake_id"])["status"], "uncertain")
        self.assertEqual(sum(agent["pending"] for agent in ended["agents"]), 0)
        jobs = self.store.list_jobs(self.run_id)
        self.assertEqual(self.store.recover(self.run_id)["agents"], ended["agents"])
        self.assertEqual([job["status"] for job in self.store.list_jobs(self.run_id)], [job["status"] for job in jobs])
        with self.assertRaises(RehearsalConflict):
            self.store.begin(self.run_id)
        self.token = self.store.begin(self.run_id, resume=True)
        self.assertFalse(self.store.get_run(self.run_id)["stop_requested"])
        self.assertIsNotNone(self.store.claim_job(self.run_id, staged["wake_id"], self.token))
        self.assertEqual(self.store.get_output(self.run_id, staged["wake_id"]), "PRIVATE_STAGED_OUTPUT")
        for job in (completed, failed, paid):
            self.assertIsNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        with self.assertRaises(RehearsalConflict):
            self.reserve(paid)
        self.assertEqual(self.store.get_run(self.run_id)["reserved_usd"], "0.1")

    def test_recovery_without_stop_keeps_explicitly_stopped_jobs_until_resume(self):
        self.begin()
        job = self.claim()
        self.store.finish_job(self.run_id, job["wake_id"], self.token, status="stopped", failure_code="local_stop")
        self.store.end(self.run_id, self.token)
        self.store.recover(self.run_id)
        self.assertEqual(self.job(job["wake_id"])["status"], "stopped")
        self.token = self.store.begin(self.run_id, resume=True)
        self.assertIsNotNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))

    def test_stop_prevents_claim_and_reservation_but_inflight_settles(self):
        self.begin()
        job = self.claim()
        request = self.reserve(job)
        self.assertEqual(self.store.request_stop(self.run_id)["status"], "stopped")
        with self.assertRaises(RehearsalStopped):
            self.store.claim_job(self.run_id, self.store.list_jobs(self.run_id)[1]["wake_id"], self.token)
        with self.assertRaises(RehearsalStopped):
            self.reserve(job)
        self.finish(request, usage={"provider_cost_usd": "0.01"}, response_model="synthetic/returned", provider="Synthetic Provider", duration_ms=20)
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertEqual(event["outcome"], "success")
        self.assertEqual(event["cost_usd"], "0.01")
        self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "rest"})
        self.store.finish_job(self.run_id, job["wake_id"], self.token, status="stopped")
        self.assertEqual(self.store.end(self.run_id, self.token)["status"], "stopped")
        self.assertEqual(self.store.get_run(self.run_id)["reserved_usd"], "0.1")

    def test_post_stop_returned_output_can_checkpoint_only_with_current_token(self):
        self.begin()
        job = self.claim()
        self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "journal"})
        request = self.reserve(job, activity="journal")
        self.store.request_stop(self.run_id)
        self.finish(request)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_output(self.run_id, job["wake_id"], str(uuid4()), "private")
        self.store.commit_output(self.run_id, job["wake_id"], self.token, "private")
        self.store.finish_job(self.run_id, job["wake_id"], self.token)
        self.store.end(self.run_id, self.token)
        with self.assertRaises(RehearsalConflict):
            self.store.commit_output(self.run_id, job["wake_id"], self.token, "private")
        self.assertEqual(self.store.get_output(self.run_id, job["wake_id"]), "private")

    def test_stop_and_reservation_race_has_no_post_stop_admission(self):
        self.begin()
        jobs = [self.claim(index) for index in range(7)]
        def reserve(job):
            try:
                return self.reserve(job)
            except (RehearsalStopped, RehearsalConflict):
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            pending = [pool.submit(reserve, job) for job in jobs]
            stopped = pool.submit(self.store.request_stop, self.run_id)
            stopped.result()
            for future in pending:
                future.result()
        total = self.store.get_run(self.run_id)["request_count"]
        for job in jobs:
            with self.assertRaises(RehearsalStopped):
                self.reserve(job)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], total)

    def test_deadline_never_resets_on_resume(self):
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1000):
            self.begin(max_runtime_seconds=10)
            self.store.end(self.run_id, self.token)
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1010):
            with self.assertRaises(RehearsalStopped):
                self.store.begin(self.run_id, resume=True)
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1009):
            self.token = self.store.begin(self.run_id, resume=True)
        with mock.patch("core.runtime.rehearsal.store.time.time", return_value=1010):
            with self.assertRaises(RehearsalStopped):
                self.store.assert_active(self.run_id, self.token)
            with self.assertRaises(RehearsalStopped):
                self.store.claim_job(self.run_id, self.store.list_jobs(self.run_id)[0]["wake_id"], self.token)

    def test_explicit_recovery_retains_inflight_reservation_and_never_retries(self):
        self.begin()
        job = self.claim()
        request = self.reserve(job)
        self.store.mark_dispatched(self.run_id, request, self.token)
        old_token = self.token
        recreated = RehearsalStore(self.root)
        with self.assertRaises(RehearsalConflict):
            recreated.begin(self.run_id, resume=True)
        recovered = recreated.recover(self.run_id)
        self.assertEqual(recovered["status"], "uncertain")
        self.assertEqual(recovered["reserved_usd"], "0.1")
        self.assertEqual(recovered["unknown_cost_requests"], 1)
        self.assertEqual(self.job(job["wake_id"])["status"], "uncertain")
        self.assertEqual(self.store.list_requests(self.run_id)["events"][0]["outcome"], "uncertain")
        self.token = self.store.begin(self.run_id, resume=True)
        self.assertIsNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        with self.assertRaises(RehearsalConflict):
            self.reserve(job)
        with self.assertRaises(RehearsalConflict):
            self.store.finish_job(self.run_id, job["wake_id"], old_token)
        with self.assertRaises(RehearsalConflict):
            self.finish(request)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 1)

    def test_resume_safe_choices_and_outputs_never_repeat_paid_work(self):
        self.begin()
        choice_only = self.claim(0)
        output_ready = self.claim(1)
        safe_unstarted = self.claim(2)
        completed = self.claim(3)
        for job in (choice_only, output_ready):
            request = self.reserve(job)
            self.finish(request)
            self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "journal"})
        activity_request = self.reserve(output_ready, activity="journal")
        self.finish(activity_request)
        self.store.commit_output(self.run_id, output_ready["wake_id"], self.token, "PRIVATE_PERSISTED_OUTPUT")
        self.store.commit_choice(self.run_id, completed["wake_id"], self.token, {"action": "rest"})
        self.store.finish_job(self.run_id, completed["wake_id"], self.token)
        self.store.recover(self.run_id)
        self.token = self.store.begin(self.run_id, resume=True)
        for job in (choice_only, output_ready, safe_unstarted):
            self.assertIsNotNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        self.assertEqual(self.store.get_choice(self.run_id, choice_only["wake_id"]), {"action": "journal"})
        self.assertEqual(self.store.get_output(self.run_id, output_ready["wake_id"]), "PRIVATE_PERSISTED_OUTPUT")
        self.assertIsNone(self.store.claim_job(self.run_id, completed["wake_id"], self.token))
        self.store.finish_job(self.run_id, output_ready["wake_id"], self.token)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 3)

    def test_safe_output_checkpoint_replays_local_effect_after_application_uncertainty(self):
        self.begin()
        job = self.claim()
        self.finish(self.reserve(job))
        self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "journal"})
        self.finish(self.reserve(job, activity="journal"))
        self.store.commit_output(self.run_id, job["wake_id"], self.token, "private checkpoint")
        self.store.finish_job(self.run_id, job["wake_id"], self.token, status="uncertain", failure_code="application_needs_review")
        self.store.recover(self.run_id)
        self.token = self.store.begin(self.run_id, resume=True)
        self.assertIsNotNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        self.assertEqual(self.store.get_output(self.run_id, job["wake_id"]), "private checkpoint")
        for activity in ("choice", "journal"):
            with self.assertRaises(RehearsalConflict):
                self.reserve(job, activity=activity)
        self.store.finish_job(self.run_id, job["wake_id"], self.token)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 2)

    def test_successful_request_cannot_be_resent_even_before_checkpoint_commit(self):
        self.begin()
        job = self.claim()
        self.finish(self.reserve(job))
        with self.assertRaises(RehearsalConflict):
            self.reserve(job)
        self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "journal"})
        with self.assertRaises(RehearsalConflict):
            self.reserve(job)
        self.finish(self.reserve(job, activity="journal"))
        with self.assertRaises(RehearsalConflict):
            self.reserve(job, activity="journal")

    def test_success_without_durable_choice_or_output_cannot_trigger_resend(self):
        self.begin()
        missing_choice = self.claim(0)
        missing_output = self.claim(1)
        self.finish(self.reserve(missing_choice))
        self.store.commit_choice(self.run_id, missing_output["wake_id"], self.token, {"action": "journal"})
        self.finish(self.reserve(missing_output, activity="journal"))
        self.store.recover(self.run_id)
        self.token = self.store.begin(self.run_id, resume=True)
        for job in (missing_choice, missing_output):
            self.assertEqual(self.job(job["wake_id"])["status"], "uncertain")
            self.assertIsNone(self.store.claim_job(self.run_id, job["wake_id"], self.token))
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 2)

    def test_finish_request_allowlist_immutable_and_unknown_distinct_zero(self):
        self.begin()
        unknown_job = self.claim(0)
        zero_job = self.claim(1)
        unknown = self.reserve(unknown_job)
        zero = self.reserve(zero_job)
        self.finish(unknown, usage={"input_tokens": 10, "messages": "PRIVATE_MESSAGES", "headers": "PRIVATE_KEY", "reasoning": "PRIVATE_REASONING"})
        arguments = {"outcome": "success", "usage": {"provider_cost_usd": "0", "input_tokens": 0}, "duration_ms": 1}
        self.store.finish_request(self.run_id, zero, **arguments)
        self.store.finish_request(self.run_id, zero, **arguments)
        with self.assertRaises(RehearsalConflict):
            self.finish(zero, usage={"provider_cost_usd": "1"})
        events = self.store.list_requests(self.run_id)["events"]
        self.assertIsNone(events[0]["cost_usd"])
        self.assertEqual(events[0]["cost_status"], "unknown")
        self.assertIsNone(events[0]["output_tokens"])
        self.assertEqual(events[1]["cost_usd"], "0")
        self.assertEqual(events[1]["cost_status"], "reported")
        self.assertEqual(events[1]["input_tokens"], 0)
        summary = self.store.get_run(self.run_id)
        self.assertEqual(summary["unknown_cost_requests"], 1)
        self.assertEqual(summary["known_cost_usd"], "0")
        blob = (self.store.run_path(self.run_id) / "control.sqlite3").read_bytes()
        for secret in ("PRIVATE_MESSAGES", "PRIVATE_KEY", "PRIVATE_REASONING"):
            self.assertNotIn(secret, json.dumps(events))
            self.assertNotIn(secret.encode(), blob)
        with sqlite3.connect(self.store.run_path(self.run_id) / "control.sqlite3") as connection:
            for sql in ("DELETE FROM requests", "UPDATE requests SET reserved_usd='0'"):
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(sql)

    def test_finish_job_cannot_hide_unresolved_request_or_freeform_refs(self):
        self.begin()
        job = self.claim()
        self.reserve(job)
        with self.assertRaises(RehearsalConflict):
            self.store.finish_job(self.run_id, job["wake_id"], self.token)
        for refs in ([{"kind": "journal", "id": 1, "content": "private"}],
                     [{"kind": "innermost", "id": 1}], [{"kind": "journal", "id": "../../escape"}]):
            with self.assertRaises(RehearsalError):
                self.store.finish_job(self.run_id, job["wake_id"], self.token, status="failed", record_refs=refs)
        with self.assertRaises(RehearsalError):
            self.store.finish_job(self.run_id, job["wake_id"], self.token, status="failed", failure_code="raw error with content")

    def test_pagination_and_selected_owner_filters(self):
        self.begin()
        for index in range(3):
            job = self.claim(index)
            self.finish(self.reserve(job))
        page = self.store.list_requests(self.run_id, limit=1, offset=1)
        self.assertEqual(page["total"], 3)
        self.assertEqual(len(page["events"]), 1)
        self.assertEqual(page["events"][0]["agent_id"], "siren")
        owner_page = self.store.list_requests(self.run_id, agent_id="tempest")
        self.assertEqual(owner_page["total"], 1)
        self.assertEqual(owner_page["events"][0]["agent_id"], "tempest")
        for kwargs in ({"limit": True}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 1.5}):
            with self.assertRaises(RehearsalError):
                self.store.list_runs(**kwargs)
            with self.assertRaises(RehearsalError):
                self.store.list_requests(self.run_id, **kwargs)
        with self.assertRaises(RehearsalError):
            self.store.list_requests(self.run_id, agent_id="../other")

    def test_invalid_run_ids_and_root_traversal_rejected(self):
        for ident in ("../escape", "..", str(uuid4()).upper(), "not-uuid", 1, None):
            with self.assertRaises(RehearsalError):
                self.store.run_path(ident)
        with self.assertRaises(RehearsalError):
            RehearsalStore(Path(self.tmp.name) / ".." / "escape")
        self.assertFalse(self.root.exists())

    def test_root_parent_run_database_and_sidecar_symlinks_rejected(self):
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        linked = Path(self.tmp.name) / "linked"
        linked.symlink_to(target, target_is_directory=True)
        for root in (linked, linked / "nested"):
            with self.assertRaises(RehearsalError):
                RehearsalStore(root)
        self.prepare()
        run_path = self.store.run_path(self.run_id)
        fake = self.root / str(uuid4())
        fake.symlink_to(target, target_is_directory=True)
        with self.assertRaises(RehearsalError):
            self.store.run_path(fake.name)
        with self.assertRaises(RehearsalError):
            self.store.list_runs()
        fake.unlink()
        db = run_path / "control.sqlite3"
        original = run_path / "saved-control.sqlite3"
        db.rename(original)
        db.symlink_to(original)
        with self.assertRaises(RehearsalError):
            self.store.get_run(self.run_id)
        db.unlink()
        original.rename(db)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(db) + suffix)
            sidecar.symlink_to(target / "missing")
            with self.assertRaises(RehearsalError):
                self.store.get_run(self.run_id)
            with self.assertRaises(RehearsalError):
                self.store.request_stop(self.run_id)
            sidecar.unlink()
        self.assertEqual(self.store.get_run(self.run_id)["status"], "prepared")

    def test_safe_run_file_is_fixed_local_and_does_not_create_files(self):
        self.prepare()
        run_path = self.store.run_path(self.run_id)
        allowed = ("usage.sqlite3", "trade_queue.sqlite3", "library.sqlite3", "library_corpus.json",
                   "profiles/snapshot.json", "profiles/tempest_soul.json", "profiles/tempest_living.json",
                   "memory/tempest.sqlite3", "memory/tempest-tempest-r1-library.json")
        for relative in allowed:
            with self.subTest(relative=relative):
                path = self.store.safe_run_file(self.run_id, relative)
                self.assertEqual(path, run_path / relative)
                self.assertFalse(path.exists())
        for relative in ("../usage.sqlite3", str(run_path / "usage.sqlite3"), "arbitrary.txt",
                         "profiles/unknown_soul.json", "memory/unknown.sqlite3", "memory/tempest-siren-r1-library.json",
                         "memory/tempest-tempest-r49-library.json", "usage.sqlite3-wal", "", None):
            with self.subTest(relative=relative), self.assertRaises(RehearsalError):
                self.store.safe_run_file(self.run_id, relative)

    def test_safe_run_file_rejects_main_parent_and_all_sqlite_sidecar_symlinks(self):
        self.prepare()
        run_path = self.store.run_path(self.run_id)
        target = Path(self.tmp.name) / "outside"
        target.mkdir()
        sentinel = target / "sentinel"
        sentinel.write_text("UNTOUCHED", encoding="utf-8")
        for relative in ("usage.sqlite3", "trade_queue.sqlite3", "library.sqlite3", "memory/tempest.sqlite3"):
            path = run_path / relative
            for suffix in ("", "-journal", "-wal", "-shm"):
                linked = Path(str(path) + suffix)
                linked.symlink_to(sentinel)
                with self.subTest(relative=relative, suffix=suffix), self.assertRaises(RehearsalError):
                    self.store.safe_run_file(self.run_id, relative)
                linked.unlink()
        for dirname, relative in (("profiles", "profiles/tempest_soul.json"), ("memory", "memory/tempest.sqlite3")):
            directory = run_path / dirname
            directory.rmdir()
            directory.symlink_to(target, target_is_directory=True)
            with self.assertRaises(RehearsalError):
                self.store.safe_run_file(self.run_id, relative)
            directory.unlink()
            directory.mkdir(mode=0o700)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "UNTOUCHED")
        self.assertEqual(set(target.iterdir()), {sentinel})

    def test_all_completed_summary_and_completed_run_cannot_restart(self):
        self.begin()
        for index in range(14):
            job = self.claim(index)
            self.store.commit_choice(self.run_id, job["wake_id"], self.token, {"action": "rest"})
            self.store.finish_job(self.run_id, job["wake_id"], self.token)
        summary = self.store.end(self.run_id, self.token)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["request_count"], 0)
        self.assertIsNone(summary["known_cost_usd"])
        self.assertTrue(all(agent["completed"] == 2 for agent in summary["agents"]))
        self.assertEqual(self.store.recover(self.run_id)["status"], "completed")
        self.assertEqual(self.store.request_stop(self.run_id)["status"], "completed")
        with self.assertRaises(RehearsalConflict):
            self.store.begin(self.run_id, resume=True)


if __name__ == "__main__":
    unittest.main()
