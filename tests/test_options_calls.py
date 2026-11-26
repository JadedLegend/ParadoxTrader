"""Options and volatility calls, Phase 1 of docs/specs/OPTIONS_CALLS.md.

Scripted offline data and controller tests; the network is blocked."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.market.options import options_evidence
from core.runtime.rehearsal.calls import (
    CALL_OPTIONS, CALLS_FILE, CallRefused, CallStore,
    call_results_line, open_calls_line, settle_open_calls, settle_option_call, settle_vol_call,
)
from core.runtime.rehearsal.controller import RehearsalController, validate_choice
from core.runtime.rehearsal.examples import ScriptedHTTP, ScriptedResponse
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from scripts.evaluate_calls import main as evaluate_main, resolve_calls_db, summarize_calls
from tests.test_rehearsal_provider import manifest

OPEN = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)  # Thursday 10:00 ET.
MARKET = {"status": "ok", "source": "alpaca-iex", "quotes": [
    {"symbol": "SPY", "last": 593.50, "as_of": "2026-11-19T14:58:00+00:00"},
]}


def options_snapshot(*, status="open", symbol="SPY", expiry="2026-11-27", iv=0.142,
                     stale=False, quote_time="2026-11-19T14:59:30+00:00"):
    contracts = []
    for option_type, strike in (("call", 593.0), ("put", 593.0), ("call", 596.0), ("put", 590.0)):
        item = {
            "symbol": f"{symbol}{expiry[2:].replace('-', '')}{'C' if option_type == 'call' else 'P'}{int(strike * 1000):08d}",
            "type": option_type,
            "strike": strike,
            "expiration": expiry,
            "bid": 2.10,
            "ask": 2.18,
            "stale": stale,
        }
        if quote_time is not None:
            item["quote_time"] = quote_time
        if iv is not None:
            item["iv"] = iv
        contracts.append(item)
    return {
        "status": status,
        "symbol": symbol,
        "feed": "indicative",
        "source": "alpaca-options",
        "checked_at": "2026-11-19T15:00:00+00:00",
        "underlying_price": 593.50,
        "contracts": contracts,
    }


VOL_CALL = {
    "action": "call",
    "kind": "vol",
    "symbol": "SPY",
    "expiry": "2026-11-27",
    "iv_view": "high",
    "confidence": "medium",
    "reason": "Implied move looks stretched into a holiday week.",
}
STOCK_CALL = {
    "action": "call",
    "symbol": "SPY",
    "direction": "up",
    "horizon_days": 5,
    "confidence": "medium",
    "reason": "Breadth improving.",
}
OPTION_CALL = {
    "action": "call",
    "kind": "option",
    "symbol": "SPY",
    "expiry": "2026-11-27",
    "option_type": "call",
    "strike": 593,
    "confidence": "medium",
    "reason": "Near-money call looks underpriced for an upside break.",
}


def day_cfg(wakes=6, budget="5.00"):
    raw = manifest()
    raw["kind"] = "day"
    raw["limits"]["wakes_per_agent"] = wakes
    raw["limits"]["max_requests"] = 2 * wakes * 7
    raw["limits"]["budget_usd"] = budget
    return raw


class Blocked(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)


class VolCallShapeTests(unittest.TestCase):
    def test_vol_call_shape_and_field_isolation(self):
        parsed = validate_choice(json.dumps(VOL_CALL))
        self.assertEqual((parsed["kind"], parsed["iv_view"]), ("vol", "high"))
        without_reason = {k: v for k, v in VOL_CALL.items() if k != "reason"}
        self.assertEqual(validate_choice(json.dumps(without_reason))["action"], "call")
        self.assertEqual(validate_choice(json.dumps(STOCK_CALL))["direction"], "up")

        for broken in (
            {**VOL_CALL, "kind": "calendar"},
            {**VOL_CALL, "iv_view": "flat"},
            {**VOL_CALL, "expiry": "11-27-2026"},
            {**VOL_CALL, "expiry": "not-a-date"},
            {**VOL_CALL, "direction": "up"},
            {**VOL_CALL, "horizon_days": 5},
            {**STOCK_CALL, "expiry": "2026-11-27"},
            {**STOCK_CALL, "iv_view": "high"},
            {k: v for k, v in VOL_CALL.items() if k != "expiry"},
        ):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_choice(json.dumps(broken))


class VolCallStoreTests(Blocked):
    def setUp(self):
        super().setUp()
        self.calls = CallStore(self.root / CALLS_FILE)

    def test_dashboard_and_settlement_reads_preserve_stock_only_schema(self):
        self.calls.record(agent_id="tempest", run_id="old", wake_id="tempest-r1",
                          choice=STOCK_CALL, market=MARKET, now=OPEN)
        path = self.root / CALLS_FILE
        with closing(sqlite3.connect(path)) as db:
            for prefix in ("vol", "option"):
                for suffix in ("handbacks", "settlements", "calls"):
                    db.execute(f"DROP TABLE IF EXISTS {prefix}_{suffix}")
            db.commit()
        before = path.read_bytes()
        self.assertEqual(self.calls.counts()["tempest"]["open"], 1)
        self.assertEqual(len(self.calls.open_calls("tempest")), 1)
        self.assertEqual(len(self.calls.all_open()), 1)
        self.assertEqual(self.calls.open_vol_calls("tempest"), [])
        self.assertEqual(self.calls.all_open_vol(), [])
        self.assertEqual(self.calls.vol_settlements(), [])
        self.assertEqual(self.calls.open_option_calls("tempest"), [])
        self.assertEqual(self.calls.all_open_option(), [])
        self.assertEqual(self.calls.option_settlements(), [])
        self.assertTrue(path.read_bytes() == before, "read operations changed the calls database")
        self.calls.record(agent_id="tempest", run_id="new", wake_id="tempest-r1",
                          choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN)
        self.assertEqual(self.calls.counts()["tempest"]["open"], 2)

    def test_seals_atm_iv_implied_move_and_shared_cap(self):
        call_id = self.calls.record(
            agent_id="tempest", run_id="run-a", wake_id="tempest-r1",
            choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
        )
        self.assertEqual(
            self.calls.record(
                agent_id="tempest", run_id="run-a", wake_id="tempest-r1",
                choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
            ),
            call_id,
        )
        [row] = self.calls.open_vol_calls("tempest")
        self.assertEqual(row["call_id"], call_id)
        self.assertEqual(row["entry_iv"], "0.142")
        self.assertEqual(row["trading_days"], 5)  # Excludes Thanksgiving; includes Friday's early close.
        self.assertEqual(row["implied_move_pct"], "2.00")
        self.assertEqual(row["atm_strike"], "593")
        self.assertEqual(row["entry_session"], "2026-11-19")
        line = open_calls_line([], [row])
        self.assertIn("vol call", line)
        self.assertIn("SPY 2026-11-27 IV high (priced +/-2.00%, medium)", line)

        # Shared cap of 5 across stock and vol calls.
        for idx in range(2, CALL_OPTIONS["max_open_per_agent"] + 1):
            stock_id = self.calls.record(
                agent_id="tempest", run_id="run-a", wake_id=f"tempest-r{idx}",
                choice=STOCK_CALL, market=MARKET, now=OPEN,
            )
            self.assertNotEqual(stock_id, call_id)
        with self.assertRaises(CallRefused) as refused:
            self.calls.record(
                agent_id="tempest", run_id="run-a", wake_id="tempest-r6",
                choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
            )
        self.assertEqual(refused.exception.code, "call_too_many_open")

        with closing(sqlite3.connect(str(self.root / CALLS_FILE))) as conn:
            for stmt in ("UPDATE vol_calls SET entry_iv='0.5'", "DELETE FROM vol_calls"):
                with self.subTest(stmt=stmt), self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(stmt)

    def test_vol_refusals(self):
        cases = [
            (VOL_CALL, MARKET, None, "call_options_unavailable"),
            (VOL_CALL, MARKET, options_snapshot(status="closed"), "call_options_unavailable"),
            (VOL_CALL, MARKET, options_snapshot(symbol="QQQ"), "call_contract_not_shown"),
            ({**VOL_CALL, "expiry": "2026-12-04"}, MARKET, options_snapshot(), "call_contract_not_shown"),
            (VOL_CALL, MARKET, options_snapshot(stale=True), "call_options_stale"),
            (VOL_CALL, MARKET, options_snapshot(quote_time=None), "call_options_stale"),
            (VOL_CALL, MARKET, options_snapshot(iv=None), "call_no_iv"),
            ({**VOL_CALL, "expiry": "2026-11-20"}, MARKET, options_snapshot(expiry="2026-11-20"), "call_horizon_too_short"),
        ]
        for idx, (choice, market, opts, expected) in enumerate(cases, start=1):
            with self.subTest(expected=expected), self.assertRaises(CallRefused) as refused:
                self.calls.record(
                    agent_id="siren", run_id="run-a", wake_id=f"siren-r{idx}",
                    choice=choice, market=market, options=opts, now=OPEN,
                )
            self.assertEqual(refused.exception.code, expected)


class VolSettleTests(Blocked):
    SESSIONS = ["2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25",
                "2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]

    @staticmethod
    def _vol(iv_view="high", implied="2.19", entry="500"):
        return {
            "call_id": 1, "agent_id": "tempest", "symbol": "SPY", "expiry": "2026-11-27",
            "iv_view": iv_view, "entry_price": entry, "entry_iv": "0.142",
            "implied_move_pct": implied, "entry_session": "2026-11-19",
        }

    @staticmethod
    def _closes(spy_prices):
        return {"SPY": {s: Decimal(str(p)) for s, p in spy_prices.items()}}

    def test_settle_vol_right_wrong_flat_and_unsettled(self):
        # 500 -> 504 is +0.80%, well below 2.19% implied: iv_view="high" is right, "low" is wrong.
        c = self._closes({"2026-11-19": 500, "2026-11-27": 504})
        state, detail = settle_vol_call(self._vol("high"), c, self.SESSIONS, "2026-12-04")
        self.assertEqual(state, "settled")
        self.assertEqual((detail["kind"], detail["outcome"], detail["actual_move_percent"], detail["spy_move_percent"]),
                         ("vol", "right", "0.80", "0.80"))
        self.assertEqual(settle_vol_call(self._vol("low"), c, self.SESSIONS, "2026-12-04")[1]["outcome"], "wrong")

        # 500 -> 510.50 is +2.10%, within +/-0.25% of 2.19% -> flat.
        c_flat = self._closes({"2026-11-19": 500, "2026-11-27": 510.50})
        self.assertEqual(settle_vol_call(self._vol("high"), c_flat, self.SESSIONS, "2026-12-04")[1]["outcome"], "flat")

        # 500 -> 482 is -3.60%, actual 3.60% > 2.19% -> iv_view="low" is right.
        c_big = self._closes({"2026-11-19": 500, "2026-11-27": 482})
        self.assertEqual(settle_vol_call(self._vol("low"), c_big, self.SESSIONS, "2026-12-04")[1]["outcome"], "right")

        # Open before expiry closes; pending then unsettled if close missing.
        self.assertEqual(settle_vol_call(self._vol(), self._closes({}), self.SESSIONS[:5], "2026-11-27"), ("open", None))
        self.assertEqual(settle_vol_call(self._vol(), self._closes({}), self.SESSIONS[:7], "2026-11-30")[0], "pending")
        self.assertEqual(settle_vol_call(self._vol(), self._closes({}), self.SESSIONS, "2026-12-04")[1]["outcome"], "unsettled")

    def test_heartbeat_and_counts_settle_vol_only_calls(self):
        store = RehearsalStore(self.root / "sessions")
        run_id = store.prepare(day_cfg())["run_id"]
        calls = CallStore(store.safe_run_file(run_id, CALLS_FILE))
        calls.record(agent_id="tempest", run_id=run_id, wake_id="tempest-r1",
                     choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN)
        self.assertEqual(calls.counts()["tempest"],
                         {"open": 1, "settled": 0, "right": 0, "wrong": 0, "flat": 0, "unsettled": 0})
        self.assertTrue(calls.has_open())

        cfg = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
               "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        clock = datetime(2026, 11, 27, 22, 0, tzinfo=timezone.utc)
        beat = Heartbeat(
            store, Schedule.from_config(cfg), prepare_day=None, run_wake=None,
            now=lambda: clock,
            fetch_closes=lambda syms, start, end: {
                "status": "ok",
                "closes": self._closes({s: 595 if s == "2026-11-27" else 593.5 for s in self.SESSIONS[:6]}),
            },
        )
        result = beat.tick()
        self.assertEqual(result["calls"], {"open": 0, "settled": 1, "pending": []})
        self.assertEqual(calls.counts()["tempest"],
                         {"open": 0, "settled": 1, "right": 1, "wrong": 0, "flat": 0, "unsettled": 0})
        self.assertFalse(calls.has_open())


class VolControllerTests(Blocked):
    def test_recomputes_cached_freshness_once_and_reuses_it_on_recovery(self):
        for minutes_after_fetch, stale in ((10, False), (25, True)):
            with self.subTest(stale=stale):
                store = RehearsalStore(self.root / f"sessions-{minutes_after_fetch}")
                run_id = store.prepare(day_cfg())["run_id"]
                snapshot = options_snapshot(quote_time=(OPEN - timedelta(minutes=15)).isoformat())
                transport = OpenRouterTransport("scripted-offline", http_post=ScriptedHTTP())
                controller = RehearsalController(store, run_id, transport=transport,
                                                 market=lambda: MARKET, options=lambda: snapshot)
                controller._now = lambda: OPEN + timedelta(minutes=minutes_after_fetch)
                controller.prepare_profiles()
                store.add_wake(run_id, "tempest")
                controller._token = store.begin(run_id)
                job = store.claim_job(run_id, "tempest-r1", controller._token)
                first = controller._decision_details(job, new_picker=True)
                self.assertTrue(all(row["stale"] == stale
                                    for row in first["private_context"]["options_snapshot"]["contracts"]))
                self.assertTrue(all(not row["stale"] for row in snapshot["contracts"]))

                store.recover(run_id)
                resumed = RehearsalController(store, run_id, transport=transport)
                resumed._now = lambda: OPEN + timedelta(hours=2)
                resumed._token = store.begin(run_id, resume=True)
                job = store.claim_job(run_id, "tempest-r1", resumed._token)
                details = resumed._decision_details(job, new_picker=True)
                self.assertEqual(details["private_context"], first["private_context"])
                if stale:
                    with self.assertRaises(CallRefused) as refused:
                        resumed._call(job, VOL_CALL, details)
                    self.assertEqual(refused.exception.code, "call_options_stale")
                else:
                    self.assertEqual(resumed._call(job, VOL_CALL, details), [{"kind": "call", "id": 1}])

    def test_legacy_inquiry_evidence_cannot_seal_an_options_call(self):
        store = RehearsalStore(self.root / "sessions")
        run_id = store.prepare(day_cfg())["run_id"]
        controller = RehearsalController(
            store, run_id, transport=OpenRouterTransport("scripted-offline", http_post=ScriptedHTTP()),
        )
        details = {
            "metadata": {"call_options": CALL_OPTIONS},
            "private_context": {
                "market": MARKET,
                "options": options_evidence(options_snapshot(stale=True)),
            },
        }
        for index, choice in enumerate((VOL_CALL, OPTION_CALL), 1):
            job = {"agent_id": "tempest", "wake_id": f"tempest-r{index}"}
            with self.subTest(kind=choice["kind"]), self.assertRaisesRegex(CallRefused, "call_options_unavailable"):
                controller._call(job, choice, details)
        self.assertFalse(CallStore(store.safe_run_file(run_id, CALLS_FILE)).has_open())

    def test_controller_wake_offers_and_records_vol_call(self):
        store = RehearsalStore(self.root / "sessions")
        run_id = store.prepare(day_cfg())["run_id"]
        scripted, prompts = ScriptedHTTP(), []

        def http(url, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in kwargs["json"]["messages"])
            prompts.append(text)
            if "Stable owner ID: tempest" in text and "REHEARSAL CHOICE" in text:
                if len(prompts) == 1:
                    scripted.calls += 1
                    return ScriptedResponse({
                        "id": "vol-1", "model": kwargs["json"].get("model"), "provider": "scripted-offline",
                        "choices": [{"message": {"content": json.dumps(VOL_CALL)}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80, "cost": "0"},
                    })
            return scripted(url, **kwargs)

        controller = RehearsalController(
            store, run_id, transport=OpenRouterTransport("scripted-offline", http_post=http),
            market=lambda: MARKET, options=lambda: options_snapshot(), now=lambda: OPEN,
        )
        job = controller.run_wake("tempest")
        self.assertEqual((job["status"], job["action"]), ("completed", "call"))
        self.assertIn("VOLATILITY CALL", prompts[0])
        self.assertIn("Options expiries: 2026-11-27.", prompts[0])
        calls = CallStore(store.safe_run_file(run_id, CALLS_FILE)).open_vol_calls("tempest")
        self.assertEqual(len(calls), 1)
        self.assertEqual(job["record_refs"], [{"kind": "call", "id": calls[0]["call_id"]}])

        # Second wake shows the open vol call in context.
        controller.run_wake("tempest")
        self.assertIn("vol call 1: SPY 2026-11-27 IV high", prompts[1])


class OptionCallShapeAndStoreTests(Blocked):
    def setUp(self):
        super().setUp()
        self.calls = CallStore(self.root / CALLS_FILE)

    def test_option_call_shape_validation(self):
        parsed = validate_choice(json.dumps(OPTION_CALL))
        self.assertEqual((parsed["kind"], parsed["option_type"], parsed["strike"]), ("option", "call", 593))
        for broken in (
            {**OPTION_CALL, "option_type": "straddle"},
            {**OPTION_CALL, "strike": 0},
            {**OPTION_CALL, "strike": -5},
            {**OPTION_CALL, "strike": True},
            {**OPTION_CALL, "strike": "593"},
            {**OPTION_CALL, "direction": "up"},
            {**OPTION_CALL, "iv_view": "high"},
            {k: v for k, v in OPTION_CALL.items() if k != "strike"},
        ):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_choice(json.dumps(broken))

    def test_seals_at_ask_and_shares_open_cap(self):
        call_id = self.calls.record(
            agent_id="alchemist", run_id="run-a", wake_id="alchemist-r1",
            choice=OPTION_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
        )
        self.assertEqual(
            self.calls.record(
                agent_id="alchemist", run_id="run-a", wake_id="alchemist-r1",
                choice=OPTION_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
            ),
            call_id,
        )
        [row] = self.calls.open_option_calls("alchemist")
        self.assertEqual(row["contract"], "SPY261127C00593000")
        self.assertEqual((row["entry_bid"], row["entry_ask"], row["spread_pct"]), ("2.1", "2.18", "3.67"))
        self.assertEqual(row["entry_underlying_price"], "593.5")
        line = open_calls_line([], [], [row])
        self.assertIn("option call 1: long SPY 2026-11-27 593 call at 2.18 ask (spread 3.67%, medium)", line)

        # Shared cap of 5 across stock, vol, and option calls.
        self.calls.record(agent_id="alchemist", run_id="run-a", wake_id="alchemist-r2",
                          choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN)
        for idx in range(3, CALL_OPTIONS["max_open_per_agent"] + 1):
            self.calls.record(agent_id="alchemist", run_id="run-a", wake_id=f"alchemist-r{idx}",
                              choice=STOCK_CALL, market=MARKET, now=OPEN)
        with self.assertRaises(CallRefused) as refused:
            self.calls.record(agent_id="alchemist", run_id="run-a", wake_id="alchemist-r6",
                              choice=OPTION_CALL, market=MARKET, options=options_snapshot(), now=OPEN)
        self.assertEqual(refused.exception.code, "call_too_many_open")

        with closing(sqlite3.connect(str(self.root / CALLS_FILE))) as conn:
            for stmt in ("UPDATE option_calls SET entry_ask='1'", "DELETE FROM option_calls"):
                with self.subTest(stmt=stmt), self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(stmt)

    def test_option_refusals(self):
        bad_quote = options_snapshot()
        bad_quote["contracts"][0]["ask"] = 0
        cases = [
            (OPTION_CALL, MARKET, None, "call_options_unavailable"),
            (OPTION_CALL, MARKET, options_snapshot(status="closed"), "call_options_unavailable"),
            ({**OPTION_CALL, "strike": 999}, MARKET, options_snapshot(), "call_contract_not_shown"),
            (OPTION_CALL, MARKET, options_snapshot(stale=True), "call_options_stale"),
            (OPTION_CALL, MARKET, bad_quote, "call_bad_option_quote"),
            ({**OPTION_CALL, "expiry": "2026-11-19"}, MARKET, options_snapshot(expiry="2026-11-19"), "call_horizon_too_short"),
        ]
        for idx, (choice, market, opts, expected) in enumerate(cases, start=1):
            with self.subTest(expected=expected), self.assertRaises(CallRefused) as refused:
                self.calls.record(
                    agent_id="siren", run_id="run-a", wake_id=f"siren-r{idx}",
                    choice=choice, market=market, options=opts, now=OPEN,
                )
            self.assertEqual(refused.exception.code, expected)


class OptionSettleAndControllerTests(Blocked):
    SESSIONS = ["2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25",
                "2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]

    @staticmethod
    def _opt(option_type="call", strike="593", ask="2.18"):
        return {
            "call_id": 1, "agent_id": "alchemist", "contract": "SPY261127C00593000",
            "symbol": "SPY", "expiry": "2026-11-27", "option_type": option_type,
            "strike": strike, "entry_ask": ask, "spread_pct": "3.67",
            "entry_underlying_price": "593.5", "entry_session": "2026-11-19",
        }

    @staticmethod
    def _closes(spy_prices):
        return {"SPY": {s: Decimal(str(p)) for s, p in spy_prices.items()}}

    def test_settle_option_itm_win_itm_net_loss_otm_loss_and_put(self):
        # ITM profit: SPY closes at 598 -> intrinsic 5.00 - 2.18 ask = +2.82 (+129.36%) -> right.
        state, detail = settle_option_call(
            self._opt(), self._closes({"2026-11-19": 593.5, "2026-11-27": 598}),
            self.SESSIONS, "2026-12-04",
        )
        self.assertEqual(state, "settled")
        self.assertEqual((detail["kind"], detail["outcome"], detail["intrinsic"], detail["net_pnl"], detail["return_percent"]),
                         ("option", "right", "5", "2.82", "129.36"))

        # Direction right (594 > 593.5) and ITM (intrinsic 1.00), but ask was 2.18 -> net -1.18 -> wrong!
        state, loss_detail = settle_option_call(
            self._opt(), self._closes({"2026-11-19": 593.5, "2026-11-27": 594}),
            self.SESSIONS, "2026-12-04",
        )
        self.assertEqual((loss_detail["outcome"], loss_detail["intrinsic"], loss_detail["net_pnl"],
                          loss_detail["underlying_move_percent"]),
                         ("wrong", "1", "-1.18", "0.08"))

        # OTM total loss (-100%).
        otm = settle_option_call(self._opt(), self._closes({"2026-11-19": 593.5, "2026-11-27": 590}),
                                 self.SESSIONS, "2026-12-04")[1]
        self.assertEqual((otm["outcome"], otm["intrinsic"], otm["return_percent"]), ("wrong", "0", "-100.00"))

        # Put ITM win: strike 593, close 588 -> intrinsic 5.00 - 2.18 = +2.82 -> right.
        put = settle_option_call(self._opt(option_type="put"), self._closes({"2026-11-19": 593.5, "2026-11-27": 588}),
                                 self.SESSIONS, "2026-12-04")[1]
        self.assertEqual((put["outcome"], put["net_pnl"]), ("right", "2.82"))

        # Missing close -> pending -> unsettled.
        self.assertEqual(settle_option_call(self._opt(), self._closes({}), self.SESSIONS[:7], "2026-11-30")[0], "pending")
        self.assertEqual(settle_option_call(self._opt(), self._closes({}), self.SESSIONS, "2026-12-04")[1]["outcome"],
                         "unsettled")

    def test_heartbeat_and_controller_handle_option_calls(self):
        store = RehearsalStore(self.root / "sessions")
        run_id = store.prepare(day_cfg())["run_id"]
        scripted, prompts = ScriptedHTTP(), []

        def http(url, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in kwargs["json"]["messages"])
            prompts.append(text)
            if "Stable owner ID: alchemist" in text and "REHEARSAL CHOICE" in text and len(prompts) == 1:
                scripted.calls += 1
                return ScriptedResponse({
                    "id": "opt-1", "model": kwargs["json"].get("model"), "provider": "scripted-offline",
                    "choices": [{"message": {"content": json.dumps(OPTION_CALL)}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80, "cost": "0"},
                })
            return scripted(url, **kwargs)

        controller = RehearsalController(
            store, run_id, transport=OpenRouterTransport("scripted-offline", http_post=http),
            market=lambda: MARKET, options=lambda: options_snapshot(), now=lambda: OPEN,
        )
        job = controller.run_wake("alchemist")
        self.assertEqual((job["status"], job["action"]), ("completed", "call"))
        self.assertIn("OPTION CALL", prompts[0])

        controller.run_wake("alchemist")
        self.assertIn("option call 1: long SPY 2026-11-27 593 call at 2.18 ask", prompts[1])

        calls = CallStore(store.safe_run_file(run_id, CALLS_FILE))
        self.assertTrue(calls.has_open())
        cfg = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
               "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        clock = datetime(2026, 11, 27, 22, 0, tzinfo=timezone.utc)
        beat = Heartbeat(
            store, Schedule.from_config(cfg), prepare_day=None, run_wake=None,
            now=lambda: clock,
            fetch_closes=lambda syms, start, end: {
                "status": "ok",
                "closes": self._closes({s: 598 if s == "2026-11-27" else 593.5 for s in self.SESSIONS[:6]}),
            },
        )
        self.assertEqual(beat.tick()["calls"], {"open": 0, "settled": 1, "pending": []})
        self.assertEqual(calls.counts()["alchemist"],
                         {"open": 0, "settled": 1, "right": 1, "wrong": 0, "flat": 0, "unsettled": 0})
        self.assertEqual(calls.option_settlements()[0]["detail"]["outcome"], "right")


class HandBackAndEvaluateTests(Blocked):
    SESSIONS = ["2026-11-19", "2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27"]

    def test_hand_back_quotes_settled_vol_and_option_calls_for_two_wakes_only(self):
        calls = CallStore(self.root / CALLS_FILE)
        vol_id = calls.record(
            agent_id="tempest", run_id="run-1", wake_id="tempest-r1",
            choice=VOL_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
        )
        opt_id = calls.record(
            agent_id="tempest", run_id="run-1", wake_id="tempest-r2",
            choice=OPTION_CALL, market=MARKET, options=options_snapshot(), now=OPEN,
        )
        settle_open_calls(
            calls,
            lambda syms, start, end: {"status": "ok", "closes": {
                "SPY": {s: Decimal("594") if s == "2026-11-27" else Decimal("593.5") for s in self.SESSIONS}
            }},
            now=datetime(2026, 11, 27, 22, tzinfo=timezone.utc),
            today="2026-11-27",
            completed=lambda s: True,
        )

        # Wake 1 & 2 see both results; replay of wake 1 stays identical; wake 3 stops showing them.
        first = calls.hand_back("tempest", run_id="run-2", sitting="tempest-r1", now=OPEN)
        self.assertEqual([r["call_id"] for r in first], [opt_id, vol_id])
        self.assertEqual(
            [r["call_id"] for r in calls.hand_back("tempest", run_id="run-2", sitting="tempest-r1", now=OPEN)],
            [opt_id, vol_id],
        )
        line = call_results_line(first)
        self.assertIn("vol call 1: SPY 2026-11-27 options priced +/-2.00% (IV 14.2%, high)", line)
        self.assertIn("option call 2: long SPY 2026-11-27 593 call at 2.18 ask (indicative, spread 3.67%)", line)
        self.assertIn("Expiry close 594 -> intrinsic 1 (-54.13%", line)

        second = calls.hand_back("tempest", run_id="run-2", sitting="tempest-r2", now=OPEN)
        self.assertEqual([r["call_id"] for r in second], [opt_id, vol_id])
        third = calls.hand_back("tempest", run_id="run-2", sitting="tempest-r3", now=OPEN)
        self.assertEqual(third, [])

        # Append-only handback triggers hold.
        with closing(sqlite3.connect(str(self.root / CALLS_FILE))) as conn:
            for stmt in ("DELETE FROM vol_handbacks", "DELETE FROM option_handbacks"):
                with self.subTest(stmt=stmt), self.assertRaises(sqlite3.DatabaseError):
                    conn.execute(stmt)

    def test_root_discovery_finds_calls_after_the_first_page(self):
        root = self.root / "sessions"
        store = RehearsalStore(root)
        with patch("core.runtime.rehearsal.store._now", return_value="2026-11-19T15:00:00+00:00"):
            oldest = store.prepare(day_cfg())["run_id"]
        with patch("core.runtime.rehearsal.store._now", return_value="2026-11-20T15:00:00+00:00"):
            for _ in range(50):
                store.prepare(day_cfg())
        self.assertIsNone(resolve_calls_db(root=root))
        path = store.safe_run_file(oldest, CALLS_FILE)
        path.touch()
        self.assertEqual(resolve_calls_db(root=root), path)

    def test_evaluate_calls_summarizes_calibration_spread_and_direction_vs_payoff_without_reasons(self):
        missing = summarize_calls(self.root / "nonexistent.sqlite3")
        self.assertEqual(missing["status"], "missing")

        calls = CallStore(self.root / CALLS_FILE)
        secret_reason = "PRIVATE AGENT REASON MUST NEVER APPEAR IN EVALUATION OUTPUT"
        calls.record(
            agent_id="tempest", run_id="run-1", wake_id="tempest-r1",
            choice={**VOL_CALL, "reason": secret_reason}, market=MARKET, options=options_snapshot(), now=OPEN,
        )
        calls.record(
            agent_id="alchemist", run_id="run-1", wake_id="alchemist-r1",
            choice={**OPTION_CALL, "confidence": "high", "reason": secret_reason},
            market=MARKET, options=options_snapshot(), now=OPEN,
        )
        calls.record(
            agent_id="siren", run_id="run-1", wake_id="siren-r1",
            choice={**STOCK_CALL, "horizon_days": 10, "confidence": "low", "reason": secret_reason},
            market=MARKET, now=OPEN,
        )
        # Close at 594.0: vol high is right (+0.08% < 2.00%), option call ITM (+1.00) < ask (2.18) -> wrong
        # despite underlying moving up (+0.08% -> right_direction_net_loss_count=1), stock call stays open (horizon 10).
        settle_open_calls(
            calls,
            lambda syms, start, end: {"status": "ok", "closes": {
                "SPY": {s: Decimal("594") if s == "2026-11-27" else Decimal("593.5") for s in self.SESSIONS}
            }},
            now=datetime(2026, 11, 27, 22, tzinfo=timezone.utc),
            today="2026-11-27",
            completed=lambda s: s < "2026-11-27" or s == "2026-11-27",
        )
        summary = summarize_calls(self.root / CALLS_FILE)
        self.assertEqual(summary["status"], "ok")
        self.assertNotIn(secret_reason, json.dumps(summary))
        self.assertEqual(summary["overall"],
                         {"open": 1, "settled": 2, "right": 1, "wrong": 1, "flat": 0, "unsettled": 0, "hit_rate": "0.5000"})
        self.assertEqual(summary["by_kind"]["vol"]["hit_rate"], "1.0000")
        self.assertEqual(summary["by_kind"]["option"]["hit_rate"], "0.0000")
        self.assertIsNone(summary["by_kind"]["stock"]["hit_rate"])
        self.assertEqual(summary["option_summary"]["right_direction_net_loss_count"], 1)
        self.assertEqual(summary["option_summary"]["mean_spread_percent"], "3.67")
        self.assertEqual(summary["vol_summary"]["high_count"], 1)
        self.assertEqual(evaluate_main(["--db", str(self.root / CALLS_FILE), "--json"]), 0)


if __name__ == "__main__":
    unittest.main()
