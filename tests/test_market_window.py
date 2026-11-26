"""Market window, phase 1: read-only prices, cached, honest when unavailable.

Scripted HTTP; the network is blocked."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.market.window import (DATA_URL, DEFAULT_WATCHLIST, MarketWindow, MarketWindowError, fetch,
                                inquiry_evidence, validate_symbols, window_line)
from core.runtime.owner_settings import OwnerSettings, SettingsError
from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest

KEY_ID, SECRET = "PK" + "A" * 18, "s" * 40
NOW = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)  # 10:00 ET.


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def snapshots(trade_time="2026-11-19T14:58:00Z"):
    def row(price, before):
        return {"latestTrade": {"p": price, "t": trade_time},
                "dailyBar": {"o": before, "h": price + 1, "l": before - 1, "c": price, "v": 1200, "t": trade_time},
                "prevDailyBar": {"c": before}}
    return {"SPY": row(505.0, 500.0), "QQQ": row(441.0, 450.0), "IWM": {"latestTrade": {"p": "bad"}}}


class ScriptedData:
    def __init__(self, status=200, data=None):
        self.status, self.data, self.calls = status, data if data is not None else snapshots(), []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url != DATA_URL:
            raise AssertionError("only the market data snapshot endpoint may be called: " + url)
        return Response(self.status, self.data)


class BlockedNetwork(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class FetchTests(BlockedNetwork):
    def test_prices_come_only_from_the_response_and_only_one_get(self):
        http = ScriptedData()
        record = fetch(["SPY", "QQQ", "IWM"], KEY_ID, SECRET, http_get=http, now=lambda: NOW)
        self.assertEqual(record["status"], "open")
        quotes = {q["symbol"]: q for q in record["quotes"]}
        self.assertEqual(set(quotes), {"SPY", "QQQ"})  # IWM had no usable price: left out.
        self.assertEqual(quotes["SPY"]["change_percent"], 1.0)
        self.assertEqual(quotes["QQQ"]["change_percent"], -2.0)
        (url, kwargs), = http.calls
        self.assertEqual(kwargs["params"], {"symbols": "SPY,QQQ,IWM", "feed": "iex"})
        self.assertFalse(kwargs["allow_redirects"])
        self.assertLessEqual(kwargs["timeout"], 10)

    def test_old_prices_say_the_market_is_closed(self):
        record = fetch(["SPY"], KEY_ID, SECRET, http_get=ScriptedData(data=snapshots("2026-11-18T21:00:00Z")),
                       now=lambda: NOW)
        self.assertEqual(record["status"], "closed")
        self.assertIn("market closed", window_line(record))
        self.assertEqual(inquiry_evidence(record)["status"], "closed")

    def test_failures_are_unavailable_and_never_invent_numbers(self):
        def down(url, **kwargs):
            raise ConnectionError("down")
        cases = [fetch(["SPY"], KEY_ID, SECRET, http_get=ScriptedData(status=403), now=lambda: NOW),
                 fetch(["SPY"], KEY_ID, SECRET, http_get=down, now=lambda: NOW),
                 fetch(["SPY"], KEY_ID, SECRET, http_get=ScriptedData(data={"SPY": {}}), now=lambda: NOW)]
        for record in cases:
            with self.subTest(record=record):
                self.assertEqual(record["status"], "unavailable")
                self.assertNotIn("quotes", record)
                self.assertTrue(window_line(record).startswith("Market window: unavailable"))
                self.assertEqual(inquiry_evidence(record), {"status": "unavailable"})
                self.assertNotIn(SECRET, json.dumps(record))

    def test_a_live_or_missing_key_is_never_sent(self):
        http = ScriptedData()
        for key_id in ("AK" + "A" * 18, None, ""):
            record = fetch(["SPY"], key_id, SECRET, http_get=http, now=lambda: NOW)
            self.assertEqual(record["status"], "unavailable")
        self.assertEqual(http.calls, [])

    def test_watchlists_are_small_and_clean(self):
        self.assertEqual(validate_symbols([" spy", "BRK.B", "SPY"]), ["SPY", "BRK.B"])
        for bad in ([], ["SPY"] * 6, ["SP Y"], ["TOOLONG"], [5], "SPY"):
            with self.subTest(bad=bad), self.assertRaises(MarketWindowError):
                validate_symbols(bad)


class CacheTests(BlockedNetwork):
    def test_one_fetch_per_window_shared_and_failures_wait_too(self):
        clock = [NOW]
        http = ScriptedData(status=500)
        window = MarketWindow(self.root / "market", DEFAULT_WATCHLIST, lambda: (KEY_ID, SECRET),
                              http_get=http, now=lambda: clock[0])
        self.assertEqual(window.read()["status"], "unavailable")
        clock[0] = NOW + timedelta(minutes=14)
        window.read()
        self.assertEqual(len(http.calls), 1)  # The failure is not retried inside the window.
        http.status = 200
        clock[0] = NOW + timedelta(minutes=16)
        self.assertIn(window.read()["status"], ("open", "closed"))
        self.assertEqual(len(http.calls), 2)
        self.assertEqual((self.root / "market" / "window.json").stat().st_mode & 0o077, 0)

    def test_a_changed_watchlist_fetches_again(self):
        http = ScriptedData()
        MarketWindow(self.root, ["SPY"], lambda: (KEY_ID, SECRET), http_get=http, now=lambda: NOW).read()
        MarketWindow(self.root, ["QQQ"], lambda: (KEY_ID, SECRET), http_get=http, now=lambda: NOW).read()
        self.assertEqual(len(http.calls), 2)


class SettingsTests(BlockedNetwork):
    def test_the_owner_sets_the_watchlist(self):
        settings = OwnerSettings(self.root / "settings")
        self.assertIsNone(settings.watchlist())
        settings.update({"watchlist": ["nvda", "SPY"]})
        self.assertEqual(settings.watchlist(), ["NVDA", "SPY"])
        self.assertEqual(settings.read()["watchlist"], ["NVDA", "SPY"])
        with self.assertRaises(SettingsError):
            settings.update({"watchlist": ["A", "B", "C", "D", "E", "F"]})


class WakeTests(BlockedNetwork):
    def test_every_choice_sees_the_window_and_inquire_gets_the_quotes(self):
        from core.runtime.orientation import SHELF_ORIENTATION

        store = RehearsalStore(self.root / "sessions")
        window = MarketWindow(self.root / "market", ["SPY", "QQQ"], lambda: (KEY_ID, SECRET),
                              http_get=ScriptedData(), now=lambda: NOW)
        http, prompts = ScriptedHTTP(), []
        contract = {"symbol": "SPY261120C00505000", "type": "call", "strike": 505.0,
                    "expiration": "2026-11-20", "bid": 2.1, "ask": 2.18, "iv": 0.142,
                    "delta": 0.5, "quote_time": "2026-11-18T09:00:00+00:00", "stale": False}

        def recording(url, **kwargs):
            prompts.append(chr(10).join(str(m.get("content", "")) for m in kwargs["json"]["messages"]))
            return http(url, **kwargs)

        def prepare_day(budget_usd, wakes_per_agent, models=None):
            return store.prepare(day_manifest(wakes=wakes_per_agent, budget=budget_usd))["run_id"]

        def run_wake(run_id, owner, step=None):
            return RehearsalController(store, run_id, transport=OpenRouterTransport(
                "scripted-offline", http_post=recording), market=window.read,
                options=lambda: {"symbol": "SPY", "status": "open", "feed": "indicative",
                                 "contracts": [dict(contract)]},
                feeds=lambda: {"headlines": {"status": "ok", "items": [{"title": "Fed holds rates", "source": "Wire"}]},
                               "x": {"status": "unavailable", "reason": "it answered 403"}}).run_wake(owner, step=step)

        config = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
                  "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        clock = [datetime(2026, 11, 18, 9, 5, tzinfo=timezone.utc)]  # Tempest 9:00, Siren 9:02, Alchemist 9:04.
        beat = Heartbeat(store, Schedule.from_config(config), prepare_day=prepare_day, run_wake=run_wake,
                         now=lambda: clock[0])
        result = beat.tick()
        self.assertEqual([w["status"] for w in result["wakes"]], ["completed"] * 3)
        market_heading = "Outside the window (UNTRUSTED"
        choices = [p for p in prompts if market_heading in p]
        self.assertEqual(len(choices), 3)
        self.assertIn(SHELF_ORIENTATION, choices[0])  # The table of contents, not full skill texts.
        self.assertIn("SPY 505 (+1.00%)", choices[0])
        self.assertIn("Headlines (Massive news): Fed holds rates (Wire)", choices[0])
        self.assertIn("On X: unavailable (it answered 403).", choices[0])
        alchemist = [p for p in prompts if "Stable owner ID: alchemist" in p and market_heading not in p]
        self.assertTrue(any('"symbol":"SPY"' in p.replace(" ", "") for p in alchemist))  # The inquiry's evidence.
        self.assertIn("SPY options (Alpaca indicative feed, delayed", choices[0])
        self.assertIn("call 505 2.1/2.18 IV 14.2%", choices[0])
        self.assertTrue(any('"strike":505.0' in p.replace(" ", "") for p in alchemist))  # Contracts reach the inquiry.

        run_id = result["run_id"]
        earlier = store.get_decision_details(run_id, "tempest-r1")
        self.assertTrue(earlier["requests"])
        self.assertEqual(earlier["private_context"]["options"]["contracts"][0]["ask"], 2.18)

        contract.update(ask=2.40, quote_time="2026-11-18T09:14:00+00:00")
        clock[0] += timedelta(minutes=14)
        self.assertEqual(beat.tick()["run_id"], run_id)
        request_count = len(prompts)
        later = store.get_decision_details(run_id, "tempest-r2")
        self.assertEqual(later["private_context"]["options"]["contracts"][0]["ask"], 2.40)
        self.assertIn("call 505 2.1/2.4", later["private_context"]["market_line"])
        self.assertEqual(store.get_decision_details(run_id, "tempest-r1"), earlier)
        self.assertEqual(len(prompts), request_count)


if __name__ == "__main__":
    unittest.main()
