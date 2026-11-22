"""The budget counts actual charges, not worst cases (docs/specs/BUDGET_ACTUAL_CHARGES.md).

Only a successful request with a provider-reported charge counts that charge;
everything else keeps its full worst-case set-aside. Private temporary stores,
scripted offline HTTP and a blocked network."""
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from core.runtime.rehearsal.store import RehearsalBudgetExceeded, RehearsalStore
from tests.test_heartbeat import HeartbeatTests, at
from tests.test_rehearsal_store import synthetic_manifest


class CountedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        for name in ("socket", "create_connection", "getaddrinfo"):
            patcher = mock.patch.object(socket, name, side_effect=AssertionError("network forbidden"))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.store = RehearsalStore(Path(temp.name) / "runs")
        self.run_id = self.store.prepare(synthetic_manifest(budget_usd="0.25"))["run_id"]
        self.token = self.store.begin(self.run_id)
        self.jobs = [job for job in self.store.list_jobs(self.run_id)]

    def request(self, index, reserved="0.1", **finish):
        job = self.jobs[index]
        if job["status"] == "pending":
            self.store.claim_job(self.run_id, job["wake_id"], self.token)
            job["status"] = "running"
        request = self.store.reserve_request(self.run_id, job["wake_id"], self.token, agent_id=job["agent_id"],
                                             activity="choice", model=job["requested_model"], input_bytes=100,
                                             max_output_tokens=1024, reserved_usd=reserved)
        if finish:
            self.store.finish_request(self.run_id, request, **finish)
        return request

    def counted(self):
        return self.store.get_run(self.run_id)["counted_usd"]

    def test_a_reported_charge_replaces_the_set_aside(self):
        self.request(0, outcome="success", usage={"provider_cost_usd": "0.004"})
        self.request(1, outcome="success", usage={"provider_cost_usd": "0.006"})
        summary = self.store.get_run(self.run_id)
        self.assertEqual((summary["reserved_usd"], summary["counted_usd"]), ("0.2", "0.01"))
        # Under the old count (0.2 set aside) this 0.1 request would pass the 0.25 budget.
        self.request(2, outcome="success", usage={"provider_cost_usd": "0.001"})
        self.assertEqual(self.counted(), "0.011")

    def test_anything_unconfirmed_counts_in_full(self):
        self.request(0)  # In flight.
        self.request(1, outcome="uncertain")
        self.assertEqual(self.counted(), "0.2")
        with self.assertRaises(RehearsalBudgetExceeded):  # 0.2 held + 0.1 > 0.25.
            self.request(2)

    def test_failures_and_unreported_charges_never_release(self):
        cases = [{"outcome": "http_error", "usage": {"provider_cost_usd": "0"}},  # An error can still be billed.
                 {"outcome": "success"},  # No charge reported.
                 {"outcome": "success", "usage": {"cost_usd": "0.001", "cost_status": "estimated"}}]
        for index, finish in enumerate(cases[:2]):
            self.request(index, **finish)
        self.assertEqual(self.counted(), "0.2")
        with self.assertRaises(RehearsalBudgetExceeded):
            self.request(2, **cases[2])

    def test_an_estimate_counts_in_full_too(self):
        self.request(0, outcome="success", usage={"cost_usd": "0.001", "cost_status": "estimated"})
        self.assertEqual(self.counted(), "0.1")

    def test_a_reported_charge_above_its_set_aside_counts_in_full(self):
        self.request(0, outcome="success", usage={"provider_cost_usd": "0.2"})
        self.assertEqual(self.counted(), "0.2")
        with self.assertRaises(RehearsalBudgetExceeded):
            self.request(1)


class HeartbeatBudgetTests(HeartbeatTests):
    """Reuses the heartbeat harness; only the test below is new here."""

    def prepare_day(self, budget_usd, wakes_per_agent, models=None):
        # Priced like a cheap real model ($1 / $2 per million tokens), so each
        # request sets aside a real worst case.
        from core.runtime.rehearsal.examples import synthetic_catalog
        from core.runtime.rehearsal.provider import catalog_snapshot
        from tests.test_day_runs import day_manifest
        raw = day_manifest(wakes=wakes_per_agent, budget=budget_usd)
        chosen = dict(models or raw["agent_models"])
        raw["agent_models"] = chosen
        raw["catalog_snapshot"] = catalog_snapshot(chosen, synthetic_catalog(chosen))
        return self.store.prepare(raw)["run_id"]

    def test_the_day_keeps_going_while_actual_charges_are_low(self):
        # Scripted replies report a $0 charge (except Oracle's, which reports none).
        # The worst-case set-asides for seven wakes far exceed $0.10, so the old
        # count stopped the day after the first few agents.
        beat = self.heartbeat(daily_budget_usd="0.10")
        woke, run_id = [], None
        for minute in range(0, 14):  # Each agent's own slot, 9:00 to 9:12.
            self.clock = at(9, minute)
            result = beat.tick()
            woke += [w["agent_id"] for w in result.get("wakes", []) if w["status"] == "completed"]
            run_id = result.get("run_id", run_id)
        self.assertEqual(len(woke), 7, woke)
        today = beat.status()["today"]
        run = self.store.get_run(run_id)
        self.assertGreater(float(run["reserved_usd"]), 0.10)  # The old count would have stopped the day.
        self.assertLess(float(today["counted_usd"]), 0.10)
        self.assertNotEqual(beat.status()["reason"], "today's budget is spent")


def load_tests(loader, tests, pattern):
    # Run only this file's own tests, not every inherited heartbeat test again.
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(CountedTests))
    suite.addTest(HeartbeatBudgetTests("test_the_day_keeps_going_while_actual_charges_are_low"))
    return suite


if __name__ == "__main__":
    unittest.main()
