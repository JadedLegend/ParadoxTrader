"""Calls, phase 1 of docs/specs/CALLS_AND_SETTLEMENT.md: write a forecast down,
sealed with the price the agent was shown. Scripted HTTP; the network is blocked."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest

from core.market.window import MarketWindow
from core.runtime.rehearsal.calls import (CALL_OPTIONS, CALLS_FILE, CallRefused, CallStore,
                                          open_calls_line)
from core.runtime.rehearsal.controller import RehearsalController, validate_choice
from core.runtime.rehearsal.examples import ScriptedHTTP, ScriptedResponse
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.home import CARRIED_FILES
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from core.runtime.rehearsal.witness import WitnessStore
from tests.test_day_runs import day_manifest
from tests.test_market_window import KEY_ID, NOW, SECRET, BlockedNetwork, ScriptedData

MARKET = {"status": "ok", "source": "alpaca-iex", "quotes": [
    {"symbol": "SPY", "last": 505.0, "as_of": "2026-11-19T14:58:00+00:00"},
    {"symbol": "QQQ", "last": 441.0},  # No time of its own: unknown, not usable.
]}
CALL = {"action": "call", "symbol": "SPY", "direction": "up", "horizon_days": 5,
        "confidence": "medium", "reason": "Breadth is improving."}


class ChoiceShapeTests(unittest.TestCase):
    def test_a_call_choice_is_strict(self):
        self.assertEqual(validate_choice(json.dumps(CALL))["symbol"], "SPY")
        without_reason = {k: v for k, v in CALL.items() if k != "reason"}
        self.assertEqual(validate_choice(json.dumps(without_reason))["action"], "call")
        for broken in ({**CALL, "horizon_days": 0}, {**CALL, "horizon_days": 21}, {**CALL, "horizon_days": 5.0},
                       {**CALL, "direction": "sideways"}, {**CALL, "confidence": "certain"},
                       {**CALL, "symbol": "spy"}, {**CALL, "reason": "x" * 401}, {**CALL, "size": 10},
                       {k: v for k, v in CALL.items() if k != "symbol"},
                       {"action": "journal", "symbol": "SPY"}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_choice(json.dumps(broken))


class CallStoreTests(BlockedNetwork):
    def setUp(self):
        super().setUp()
        self.calls = CallStore(self.root / CALLS_FILE)

    def record(self, wake="tempest-r1", choice=CALL, market=MARKET, agent="tempest", run="run-a"):
        return self.calls.record(agent_id=agent, run_id=run, wake_id=wake, choice=choice, market=market,
                                 now=NOW)

    def test_a_call_is_sealed_with_the_committed_price_and_its_own_time(self):
        call_id = self.record()
        self.assertEqual(self.record(), call_id)  # A resumed wake records nothing new.
        [call] = self.calls.open_calls("tempest")
        self.assertEqual((call["call_id"], call["entry_price"], call["price_as_of"], call["entry_session"]),
                         (call_id, "505", "2026-11-19T14:58:00+00:00", "2026-11-19"))
        self.assertEqual(self.calls.open_calls("siren"), [])
        line = open_calls_line(self.calls.open_calls("tempest"))
        self.assertIn("SPY up within 5 trading days of 2026-11-19 (medium), sealed at 505", line)
        self.assertEqual(open_calls_line([]), "")

    def test_unknown_prices_and_unwatched_tickers_are_refused(self):
        cases = [({**CALL, "symbol": "TSLA"}, MARKET, "call_symbol_not_watched"),
                 ({**CALL, "symbol": "QQQ"}, MARKET, "call_no_price"),
                 (CALL, {"status": "unavailable"}, "call_no_price"),
                 (CALL, None, "call_no_price")]
        for number, (choice, market, code) in enumerate(cases):
            with self.subTest(code=code), self.assertRaises(CallRefused) as refused:
                self.record(wake=f"tempest-r{number + 1}", choice=choice, market=market)
            self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.calls.open_calls("tempest"), [])

    def test_at_most_five_open_calls_and_the_record_is_append_only(self):
        for number in range(CALL_OPTIONS["max_open_per_agent"]):
            self.record(wake=f"tempest-r{number + 1}")
        with self.assertRaises(CallRefused) as refused:
            self.record(wake="tempest-r6")
        self.assertEqual(refused.exception.code, "call_too_many_open")
        self.record(wake="siren-r1", agent="siren")  # Another agent's cap is its own.
        self.record(wake="weaver-r1", agent="weaver")
        self.record(wake="weaver-r1", agent="weaver", run="run-b")  # The same wake name on another day is new.
        self.assertEqual(len(self.calls.open_calls("weaver")), 2)
        with closing(sqlite3.connect(str(self.root / CALLS_FILE))) as connection:
            for statement in ("UPDATE calls SET entry_price='1'", "DELETE FROM calls"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)

    def test_open_calls_carry_to_the_next_day(self):
        self.assertIn(CALLS_FILE, CARRIED_FILES)


class CallWakeTests(BlockedNetwork):
    def beat(self, *, with_market=True):
        store = RehearsalStore(self.root / "sessions")
        window = MarketWindow(self.root / "market", ["SPY", "QQQ"], lambda: (KEY_ID, SECRET),
                              http_get=ScriptedData(), now=lambda: NOW)
        scripted, prompts, tempest_choices = ScriptedHTTP(), [], []

        def http(url, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in kwargs["json"]["messages"])
            prompts.append(text)
            if "Stable owner ID: tempest" in text and "REHEARSAL CHOICE" in text:
                tempest_choices.append(text)
                if len(tempest_choices) == 1:  # Tempest's first wake makes a call.
                    scripted.calls += 1
                    return ScriptedResponse({"id": "call-1", "model": kwargs["json"].get("model"),
                                             "provider": "scripted-offline",
                                             "choices": [{"message": {"content": json.dumps(CALL)}, "finish_reason": "stop"}],
                                             "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80,
                                                       "cost": "0"}})
            return scripted(url, **kwargs)

        def prepare_day(budget_usd, wakes_per_agent, models=None):
            return store.prepare(day_manifest(wakes=wakes_per_agent, budget=budget_usd))["run_id"]

        def run_wake(run_id, owner, step=None):
            return RehearsalController(store, run_id, transport=OpenRouterTransport("scripted-offline", http_post=http),
                                       market=window.read if with_market else None).run_wake(owner, step=step)

        config = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
                  "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        clock = [datetime(2026, 11, 18, 9, 1, tzinfo=timezone.utc)]  # Tempest only.
        beat = Heartbeat(store, Schedule.from_config(config), prepare_day=prepare_day, run_wake=run_wake,
                         now=lambda: clock[0])
        return store, beat, clock, tempest_choices

    def test_a_call_is_offered_beside_the_window_sealed_and_shown_on_the_next_wake(self):
        store, beat, clock, choices = self.beat()
        result = beat.tick()
        run_id = result["run_id"]
        [job] = [j for j in store.list_jobs(run_id) if j["wake_id"] == "tempest-r1"]
        self.assertEqual((job["status"], job["action"]), ("completed", "call"))
        details = store.get_decision_details(run_id, "tempest-r1")
        self.assertEqual(details["metadata"]["call_options"], CALL_OPTIONS)
        self.assertEqual(len(details["requests"]), 1)  # The choice is the call: no extra request.
        self.assertIn("CALL (offered on this wake)", choices[0])
        self.assertNotIn("Your open calls", choices[0])
        calls = CallStore(store.safe_run_file(run_id, CALLS_FILE)).open_calls("tempest")
        self.assertEqual([(c["symbol"], c["entry_price"]) for c in calls], [("SPY", "505")])
        self.assertEqual(job["record_refs"], [{"kind": "call", "id": calls[0]["call_id"]}])
        [account] = WitnessStore(store.safe_run_file(run_id, "witness.sqlite3")).list_accounts("tempest")["accounts"]
        self.assertIn("Call offered beside the market window on 1 wakes.", account["content"])
        self.assertIn("Recorded menu: rest, journal, inquire, library, roam.", account["content"])
        self.assertNotIn(CALL["reason"], account["content"])  # The witness never sees the reason.

        while len(choices) < 2 and clock[0].minute < 40:  # Tick on to Tempest's next own slot.
            clock[0] += timedelta(minutes=1)
            beat.tick()
        self.assertGreaterEqual(len(choices), 2, "Tempest never reached a second wake")
        self.assertIn("Your open calls (1 of 5", choices[1])
        self.assertIn("SPY up within 5 trading days", choices[1])

    def test_without_a_window_no_call_is_offered_and_one_is_refused(self):
        store, beat, clock, choices = self.beat(with_market=False)
        run_id = beat.tick()["run_id"]
        self.assertNotIn("CALL (offered on this wake)", choices[0])
        [job] = [j for j in store.list_jobs(run_id) if j["wake_id"] == "tempest-r1"]
        self.assertEqual((job["status"], job["failure_code"]), ("failed", "call_not_offered"))
        self.assertFalse(store.safe_run_file(run_id, CALLS_FILE).exists())


if __name__ == "__main__":
    unittest.main()
