"""Options view phase 1: read-only, small, labelled delayed, honest when unavailable.

Scripted HTTP; the network is blocked."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.market.options import (SNAPSHOTS_URL, OptionsView, fetch, market_open, options_evidence,
                                 options_line)
from core.market.window import fetch as fetch_prices, window_line
from core.runtime.owner_settings import OwnerSettings, SettingsError

KEY_ID, SECRET = "PK" + "C" * 18, "s" * 40
OPEN = datetime(2026, 11, 19, 15, 0, tzinfo=timezone.utc)      # Thursday 10:00 ET.
CLOSED = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)    # Thursday 17:00 ET.


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def snapshot(bid, ask, t="2026-11-19T14:59:30.123456789Z", iv=0.142, delta=0.5):
    return {"latestQuote": {"bp": bid, "ap": ask, "t": t}, "impliedVolatility": iv, "greeks": {"delta": delta}}


def chain():
    rows = {}
    for expiry in ("261120", "261121", "261127"):
        for strike in (730, 733, 736):
            rows[f"SPY{expiry}C00{strike}000"] = snapshot(2.1, 2.18)
            rows[f"SPY{expiry}P00{strike}000"] = snapshot(2.35, 2.44, delta=-0.5)
    rows["SPY261120C00739000"] = {"latestQuote": {"bp": 1.0}}  # No ask: left out.
    rows["NOT-AN-OCC"] = snapshot(1, 2)
    return {"snapshots": rows, "next_page_token": None}


class Scripted:
    def __init__(self, status=200, data=None):
        self.status, self.data, self.calls = status, data if data is not None else chain(), []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url != SNAPSHOTS_URL.format(symbol="SPY"):
            raise AssertionError("only the options snapshots address may be read: " + url)
        return Response(self.status, self.data)


class Blocked(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)


class FetchTests(Blocked):
    def test_fetch_keeps_quote_time_separate_from_fetch_time(self):
        from decimal import Decimal
        earlier = (OPEN - timedelta(minutes=7)).isoformat()
        for source_time in (earlier, None):
            with self.subTest(source_time=source_time):
                record = fetch("SPY", Decimal("733.4"), KEY_ID, SECRET, None,
                               http_get=Scripted(), now=lambda: OPEN, underlying_as_of=source_time)
                self.assertEqual(record["status"], "open")
                self.assertEqual(record["checked_at"], OPEN.isoformat())
                self.assertEqual(record.get("underlying_as_of"), source_time)

    def test_two_nearest_expiries_atm_pair_and_one_strike_out_each_side(self):
        from decimal import Decimal
        http = Scripted()
        record = fetch("SPY", Decimal("733.4"), KEY_ID, SECRET, "tempest paper account", http_get=http, now=lambda: OPEN)
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["feed"], "indicative")
        self.assertEqual(record["account"], "tempest paper account")
        contracts = record["contracts"]
        self.assertEqual({c["expiration"] for c in contracts}, {"2026-11-20", "2026-11-21"})
        self.assertEqual(sorted((c["type"], c["strike"]) for c in contracts if c["expiration"] == "2026-11-20"),
                         [("call", 733.0), ("call", 736.0), ("put", 730.0), ("put", 733.0)])
        self.assertLessEqual(len(contracts), 10)
        self.assertTrue(all(c["quote_time"].startswith("2026-11-19T14:59:30.123456") for c in contracts))
        (url, kwargs), = http.calls
        self.assertEqual(kwargs["params"]["feed"], "indicative")
        self.assertEqual(kwargs["params"]["expiration_date_gte"], "2026-11-20")
        self.assertFalse(kwargs["allow_redirects"])
        line = options_line(record, now=lambda: OPEN)
        self.assertIn("SPY options (Alpaca indicative feed, delayed", line)
        self.assertIn("Nov 20 (1 day): call 733 2.1/2.18 IV 14.2%", line)
        self.assertLessEqual(len(line), 700)
        evidence = options_evidence(record)
        self.assertEqual((evidence["status"], len(evidence["contracts"])), ("ok", 8))

    def test_old_quotes_are_marked_and_failures_never_invent_numbers(self):
        from decimal import Decimal
        old = {"snapshots": {f"SPY261120{k}00733000": snapshot(1, 2, t="2026-11-18T20:00:00Z") for k in "CP"}}
        record = fetch("SPY", Decimal(733), KEY_ID, SECRET, None, http_get=Scripted(data=old), now=lambda: OPEN)
        self.assertEqual(record["status"], "closed")
        self.assertIn("(old quote)", options_line(record, now=lambda: OPEN))
        for bad in (fetch("SPY", None, KEY_ID, SECRET, None, http_get=Scripted(), now=lambda: OPEN),
                    fetch("SPY", Decimal(733), "AK" + "A" * 18, SECRET, None, http_get=Scripted(), now=lambda: OPEN),
                    fetch("SPY", Decimal(733), KEY_ID, SECRET, None, http_get=Scripted(status=403), now=lambda: OPEN),
                    fetch("SPY", Decimal(733), KEY_ID, SECRET, None, http_get=Scripted(data={"snapshots": {}}), now=lambda: OPEN)):
            self.assertEqual(bad["status"], "unavailable")
            self.assertNotIn("contracts", bad)
            self.assertNotIn(SECRET, json.dumps(bad))
            self.assertTrue(options_line(bad).startswith("SPY options: unavailable"))
            self.assertEqual(options_evidence(bad), {"status": "unavailable"})

    def test_market_hours(self):
        self.assertTrue(market_open(OPEN))
        self.assertFalse(market_open(CLOSED))
        self.assertFalse(market_open(datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)))  # Saturday.


class CacheTests(Blocked):
    def test_options_cache_keeps_the_underlying_quotes_own_timestamp(self):
        quote_time = OPEN - timedelta(days=1)
        quote = {"last": 733.4, "as_of": quote_time.isoformat()}
        view = OptionsView(self.root, "SPY", lambda: (KEY_ID, SECRET, None), lambda: quote,
                           http_get=Scripted(), now=lambda: OPEN)
        record = view.read()
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["underlying_as_of"], quote_time.isoformat())
        self.assertNotEqual(record["underlying_as_of"], record["checked_at"])
        self.assertEqual(view.cached()["underlying_as_of"], record["underlying_as_of"])

    def test_one_fetch_per_half_hour_and_none_outside_market_hours(self):
        clock = [CLOSED]
        http = Scripted()
        view = OptionsView(self.root, "SPY", lambda: (KEY_ID, SECRET, "tempest paper account"),
                           lambda: 733.4, http_get=http, now=lambda: clock[0])
        self.assertEqual(view.read()["status"], "unavailable")  # Closed and nothing read yet.
        self.assertEqual(http.calls, [])
        clock[0] = OPEN
        self.assertEqual(view.read()["status"], "open")
        cached = view.cached()
        self.assertNotIn("underlying_as_of", cached)
        self.assertEqual(cached["checked_at"], OPEN.isoformat())
        clock[0] = OPEN + timedelta(minutes=29)
        view.read()
        self.assertEqual(len(http.calls), 1)
        clock[0] = OPEN + timedelta(minutes=31)
        view.read()
        self.assertEqual(len(http.calls), 2)
        clock[0] = CLOSED
        self.assertEqual(view.read()["status"], "closed")  # Last quotes kept, nothing fetched.
        self.assertEqual(len(http.calls), 2)
        self.assertEqual((self.root / "options.json").stat().st_mode & 0o077, 0)


class PriceTimeTests(Blocked):
    def test_each_price_keeps_its_own_time_and_a_stale_one_is_marked(self):
        rows = {"SPY": {"latestTrade": {"p": 733, "t": "2026-11-19T14:59:00Z"}, "prevDailyBar": {"c": 730}},
                "GLD": {"latestTrade": {"p": 343, "t": "2026-11-18T20:59:00Z"}},
                "TLT": {"dailyBar": {"c": 80}}}  # No time of its own.
        http = lambda url, **kwargs: Response(200, rows)
        record = fetch_prices(["SPY", "GLD", "TLT"], KEY_ID, SECRET, http_get=http, now=lambda: OPEN,
                              account="tempest paper account")
        quotes = {q["symbol"]: q for q in record["quotes"]}
        self.assertEqual(record["status"], "open")
        self.assertEqual(record["account"], "tempest paper account")
        self.assertFalse(quotes["SPY"]["stale"])
        self.assertTrue(quotes["GLD"]["stale"])
        self.assertNotIn("as_of", quotes["TLT"])  # Never given the fetch time.
        line = window_line(record)
        self.assertIn("GLD 343 (old price)", line)
        self.assertIn("TLT 80 (time unknown)", line)


class SettingsTests(Blocked):
    def test_the_owner_picks_the_options_ticker_and_the_data_account(self):
        settings = OwnerSettings(self.root / "settings")
        self.assertIsNone(settings.data_credentials())
        settings.update({"secrets": {"alpaca_siren_key_id": "PKSIREN123456789", "alpaca_siren_secret": "s" * 40,
                                     "alpaca_weaver_key_id": "PKWEAVER12345678", "alpaca_weaver_secret": "w" * 40}})
        self.assertEqual(settings.data_credentials()[2], "siren paper account (fallback)")
        settings.update({"data_account": "weaver", "options_symbol": " qqq "})
        self.assertEqual(settings.data_credentials()[2], "weaver paper account")
        self.assertEqual(settings.options_symbol(), "QQQ")
        self.assertEqual((settings.read()["data_account"], settings.read()["options_symbol"]), ("weaver", "QQQ"))
        for bad in ({"data_account": "witness"}, {"options_symbol": "BRK.B"}, {"options_symbol": ""}):
            with self.subTest(bad=bad), self.assertRaises(SettingsError):
                settings.update(bad)


if __name__ == "__main__":
    unittest.main()
