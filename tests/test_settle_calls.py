"""Calls, phase 2 of docs/specs/CALLS_AND_SETTLEMENT.md: plain code opens the
envelope after the horizon and writes down what really happened.

No model and no network: closing prices come from a scripted reader."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.market.closes import BARS_URL, fetch_closes
from core.runtime.rehearsal.calls import CALLS_FILE, CallStore, settle_call, settle_open_calls
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest

KEY_ID, SECRET = "PKTESTONLY1234", "test-secret-not-real"
# Thursday Nov 19, 2026. Thanksgiving (Nov 26) has no session.
SESSIONS = ["2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27",
            "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]
MARKET = {"status": "ok", "quotes": [{"symbol": "GLD", "last": 241.10, "as_of": "2026-11-19T14:58:00+00:00"}]}
CALL = {"action": "call", "symbol": "GLD", "direction": "up", "horizon_days": 5, "confidence": "medium",
        "reason": "Private reasoning that must never reach the heartbeat page."}


def open_call(direction="up", horizon=5, entry="241.10", session="2026-11-19", symbol="GLD"):
    return {"call_id": 1, "agent_id": "tempest", "symbol": symbol, "direction": direction,
            "horizon_days": horizon, "entry_price": entry, "entry_session": session}


def closes(gld, spy=None):
    return {"GLD": {s: Decimal(str(p)) for s, p in gld.items()},
            "SPY": {s: Decimal(str(p)) for s, p in (spy or {}).items()}}


class SettleOneCallTests(unittest.TestCase):
    def test_right_counts_trading_days_past_a_holiday_and_beside_spy(self):
        state, detail = settle_call(open_call(), closes({"2026-11-27": 243.00}, {"2026-11-19": 500, "2026-11-27": 501.5}),
                                    SESSIONS, "2026-12-04")
        self.assertEqual(state, "settled")
        self.assertEqual(detail, {"outcome": "right", "exit_session": "2026-11-27", "exit_price": "243",
                                  "move_percent": "0.79", "spy_move_percent": "0.30"})

    def test_wrong_and_down_calls(self):
        self.assertEqual(settle_call(open_call(), closes({"2026-11-27": 238}), SESSIONS, "2026-12-04")[1]["outcome"],
                         "wrong")
        self.assertEqual(settle_call(open_call("down"), closes({"2026-11-27": 238}), SESSIONS,
                                     "2026-12-04")[1]["outcome"], "right")

    def test_a_tiny_move_is_flat_not_right_or_wrong(self):
        detail = settle_call(open_call(), closes({"2026-11-27": 241.20}), SESSIONS, "2026-12-04")[1]
        self.assertEqual((detail["outcome"], detail["move_percent"]), ("flat", "0.04"))

    def test_missing_spy_is_left_out_not_zero(self):
        detail = settle_call(open_call(), closes({"2026-11-27": 243}), SESSIONS, "2026-12-04")[1]
        self.assertNotIn("spy_move_percent", detail)

    def test_not_due_until_the_horizon_has_passed(self):
        self.assertEqual(settle_call(open_call(), closes({}), SESSIONS[:5], "2026-11-25"), ("open", None))

    def test_a_weekend_entry_counts_from_the_next_session(self):
        call = open_call(horizon=1, session="2026-11-21")  # Saturday: the call was made on Friday's price.
        self.assertEqual(settle_call(call, closes({"2026-11-23": 245}), SESSIONS, "2026-12-04")[1]["exit_session"],
                         "2026-11-23")

    def test_a_missing_close_waits_then_becomes_unsettled(self):
        state, reason = settle_call(open_call(), closes({}), SESSIONS[:7], "2026-11-30")
        self.assertEqual((state, reason), ("pending", "no GLD close for 2026-11-27"))
        state, detail = settle_call(open_call(), closes({}), SESSIONS, "2026-12-04")  # Five sessions later.
        self.assertEqual((state, detail["outcome"]), ("settled", "unsettled"))
        self.assertNotIn("move_percent", detail)

    def test_no_market_data_at_all_waits_on_weekdays_then_ends(self):
        self.assertEqual(settle_call(open_call(), None, [], "2026-11-24"), ("open", None))
        self.assertEqual(settle_call(open_call(), None, [], "2026-11-27"), ("pending", "market data unavailable"))
        state, detail = settle_call(open_call(), None, [], "2026-12-10")
        self.assertEqual((state, detail["outcome"]), ("settled", "unsettled"))


class SettleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = CallStore(Path(self.temp.name) / CALLS_FILE)
        self.call_id = self.calls.record(agent_id="tempest", run_id="run-a", wake_id="tempest-r1", choice=CALL,
                                         market=MARKET, now=datetime(2026, 11, 19, 15, tzinfo=timezone.utc))
        self.fetched = []

    def fetch(self, symbols, start, end):
        self.fetched.append((tuple(symbols), start, end))
        return {"status": "ok", "closes": closes({s: 243 for s in SESSIONS}, {s: 500 for s in SESSIONS})}

    def settle(self, today="2026-12-04"):
        return settle_open_calls(self.calls, self.fetch, now=datetime(2026, 12, 4, 22, tzinfo=timezone.utc),
                                 today=today, completed=lambda s: s < today)

    def test_settling_writes_one_row_and_twice_is_a_no_op(self):
        self.assertEqual(self.settle(), {"open": 0, "settled": 1, "pending": []})
        self.assertEqual(self.fetched, [(("GLD", "SPY"), "2026-11-19", "2026-12-04")])
        self.assertEqual(self.calls.open_calls("tempest"), [])  # It leaves the agent's open list.
        [row] = self.calls.settlements()
        self.assertEqual((row["call_id"], row["detail"]["outcome"]), (self.call_id, "right"))
        self.assertEqual(self.settle(), {"open": 0, "settled": 0, "pending": []})
        self.assertFalse(self.calls.settle(self.call_id, {"outcome": "wrong"}, now=datetime.now(timezone.utc)))
        self.assertEqual(self.calls.settlements()[0]["detail"]["outcome"], "right")  # Append-only.

    def test_a_session_still_trading_is_never_used(self):
        # Today is the fifth session but has not closed: the call stays open.
        summary = settle_open_calls(self.calls, self.fetch, now=datetime(2026, 11, 27, 17, tzinfo=timezone.utc),
                                    today="2026-11-27", completed=lambda s: s < "2026-11-27")
        self.assertEqual(summary, {"open": 1, "settled": 0, "pending": []})

    def test_unavailable_data_keeps_the_call_open_with_a_reason(self):
        summary = settle_open_calls(self.calls, lambda *a: {"status": "unavailable", "reason": "market data answered 500"},
                                    now=datetime(2026, 11, 30, 22, tzinfo=timezone.utc), today="2026-11-30",
                                    completed=lambda s: True)
        self.assertEqual(summary, {"open": 1, "settled": 0, "pending": ["tempest call 1: market data unavailable"],
                                   "unavailable": "market data answered 500"})


class Reply:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class FetchClosesTests(unittest.TestCase):
    def test_bars_become_eastern_sessions_across_pages(self):
        pages = [{"bars": {"GLD": [{"t": "2026-11-20T05:00:00Z", "c": 242.5}, {"t": "bad", "c": 1}],
                           "XYZ": [{"t": "2026-11-20T05:00:00Z", "c": 9}]}, "next_page_token": "p2"},
                 {"bars": {"GLD": [{"t": "2026-11-23T05:00:00Z", "c": "243.1"}, {"t": "2026-11-24T05:00:00Z", "c": 0}]},
                  "next_page_token": None}]
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs["params"].get("page_token"), kwargs["params"]["feed"]))
            return Reply(200, pages[len(calls) - 1])

        record = fetch_closes(["GLD", "SPY"], "2026-11-19", "2026-11-24", KEY_ID, SECRET, http_get=http_get)
        self.assertEqual(record, {"status": "ok", "closes": {"GLD": {"2026-11-20": Decimal("242.5"),
                                                                     "2026-11-23": Decimal("243.1")}}})
        self.assertEqual(calls, [(BARS_URL, None, "iex"), (BARS_URL, "p2", "iex")])

    def test_trouble_is_unavailable_never_raised(self):
        def broken(url, **kwargs):
            raise OSError("down")

        self.assertEqual(fetch_closes(["GLD"], "a", "b", KEY_ID, SECRET, http_get=broken)["status"], "unavailable")
        self.assertEqual(fetch_closes(["GLD"], "a", "b", KEY_ID, SECRET, http_get=lambda u, **k: Reply(403, {})),
                         {"status": "unavailable", "reason": "market data answered 403"})
        self.assertEqual(fetch_closes(["GLD"], "a", "b", "not-a-paper-key", SECRET, http_get=broken)["reason"],
                         "no Alpaca paper key is saved")


CONFIG = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
          "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}


class HeartbeatSettleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.store = RehearsalStore(Path(self.temp.name) / "sessions")
        self.run_id = self.store.prepare(day_manifest())["run_id"]
        CallStore(self.store.safe_run_file(self.run_id, CALLS_FILE)).record(
            agent_id="tempest", run_id=self.run_id, wake_id="tempest-r1", choice=CALL, market=MARKET,
            now=datetime(2026, 11, 19, 15, tzinfo=timezone.utc))
        self.clock = datetime(2026, 11, 27, 22, 0, tzinfo=timezone.utc)  # 17:00 Eastern, after the close.
        self.answer = {"status": "ok", "closes": closes({s: 243 for s in SESSIONS[:6]}, {})}
        self.reads = 0

    def fetch(self, symbols, start, end):
        self.reads += 1
        return self.answer

    def heartbeat(self, fetch="default"):
        return Heartbeat(self.store, Schedule.from_config(CONFIG), prepare_day=None, run_wake=None,
                         now=lambda: self.clock, fetch_closes=self.fetch if fetch == "default" else fetch)

    def calls(self):
        return CallStore(self.store.safe_run_file(self.run_id, CALLS_FILE))

    def test_a_tick_after_the_close_settles_the_due_call_without_any_wake(self):
        result = self.heartbeat().tick()
        self.assertEqual(result["calls"], {"open": 0, "settled": 1, "pending": []})
        self.assertEqual(self.calls().settlements()[0]["detail"]["exit_session"], "2026-11-27")
        self.assertIsNone(self.heartbeat().tick().get("calls"))  # Nothing open: no more market reads.
        self.assertEqual(self.reads, 1)

    def test_before_the_close_today_is_not_used(self):
        self.clock = datetime(2026, 11, 27, 19, 0, tzinfo=timezone.utc)  # 14:00 Eastern.
        self.assertEqual(self.heartbeat().tick()["calls"], {"open": 1, "settled": 0, "pending": []})

    def test_reads_at_most_every_thirty_minutes_and_shows_problems_without_reasons(self):
        self.answer = {"status": "unavailable", "reason": "market data answered 500"}
        beat = self.heartbeat()
        beat.tick()
        self.clock = self.clock.replace(minute=20)
        beat.tick()
        self.assertEqual(self.reads, 1)
        notes = [p["note"] for p in beat.status()["problems"]]
        self.assertTrue(any("market data answered 500" in note for note in notes))
        self.assertFalse(any("Private reasoning" in note for note in notes))
        self.clock = self.clock.replace(minute=31)
        self.answer = {"status": "ok", "closes": closes({s: 243 for s in SESSIONS[:6]}, {})}
        self.assertEqual(beat.tick()["calls"]["settled"], 1)
        self.assertEqual(self.reads, 2)

    def test_a_broken_reader_never_fails_the_tick(self):
        def broken(*args):
            raise RuntimeError("boom")

        result = self.heartbeat(fetch=broken).tick()
        self.assertEqual(result["outcome"], "quiet")
        self.assertEqual(result["calls"]["error"], "RuntimeError")

    def test_without_a_reader_nothing_settles_and_ticks_look_the_same(self):
        self.assertNotIn("calls", self.heartbeat(fetch=None).tick())


if __name__ == "__main__":
    unittest.main()
