"""Calls, phase 3 of docs/specs/CALLS_AND_SETTLEMENT.md: a settled call is handed
back to its agent on its next wakes, then stays only in the record.

Actual temporary stores, scripted offline HTTP; the network is blocked."""
from datetime import datetime, timezone
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.calls import CALLS_FILE, HANDBACK_WAKES, CallStore, call_results_line
from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.heartbeat_view import day_view
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest

NOW = datetime(2026, 11, 28, 15, tzinfo=timezone.utc)
MARKET = {"status": "ok", "quotes": [{"symbol": "GLD", "last": 241.10, "as_of": "2026-11-19T14:58:00+00:00"}]}
CALL = {"action": "call", "symbol": "GLD", "direction": "up", "horizon_days": 5, "confidence": "medium",
        "reason": "Private reasoning that must stay private."}
RIGHT = {"outcome": "right", "exit_session": "2026-11-27", "exit_price": "243", "move_percent": "0.79",
         "spy_move_percent": "0.30"}


class Blocked(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)


class HandBackStoreTests(Blocked):
    def setUp(self):
        super().setUp()
        self.calls = CallStore(Path(self.temp.name) / CALLS_FILE)
        self.call_id = self.calls.record(agent_id="tempest", run_id="run-a", wake_id="tempest-r1", choice=CALL,
                                         market=MARKET, now=NOW)

    def shown(self, sitting, agent="tempest", run="run-b"):
        return [r["call_id"] for r in self.calls.hand_back(agent, run_id=run, sitting=sitting, now=NOW)]

    def test_nothing_is_handed_back_before_settling(self):
        self.assertEqual(self.shown("tempest-r1"), [])

    def test_an_empty_selection_stays_empty_after_a_settlement(self):
        self.assertEqual(self.shown("tempest-r1"), [])
        self.calls.settle(self.call_id, RIGHT, now=NOW)
        self.calls = CallStore(self.calls.path)
        self.assertEqual(self.shown("tempest-r1"), [])
        self.assertEqual(self.shown("tempest-r1", run="run-c"), [self.call_id])
        self.assertEqual(self.shown("tempest-r2", run="run-c"), [self.call_id])
        self.assertEqual(self.shown("tempest-r3", run="run-c"), [])

    def test_first_empty_selection_is_kept_even_if_the_database_did_not_exist(self):
        path = Path(self.temp.name) / "fresh.sqlite3"
        wake = {"run_id": "run-b", "sitting": "tempest-r1", "now": NOW}
        self.assertEqual(CallStore(path).hand_back("tempest", **wake), [])

        calls = CallStore(path)
        call_id = calls.record(agent_id="tempest", run_id="run-a", wake_id="tempest-r1",
                               choice=CALL, market=MARKET, now=NOW)
        calls.settle(call_id, RIGHT, now=NOW)
        self.assertEqual(calls.hand_back("tempest", **wake), [])
        for sitting in ("tempest-r2", "tempest-r3"):
            self.assertEqual([row["call_id"] for row in calls.hand_back(
                "tempest", **{**wake, "sitting": sitting})], [call_id])

    def test_first_five_results_survive_later_settlements_and_other_wakes(self):
        ids = [self.call_id]
        for i in range(2, 8):
            ids.append(self.calls.record(agent_id="tempest", run_id="run-a", wake_id=f"tempest-r{i}",
                                         choice=CALL, market=MARKET, now=NOW))
            self.calls.settle(ids[-2], RIGHT, now=NOW)

        selected = ids[-2:-7:-1]
        self.assertEqual(self.shown("tempest-r1"), selected)
        self.calls.settle(ids[-1], RIGHT, now=NOW)
        self.assertEqual(self.shown("tempest-r1"), selected)
        self.assertEqual(self.shown("tempest-r2"), ids[-1:-6:-1])
        # The oldest result was eligible before but was never shown.
        self.assertEqual(self.shown("tempest-r3"), [ids[-1], ids[1], ids[0]])
        self.assertEqual(self.shown("tempest-r1"), selected)

    def test_a_result_shows_on_two_wakes_then_stays_only_in_the_record(self):
        self.calls.settle(self.call_id, RIGHT, now=NOW)
        self.assertEqual(self.shown("tempest-r1"), [self.call_id])
        self.assertEqual(self.shown("tempest-r1"), [self.call_id])  # Later moves of the same wake see it too.
        self.assertEqual(self.shown("tempest-r5"), [self.call_id])
        self.assertEqual(HANDBACK_WAKES, 2)
        self.assertEqual(self.shown("tempest-r9"), [])
        self.assertEqual(self.shown("tempest-r9", run="run-c"), [])  # A new day does not reset it.
        self.assertEqual(self.calls.settlements()[0]["detail"]["outcome"], "right")  # Still in the record.

    def test_only_the_owner_gets_its_result(self):
        self.calls.settle(self.call_id, RIGHT, now=NOW)
        self.assertEqual(self.shown("siren-r1", agent="siren"), [])

    def test_the_line_states_facts_and_never_the_reason(self):
        self.calls.settle(self.call_id, RIGHT, now=NOW)
        line = call_results_line(self.calls.hand_back("tempest", run_id="run-b", sitting="tempest-r1", now=NOW))
        self.assertIn(f"call {self.call_id}: GLD up within 5 trading days (medium), made 2026-11-19 at 241.1. "
                      "Settled 2026-11-27 at 243: +0.79%, SPY +0.30%. Right.", line)
        self.assertNotIn("Private reasoning", line)
        self.assertEqual(call_results_line([]), "")

    def test_flat_unsettled_and_unknown_spy_read_plainly(self):
        base = {"call_id": 4, "symbol": "GLD", "direction": "down", "horizon_days": 2, "confidence": "low",
                "entry_price": "241.1", "entry_session": "2026-11-19"}
        flat = call_results_line([{**base, "detail": {"outcome": "flat", "exit_session": "2026-11-23",
                                                      "exit_price": "241", "move_percent": "-0.04"}}])
        self.assertIn("-0.04%, SPY unknown. Flat.", flat)
        unsettled = call_results_line([{**base, "detail": {"outcome": "unsettled",
                                                           "reason": "no GLD close for 2026-11-23"}}])
        self.assertIn("Could not be settled: no GLD close for 2026-11-23.", unsettled)

    def test_counts_per_agent_have_no_reason_text(self):
        self.calls.record(agent_id="tempest", run_id="run-a", wake_id="tempest-r2", choice=CALL, market=MARKET,
                          now=NOW)
        self.calls.settle(self.call_id, RIGHT, now=NOW)
        self.assertEqual(self.calls.counts(), {"tempest": {"open": 1, "settled": 1, "right": 1, "wrong": 0,
                                                           "flat": 0, "unsettled": 0}})


class HandBackWakeTests(Blocked):
    """The hand-back reaches the agent's actual choice page, frozen with it."""

    def setUp(self):
        super().setUp()
        self.store = RehearsalStore(Path(self.temp.name) / "sessions")
        self.day = self.store.prepare(day_manifest(wakes=10))["run_id"]
        calls = CallStore(self.store.safe_run_file(self.day, CALLS_FILE))
        self.call_id = calls.record(agent_id="tempest", run_id=self.day, wake_id="tempest-r0", choice=CALL,
                                    market=MARKET, now=NOW)
        calls.settle(self.call_id, RIGHT, now=NOW)
        self.http = ScriptedHTTP()

    def wake(self, owner="tempest", step=None):
        job = RehearsalController(self.store, self.day, transport=OpenRouterTransport(
            "scripted-offline", http_post=self.http)).run_wake(owner, step=step)
        return self.store.get_decision_details(self.day, job["wake_id"])["private_context"].get("call_results", "")

    def test_the_next_two_wakes_see_the_result_and_the_third_does_not(self):
        first, second, third = self.wake(), self.wake(), self.wake()
        self.assertIn(f"call {self.call_id}: GLD up", first)
        self.assertIn("Right.", second)
        self.assertEqual(third, "")
        self.assertEqual(self.wake("siren"), "")

    def test_every_move_of_one_wake_counts_once(self):
        self.assertIn("Right.", self.wake(step=(1, 2)))
        self.assertIn("Right.", self.wake(step=(2, 2)))  # Same wake, second move.
        self.assertIn("Right.", self.wake(step=(1, 2)))  # The second wake.
        self.assertIn("Right.", self.wake(step=(2, 2)))
        self.assertEqual(self.wake(step=(1, 2)), "")  # The third wake: back in the record only.

    def test_later_moves_stay_empty_if_the_calls_file_appears_mid_wake(self):
        day = self.store.prepare(day_manifest(wakes=10))["run_id"]
        self.day = day
        path = self.store.safe_run_file(day, CALLS_FILE)
        self.assertFalse(path.exists())
        self.assertEqual(self.wake(step=(1, 2)), "")
        calls = CallStore(path)
        call_id = calls.record(agent_id="tempest", run_id=day, wake_id="tempest-r0", choice=CALL,
                               market=MARKET, now=NOW)
        calls.settle(call_id, RIGHT, now=NOW)
        self.assertEqual(self.wake(step=(2, 2)), "")
        self.assertIn("Right.", self.wake(step=(1, 2)))


class HeartbeatPageCallsTests(Blocked):
    def test_the_page_shows_counts_per_agent_and_never_a_reason(self):
        store = RehearsalStore(Path(self.temp.name) / "sessions")
        day = store.prepare(day_manifest())["run_id"]
        calls = CallStore(store.safe_run_file(day, CALLS_FILE))
        call_id = calls.record(agent_id="siren", run_id=day, wake_id="siren-r1", choice=CALL, market=MARKET, now=NOW)
        calls.settle(call_id, {**RIGHT, "outcome": "wrong"}, now=NOW)
        config = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
                  "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        beat = Heartbeat(store, Schedule.from_config(config), prepare_day=None, run_wake=None, now=lambda: NOW)
        view = day_view(beat)
        by_agent = {row["agent_id"]: row["calls"] for row in view["agents"]}
        self.assertEqual(by_agent["siren"], {"open": 0, "settled": 1, "right": 0, "wrong": 1, "flat": 0,
                                             "unsettled": 0})
        self.assertEqual(by_agent["tempest"], {"open": 0, "settled": 0, "right": 0, "wrong": 0, "flat": 0,
                                               "unsettled": 0})
        self.assertNotIn("Private reasoning", repr(view))


if __name__ == "__main__":
    unittest.main()
