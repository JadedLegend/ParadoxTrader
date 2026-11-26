"""Calls: an agent writes down a forecast, sealed with the price it was shown.

Phase 1 of docs/specs/CALLS_AND_SETTLEMENT.md. A call is a forecast, not a
trade: it buys nothing, sizes nothing and touches no broker. Making one is the
choice itself, so it adds no model request.

- The entry price comes only from the market window already committed with that
  wake's choice, never a later read, so a resumed wake records the same price
  and nothing can see the future.
- Append-only: a call row is never updated or deleted. Settlement (phase 2) is
  a separate table; a call with no settlement is open.
- Unknown is unknown: no committed price for the ticker refuses the call with a
  reason instead of recording a guess or a zero.

The database lives in each run (``calls.sqlite3``) and carries to the next day
with the rest of the home, so open calls stay open.
"""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import re
import sqlite3

from core.market.options import STALE_QUOTE_SECONDS

CALLS_FILE = "calls.sqlite3"
CALL_OPTIONS = {
    "directions": ["up", "down"],
    "min_horizon_days": 1, "max_horizon_days": 20, "horizon_unit": "trading_days",
    "confidences": ["low", "medium", "high"],
    "max_reason_chars": 400, "max_open_per_agent": 5,
    "symbols": "this wake's market window",
}
CALL_FIELDS = ("kind", "symbol", "direction", "horizon_days", "expiry", "iv_view",
               "option_type", "strike", "confidence", "reason")
VOL_IV_VIEWS = ("high", "low")
OPTION_TYPES = ("call", "put")
VOL_DEADBAND = Decimal("0.25")
OPTION_DEADBAND = Decimal("0.01")
NO_CALLS = {"open": 0, "settled": 0, "right": 0, "wrong": 0, "flat": 0, "unsettled": 0}
_SYMBOL = re.compile(r"[A-Z]{1,5}(?:[.][A-Z]{1,2})?")


def _session(moment):
    """The trading session (Eastern date) of a price time. Without tz data, US Eastern
    standard time gives the same date for any time a US session prices."""
    try:
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:
        return moment.astimezone(timezone(timedelta(hours=-5))).date().isoformat()


CALL_INSTRUCTIONS = (
    # Kept short: choice prompts already reach the input bound, and every byte here
    # is trimmed from the agent's own continuity. A shape, not sample values: a
    # concrete example would be copied by every agent.
    "\nCALL (offered on this wake): or choose a forecast sealed with the price shown below: "
    "{\"action\":\"call\",\"symbol\":<ticker in the window>,\"direction\":<up|down>,"
    "\"horizon_days\":<1-20 trading days>,\"confidence\":<low|medium|high>,\"reason\":<optional, "
    "at most 400 characters>}. Not a trade; nothing is bought. The later close is recorded beside "
    "it and shown to you. Never edited; at most five open. No call is owed."
)

VOL_CALL_INSTRUCTIONS = (
    "\nVOLATILITY CALL (when options are open): or seal a volatility view against the options line: "
    "{\"action\":\"call\",\"kind\":\"vol\",\"symbol\":<options ticker>,\"expiry\":<YYYY-MM-DD>,"
    "\"iv_view\":<high|low>,\"confidence\":<low|medium|high>,\"reason\":<optional, <=400 chars>}. "
    "Checks whether the move by expiry is smaller (high) or larger (low) than the options' implied move."
)

OPTION_CALL_INSTRUCTIONS = (
    "\nOPTION CALL (when options are open): or seal one long option from the options line at its ask: "
    "{\"action\":\"call\",\"kind\":\"option\",\"symbol\":<options ticker>,\"expiry\":<YYYY-MM-DD>,"
    "\"option_type\":<call|put>,\"strike\":<number>,\"confidence\":<low|medium|high>,"
    "\"reason\":<optional, <=400 chars>}. Settles at expiry close minus ask."
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
 call_id INTEGER PRIMARY KEY,
 agent_id TEXT NOT NULL, run_id TEXT NOT NULL, wake_id TEXT NOT NULL,
 symbol TEXT NOT NULL, direction TEXT NOT NULL CHECK (direction IN ('up','down')),
 horizon_days INTEGER NOT NULL CHECK (horizon_days BETWEEN 1 AND 20),
 confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
 reason TEXT NOT NULL,
 entry_price TEXT NOT NULL, price_as_of TEXT NOT NULL, window_status TEXT NOT NULL,
 entry_session TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE (run_id, wake_id)
);
CREATE TRIGGER IF NOT EXISTS calls_no_update BEFORE UPDATE ON calls
 BEGIN SELECT RAISE(ABORT, 'calls are append-only'); END;
CREATE TRIGGER IF NOT EXISTS calls_no_delete BEFORE DELETE ON calls
 BEGIN SELECT RAISE(ABORT, 'calls are append-only'); END;
CREATE TABLE IF NOT EXISTS settlements (
 call_id INTEGER PRIMARY KEY REFERENCES calls(call_id),
 settled_at TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS settlements_no_update BEFORE UPDATE ON settlements
 BEGIN SELECT RAISE(ABORT, 'settlements are append-only'); END;
CREATE TRIGGER IF NOT EXISTS settlements_no_delete BEFORE DELETE ON settlements
 BEGIN SELECT RAISE(ABORT, 'settlements are append-only'); END;
CREATE TABLE IF NOT EXISTS handbacks (
 call_id INTEGER NOT NULL REFERENCES settlements(call_id),
 run_id TEXT NOT NULL, sitting TEXT NOT NULL, shown_at TEXT NOT NULL,
 PRIMARY KEY (call_id, run_id, sitting)
);
CREATE TRIGGER IF NOT EXISTS handbacks_no_update BEFORE UPDATE ON handbacks
 BEGIN SELECT RAISE(ABORT, 'handbacks are append-only'); END;
CREATE TRIGGER IF NOT EXISTS handbacks_no_delete BEFORE DELETE ON handbacks
 BEGIN SELECT RAISE(ABORT, 'handbacks are append-only'); END;
CREATE TABLE IF NOT EXISTS vol_calls (
 call_id INTEGER PRIMARY KEY,
 agent_id TEXT NOT NULL, run_id TEXT NOT NULL, wake_id TEXT NOT NULL,
 symbol TEXT NOT NULL, expiry TEXT NOT NULL,
 iv_view TEXT NOT NULL CHECK (iv_view IN ('high','low')),
 confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
 reason TEXT NOT NULL,
 entry_price TEXT NOT NULL, price_as_of TEXT NOT NULL,
 entry_iv TEXT NOT NULL, implied_move_pct TEXT NOT NULL,
 trading_days INTEGER NOT NULL CHECK (trading_days >= 2),
 atm_strike TEXT NOT NULL, quote_time TEXT NOT NULL, feed TEXT NOT NULL,
 entry_session TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE (run_id, wake_id)
);
CREATE TRIGGER IF NOT EXISTS vol_calls_no_update BEFORE UPDATE ON vol_calls
 BEGIN SELECT RAISE(ABORT, 'vol calls are append-only'); END;
CREATE TRIGGER IF NOT EXISTS vol_calls_no_delete BEFORE DELETE ON vol_calls
 BEGIN SELECT RAISE(ABORT, 'vol calls are append-only'); END;
CREATE TABLE IF NOT EXISTS vol_settlements (
 call_id INTEGER PRIMARY KEY REFERENCES vol_calls(call_id),
 settled_at TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS vol_settlements_no_update BEFORE UPDATE ON vol_settlements
 BEGIN SELECT RAISE(ABORT, 'vol settlements are append-only'); END;
CREATE TRIGGER IF NOT EXISTS vol_settlements_no_delete BEFORE DELETE ON vol_settlements
 BEGIN SELECT RAISE(ABORT, 'vol settlements are append-only'); END;
CREATE TABLE IF NOT EXISTS vol_handbacks (
 call_id INTEGER NOT NULL REFERENCES vol_settlements(call_id),
 run_id TEXT NOT NULL, sitting TEXT NOT NULL, shown_at TEXT NOT NULL,
 PRIMARY KEY (call_id, run_id, sitting)
);
CREATE TRIGGER IF NOT EXISTS vol_handbacks_no_update BEFORE UPDATE ON vol_handbacks
 BEGIN SELECT RAISE(ABORT, 'vol handbacks are append-only'); END;
CREATE TRIGGER IF NOT EXISTS vol_handbacks_no_delete BEFORE DELETE ON vol_handbacks
 BEGIN SELECT RAISE(ABORT, 'vol handbacks are append-only'); END;
CREATE TABLE IF NOT EXISTS option_calls (
 call_id INTEGER PRIMARY KEY,
 agent_id TEXT NOT NULL, run_id TEXT NOT NULL, wake_id TEXT NOT NULL,
 contract TEXT NOT NULL, symbol TEXT NOT NULL, expiry TEXT NOT NULL,
 option_type TEXT NOT NULL CHECK (option_type IN ('call','put')),
 strike TEXT NOT NULL,
 confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
 reason TEXT NOT NULL,
 entry_bid TEXT NOT NULL, entry_ask TEXT NOT NULL, spread_pct TEXT NOT NULL,
 entry_iv TEXT, entry_delta TEXT,
 entry_underlying_price TEXT NOT NULL, price_as_of TEXT NOT NULL,
 quote_time TEXT NOT NULL, feed TEXT NOT NULL,
 entry_session TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE (run_id, wake_id)
);
CREATE TRIGGER IF NOT EXISTS option_calls_no_update BEFORE UPDATE ON option_calls
 BEGIN SELECT RAISE(ABORT, 'option calls are append-only'); END;
CREATE TRIGGER IF NOT EXISTS option_calls_no_delete BEFORE DELETE ON option_calls
 BEGIN SELECT RAISE(ABORT, 'option calls are append-only'); END;
CREATE TABLE IF NOT EXISTS option_settlements (
 call_id INTEGER PRIMARY KEY REFERENCES option_calls(call_id),
 settled_at TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS option_settlements_no_update BEFORE UPDATE ON option_settlements
 BEGIN SELECT RAISE(ABORT, 'option settlements are append-only'); END;
CREATE TRIGGER IF NOT EXISTS option_settlements_no_delete BEFORE DELETE ON option_settlements
 BEGIN SELECT RAISE(ABORT, 'option settlements are append-only'); END;
CREATE TABLE IF NOT EXISTS option_handbacks (
 call_id INTEGER NOT NULL REFERENCES option_settlements(call_id),
 run_id TEXT NOT NULL, sitting TEXT NOT NULL, shown_at TEXT NOT NULL,
 PRIMARY KEY (call_id, run_id, sitting)
);
CREATE TRIGGER IF NOT EXISTS option_handbacks_no_update BEFORE UPDATE ON option_handbacks
 BEGIN SELECT RAISE(ABORT, 'option handbacks are append-only'); END;
CREATE TRIGGER IF NOT EXISTS option_handbacks_no_delete BEFORE DELETE ON option_handbacks
 BEGIN SELECT RAISE(ABORT, 'option handbacks are append-only'); END;
"""


class CallRefused(ValueError):
    """A call the runtime declines, with a short code for the wake record."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _validate_expiry(expiry):
    if not isinstance(expiry, str) or len(expiry) != 10:
        raise ValueError("invalid call expiry")
    try:
        date.fromisoformat(expiry)
    except ValueError as exc:
        raise ValueError("invalid call expiry") from exc


def validate_call_fields(value):
    """Shape only. Raises ValueError; market/options quotes are checked later."""
    if value.get("action") != "call":
        if set(value) & set(CALL_FIELDS):
            raise ValueError("invalid call fields")
        return
    kind = value.get("kind", "stock")
    if "kind" in value and kind not in ("stock", "vol", "option"):
        raise ValueError("invalid call kind")
    if kind == "vol":
        if {"direction", "horizon_days", "option_type", "strike"} & set(value):
            raise ValueError("invalid vol call fields")
        missing = {"symbol", "expiry", "iv_view", "confidence"} - set(value)
        if missing:
            raise ValueError("incomplete call")
        if not isinstance(value["symbol"], str) or not _SYMBOL.fullmatch(value["symbol"]):
            raise ValueError("invalid call symbol")
        _validate_expiry(value["expiry"])
        if value["iv_view"] not in VOL_IV_VIEWS:
            raise ValueError("invalid iv_view")
    elif kind == "option":
        if {"direction", "horizon_days", "iv_view"} & set(value):
            raise ValueError("invalid option call fields")
        missing = {"symbol", "expiry", "option_type", "strike", "confidence"} - set(value)
        if missing:
            raise ValueError("incomplete call")
        if not isinstance(value["symbol"], str) or not _SYMBOL.fullmatch(value["symbol"]):
            raise ValueError("invalid call symbol")
        _validate_expiry(value["expiry"])
        if value["option_type"] not in OPTION_TYPES:
            raise ValueError("invalid option_type")
        strike = value["strike"]
        if isinstance(strike, bool) or not isinstance(strike, (int, float)):
            raise ValueError("invalid call strike")
        if not math.isfinite(strike) or Decimal(str(strike)) <= 0:
            raise ValueError("invalid call strike")
    else:
        if {"expiry", "iv_view", "option_type", "strike"} & set(value):
            raise ValueError("invalid stock call fields")
        missing = {"symbol", "direction", "horizon_days", "confidence"} - set(value)
        if missing:
            raise ValueError("incomplete call")
        if not isinstance(value["symbol"], str) or not _SYMBOL.fullmatch(value["symbol"]):
            raise ValueError("invalid call symbol")
        if value["direction"] not in CALL_OPTIONS["directions"]:
            raise ValueError("invalid call direction")
        horizon = value["horizon_days"]
        if type(horizon) is not int or not CALL_OPTIONS["min_horizon_days"] <= horizon <= CALL_OPTIONS["max_horizon_days"]:
            raise ValueError("invalid call horizon")
    if value["confidence"] not in CALL_OPTIONS["confidences"]:
        raise ValueError("invalid call confidence")
    if "reason" in value:
        reason = value["reason"]
        if (not isinstance(reason, str) or len(reason) > CALL_OPTIONS["max_reason_chars"]
                or any(ord(c) < 32 and c not in "\n\t" for c in reason)):
            raise ValueError("invalid call reason")


def _entry(market, symbol):
    """The committed quote for ``symbol``: (price text, its as_of, window status)."""
    if not isinstance(market, dict) or market.get("status") not in ("ok", "closed"):
        raise CallRefused("call_no_price")
    quote = next((q for q in market.get("quotes") or [] if isinstance(q, dict) and q.get("symbol") == symbol), None)
    if quote is None:
        symbols = [q.get("symbol") for q in market.get("quotes") or [] if isinstance(q, dict)]
        raise CallRefused("call_symbol_not_watched" if symbol not in symbols else "call_no_price")
    try:
        price = Decimal(str(quote["last"]))
        moment = datetime.fromisoformat(quote["as_of"])
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise CallRefused("call_no_price") from None
    if not price.is_finite() or price <= 0 or moment.tzinfo is None:
        raise CallRefused("call_no_price")  # A price with no time of its own is unknown.
    return format(price.normalize(), "f"), moment.astimezone(timezone.utc), market["status"]


def _vol_underlying(market, options, symbol):
    """Entry underlying price + timestamp from committed market or options snapshot."""
    if isinstance(market, dict) and market.get("status") in ("ok", "closed"):
        try:
            price_text, moment, _ = _entry(market, symbol)
            return Decimal(price_text), price_text, moment
        except CallRefused as error:
            if error.code == "call_no_price":
                pass
    try:
        price = Decimal(str(options["underlying_price"]))
        moment = datetime.fromisoformat(str(options["checked_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise CallRefused("call_no_price") from None
    if not price.is_finite() or price <= 0 or moment.tzinfo is None:
        raise CallRefused("call_no_price")
    return price, format(price.normalize(), "f"), moment.astimezone(timezone.utc)


def _parse_quote_time(row, now):
    """Check staleness and return UTC quote_time, or raise CallRefused('call_options_stale')."""
    if row.get("stale") is True:
        raise CallRefused("call_options_stale")
    raw_qt = row.get("quote_time")
    if not isinstance(raw_qt, str):
        raise CallRefused("call_options_stale")
    try:
        qt = datetime.fromisoformat(raw_qt.replace("Z", "+00:00"))
    except ValueError:
        raise CallRefused("call_options_stale") from None
    if qt.tzinfo is None or not 0 <= (now - qt).total_seconds() <= STALE_QUOTE_SECONDS:
        raise CallRefused("call_options_stale")
    return qt.astimezone(timezone.utc)


def _exchange_sessions_after(entry_session, expiry):
    """Count NYSE sessions after entry through expiry, including early closes."""
    from exchange_calendars import get_calendar

    if expiry <= entry_session:
        return 0
    start = date.fromisoformat(entry_session) + timedelta(days=1)
    end = date.fromisoformat(expiry)
    # Use stable calendar bounds around the frozen dates, independent of retry time.
    try:
        calendar = get_calendar("XNYS", start=f"{start.year - 1:04d}-12-01", end=f"{end.year + 1:04d}-01-31")
        return calendar.sessions_distance(start, end)
    except ValueError:
        raise CallRefused("call_calendar_unavailable") from None


def _vol_entry(market, options, symbol, expiry, now):
    """Seal ATM implied volatility and expected move from committed options snapshot."""
    if not isinstance(options, dict) or options.get("status") not in ("open", "ok"):
        raise CallRefused("call_options_unavailable")
    if options.get("symbol") not in (None, symbol):
        raise CallRefused("call_contract_not_shown")
    contracts = [
        c for c in (options.get("contracts") or [])
        if isinstance(c, dict) and c.get("expiration") == expiry
        and (not c.get("symbol") or str(c["symbol"]).startswith(symbol))
    ]
    if not contracts:
        raise CallRefused("call_contract_not_shown")
    price_dec, price_text, price_moment = _vol_underlying(market, options, symbol)
    entry_session = _session(price_moment)
    trading_days = _exchange_sessions_after(entry_session, expiry)
    if trading_days < 2:
        raise CallRefused("call_horizon_too_short")
    by_strike = {}
    for row in contracts:
        try:
            strike = Decimal(str(row["strike"]))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if not strike.is_finite() or strike <= 0 or row.get("type") not in ("call", "put"):
            continue
        by_strike.setdefault(strike, []).append(row)
    if not by_strike:
        raise CallRefused("call_contract_not_shown")
    atm_strike = min(by_strike, key=lambda strike: (abs(strike - price_dec), strike))
    atm_rows = by_strike[atm_strike]
    quote_times, ivs = [], {}
    for row in atm_rows:
        quote_times.append(_parse_quote_time(row, now))
        if row.get("iv") is not None and not isinstance(row.get("iv"), bool):
            try:
                iv = Decimal(str(row["iv"]))
            except (ValueError, InvalidOperation):
                iv = None
            if iv is not None and iv.is_finite() and iv > 0:
                ivs.setdefault(row["type"], iv)
    if not ivs:
        raise CallRefused("call_no_iv")
    entry_iv = (sum(ivs.values()) / Decimal(len(ivs))).quantize(Decimal("0.0001"))
    implied_move_pct = (entry_iv * Decimal(str(math.sqrt(trading_days / 252))) * Decimal("100")).quantize(Decimal("0.01"))
    if implied_move_pct <= 0:
        raise CallRefused("call_no_iv")
    return {
        "entry_price": price_text,
        "price_as_of": price_moment.isoformat(),
        "entry_session": entry_session,
        "entry_iv": format(entry_iv.normalize(), "f"),
        "implied_move_pct": format(implied_move_pct, "f"),
        "trading_days": trading_days,
        "atm_strike": format(atm_strike.normalize(), "f"),
        "quote_time": max(quote_times).isoformat(),
        "feed": str(options.get("source") or options.get("feed") or "alpaca-options indicative delayed"),
    }


def _optional_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        dec = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return format(dec.normalize(), "f") if dec.is_finite() else None


def _option_entry(market, options, symbol, expiry, option_type, strike, now):
    """Seal a single-leg long option contract at its quoted ask price."""
    if not isinstance(options, dict) or options.get("status") not in ("open", "ok"):
        raise CallRefused("call_options_unavailable")
    if options.get("symbol") not in (None, symbol):
        raise CallRefused("call_contract_not_shown")
    target_strike = Decimal(str(strike)).normalize()
    matched = None
    for row in options.get("contracts") or []:
        if not isinstance(row, dict):
            continue
        if row.get("expiration") != expiry or row.get("type") != option_type:
            continue
        if row.get("symbol") and not str(row["symbol"]).startswith(symbol):
            continue
        try:
            row_strike = Decimal(str(row["strike"])).normalize()
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        if row_strike == target_strike:
            matched = row
            break
    if matched is None:
        raise CallRefused("call_contract_not_shown")
    qt = _parse_quote_time(matched, now)
    try:
        bid = Decimal(str(matched["bid"]))
        ask = Decimal(str(matched["ask"]))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise CallRefused("call_bad_option_quote") from None
    if (isinstance(matched.get("bid"), bool) or isinstance(matched.get("ask"), bool)
            or not bid.is_finite() or not ask.is_finite() or bid < 0 or ask <= 0 or ask < bid):
        raise CallRefused("call_bad_option_quote")
    _, price_text, price_moment = _vol_underlying(market, options, symbol)
    entry_session = _session(price_moment)
    if expiry <= entry_session:
        raise CallRefused("call_horizon_too_short")
    spread_pct = ((ask - bid) / ask * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "contract": str(matched["symbol"]),
        "strike": format(target_strike, "f"),
        "entry_bid": format(bid.normalize(), "f"),
        "entry_ask": format(ask.normalize(), "f"),
        "spread_pct": format(spread_pct, "f"),
        "entry_iv": _optional_decimal(matched.get("iv")),
        "entry_delta": _optional_decimal(matched.get("delta")),
        "entry_underlying_price": price_text,
        "price_as_of": price_moment.isoformat(),
        "entry_session": entry_session,
        "quote_time": qt.isoformat(),
        "feed": str(options.get("source") or options.get("feed") or "alpaca-options indicative delayed"),
    }


class CallStore:
    def __init__(self, path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript(_SCHEMA)
        return connection

    def _reader(self):
        connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _has_table(connection, table):
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    @staticmethod
    def _next_call_id(connection):
        row = connection.execute(
            "SELECT MAX(id) FROM ("
            " SELECT COALESCE(MAX(call_id), 0) AS id FROM calls"
            " UNION ALL"
            " SELECT COALESCE(MAX(call_id), 0) AS id FROM vol_calls"
            " UNION ALL"
            " SELECT COALESCE(MAX(call_id), 0) AS id FROM option_calls"
            ")"
        ).fetchone()
        return (row[0] or 0) + 1

    def record(self, *, agent_id, run_id, wake_id, choice, market, options=None, now=None):
        """Seal one call. Retrying the same wake returns the same call."""
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        kind = choice.get("kind", "stock")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for table in ("calls", "vol_calls", "option_calls"):
                existing = connection.execute(f"SELECT call_id FROM {table} WHERE run_id=? AND wake_id=?",
                                              (run_id, wake_id)).fetchone()
                if existing is not None:
                    return existing["call_id"]
            open_count = (len(self._open(connection, agent_id))
                          + len(self._open_vol(connection, agent_id))
                          + len(self._open_option(connection, agent_id)))
            if open_count >= CALL_OPTIONS["max_open_per_agent"]:
                if kind == "vol":
                    _vol_entry(market, options, choice["symbol"], choice["expiry"], stamp)
                elif kind == "option":
                    _option_entry(market, options, choice["symbol"], choice["expiry"],
                                  choice["option_type"], choice["strike"], stamp)
                else:
                    _entry(market, choice["symbol"])
                raise CallRefused("call_too_many_open")
            call_id = self._next_call_id(connection)
            if kind == "vol":
                sealed = _vol_entry(market, options, choice["symbol"], choice["expiry"], stamp)
                connection.execute(
                    "INSERT INTO vol_calls (call_id, agent_id, run_id, wake_id, symbol, expiry, iv_view,"
                    " confidence, reason, entry_price, price_as_of, entry_iv, implied_move_pct,"
                    " trading_days, atm_strike, quote_time, feed, entry_session, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (call_id, agent_id, run_id, wake_id, choice["symbol"], choice["expiry"], choice["iv_view"],
                     choice["confidence"], choice.get("reason", ""), sealed["entry_price"], sealed["price_as_of"],
                     sealed["entry_iv"], sealed["implied_move_pct"], sealed["trading_days"],
                     sealed["atm_strike"], sealed["quote_time"], sealed["feed"],
                     sealed["entry_session"], stamp.isoformat()))
                return call_id
            if kind == "option":
                sealed = _option_entry(market, options, choice["symbol"], choice["expiry"],
                                       choice["option_type"], choice["strike"], stamp)
                connection.execute(
                    "INSERT INTO option_calls (call_id, agent_id, run_id, wake_id, contract, symbol, expiry,"
                    " option_type, strike, confidence, reason, entry_bid, entry_ask, spread_pct,"
                    " entry_iv, entry_delta, entry_underlying_price, price_as_of, quote_time, feed,"
                    " entry_session, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (call_id, agent_id, run_id, wake_id, sealed["contract"], choice["symbol"], choice["expiry"],
                     choice["option_type"], sealed["strike"], choice["confidence"], choice.get("reason", ""),
                     sealed["entry_bid"], sealed["entry_ask"], sealed["spread_pct"], sealed["entry_iv"],
                     sealed["entry_delta"], sealed["entry_underlying_price"], sealed["price_as_of"],
                     sealed["quote_time"], sealed["feed"], sealed["entry_session"], stamp.isoformat()))
                return call_id
            price, moment, status = _entry(market, choice["symbol"])
            connection.execute(
                "INSERT INTO calls (call_id, agent_id, run_id, wake_id, symbol, direction, horizon_days, confidence,"
                " reason, entry_price, price_as_of, window_status, entry_session, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (call_id, agent_id, run_id, wake_id, choice["symbol"], choice["direction"], choice["horizon_days"],
                 choice["confidence"], choice.get("reason", ""), price, moment.isoformat(), status,
                 _session(moment), stamp.isoformat()))
            return call_id

    @staticmethod
    def _open(connection, agent_id):
        return [dict(row) for row in connection.execute(
            "SELECT c.call_id, c.symbol, c.direction, c.horizon_days, c.confidence, c.entry_price,"
            " c.price_as_of, c.entry_session FROM calls c LEFT JOIN settlements s USING (call_id)"
            " WHERE c.agent_id=? AND s.call_id IS NULL ORDER BY c.call_id", (agent_id,))]

    @staticmethod
    def _open_vol(connection, agent_id):
        return [dict(row) for row in connection.execute(
            "SELECT v.call_id, v.symbol, v.expiry, v.iv_view, v.confidence, v.entry_price,"
            " v.entry_iv, v.implied_move_pct, v.trading_days, v.atm_strike, v.quote_time, v.entry_session"
            " FROM vol_calls v LEFT JOIN vol_settlements s USING (call_id)"
            " WHERE v.agent_id=? AND s.call_id IS NULL ORDER BY v.call_id", (agent_id,))]

    @staticmethod
    def _open_option(connection, agent_id):
        return [dict(row) for row in connection.execute(
            "SELECT o.call_id, o.contract, o.symbol, o.expiry, o.option_type, o.strike, o.confidence,"
            " o.entry_bid, o.entry_ask, o.spread_pct, o.entry_iv, o.entry_delta,"
            " o.entry_underlying_price, o.quote_time, o.entry_session"
            " FROM option_calls o LEFT JOIN option_settlements s USING (call_id)"
            " WHERE o.agent_id=? AND s.call_id IS NULL ORDER BY o.call_id", (agent_id,))]

    def open_calls(self, agent_id):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "calls"):
                return []
            return self._open(connection, agent_id)

    def open_vol_calls(self, agent_id):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "vol_calls"):
                return []
            return self._open_vol(connection, agent_id)

    def open_option_calls(self, agent_id):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "option_calls"):
                return []
            return self._open_option(connection, agent_id)

    def all_open(self):
        """Every agent's open stock calls, oldest first, for settling."""
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "calls"):
                return []
            return [dict(row) for row in connection.execute(
                "SELECT c.call_id, c.agent_id, c.symbol, c.direction, c.horizon_days, c.entry_price,"
                " c.entry_session FROM calls c LEFT JOIN settlements s USING (call_id)"
                " WHERE s.call_id IS NULL ORDER BY c.call_id")]

    def all_open_vol(self):
        """Every agent's open volatility calls, oldest first, for settling."""
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "vol_calls"):
                return []
            return [dict(row) for row in connection.execute(
                "SELECT v.call_id, v.agent_id, v.symbol, v.expiry, v.iv_view, v.entry_price,"
                " v.entry_iv, v.implied_move_pct, v.entry_session FROM vol_calls v"
                " LEFT JOIN vol_settlements s USING (call_id) WHERE s.call_id IS NULL ORDER BY v.call_id")]

    def all_open_option(self):
        """Every agent's open option calls, oldest first, for settling."""
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "option_calls"):
                return []
            return [dict(row) for row in connection.execute(
                "SELECT o.call_id, o.agent_id, o.contract, o.symbol, o.expiry, o.option_type, o.strike,"
                " o.entry_ask, o.spread_pct, o.entry_underlying_price, o.entry_session FROM option_calls o"
                " LEFT JOIN option_settlements s USING (call_id) WHERE s.call_id IS NULL ORDER BY o.call_id")]

    def has_open(self):
        return bool(self.all_open() or self.all_open_vol() or self.all_open_option())

    def settle(self, call_id, detail, *, now):
        """Write one stock settlement. A call already settled is left as it was."""
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO settlements (call_id, settled_at, detail) VALUES (?,?,?)",
                (call_id, now.astimezone(timezone.utc).isoformat(), json.dumps(detail, sort_keys=True)))
            return cursor.rowcount == 1

    def settle_vol(self, call_id, detail, *, now):
        """Write one volatility settlement. A call already settled is left as it was."""
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO vol_settlements (call_id, settled_at, detail) VALUES (?,?,?)",
                (call_id, now.astimezone(timezone.utc).isoformat(), json.dumps(detail, sort_keys=True)))
            return cursor.rowcount == 1

    def settle_option(self, call_id, detail, *, now):
        """Write one option settlement. A call already settled is left as it was."""
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO option_settlements (call_id, settled_at, detail) VALUES (?,?,?)",
                (call_id, now.astimezone(timezone.utc).isoformat(), json.dumps(detail, sort_keys=True)))
            return cursor.rowcount == 1

    def hand_back(self, agent_id, *, run_id, sitting, now):
        """This agent's settled calls still to show on this wake, newest first.

        Each result shows on at most HANDBACK_WAKES wakes (a wake of several
        moves counts once, by its first move), then drops out of routine
        context; the settlement itself stays in the record. Asking again for
        the same wake returns the same results."""
        if not self.path.exists():
            return []
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            specs = (
                ("stock", "calls", "settlements", "handbacks",
                 "c.call_id, c.symbol, c.direction, c.horizon_days, c.confidence, c.entry_price, c.entry_session"),
                ("vol", "vol_calls", "vol_settlements", "vol_handbacks",
                 "c.call_id, c.symbol, c.expiry, c.iv_view, c.confidence, c.entry_price,"
                 " c.entry_iv, c.implied_move_pct, c.entry_session"),
                ("option", "option_calls", "option_settlements", "option_handbacks",
                 "c.call_id, c.contract, c.symbol, c.expiry, c.option_type, c.strike, c.confidence,"
                 " c.entry_bid, c.entry_ask, c.spread_pct, c.entry_underlying_price, c.entry_session"),
            )
            candidates = []
            for kind, table, settle_table, handback_table, cols in specs:
                for raw in connection.execute(
                    f"SELECT {cols}, s.detail FROM {table} c JOIN {settle_table} s USING (call_id)"
                    f" WHERE c.agent_id=? AND (SELECT COUNT(*) FROM {handback_table} h WHERE h.call_id=c.call_id"
                    " AND NOT (h.run_id=? AND h.sitting=?)) < ? ORDER BY c.call_id DESC LIMIT ?",
                    (agent_id, run_id, sitting, HANDBACK_WAKES, MAX_HANDBACKS),
                ):
                    row = dict(raw)
                    row["kind"] = kind
                    row["_handback_table"] = handback_table
                    candidates.append(row)
            candidates.sort(key=lambda r: r["call_id"], reverse=True)
            rows = candidates[:MAX_HANDBACKS]
            stamp = now.astimezone(timezone.utc).isoformat()
            for row in rows:
                table = row.pop("_handback_table")
                connection.execute(f"INSERT OR IGNORE INTO {table} (call_id, run_id, sitting, shown_at)"
                                   " VALUES (?,?,?,?)", (row["call_id"], run_id, sitting, stamp))
                row["detail"] = json.loads(row["detail"])
            return rows

    def counts(self):
        """Per agent: open, settled, and each outcome. Counts only, never a reason."""
        if not self.path.exists():
            return {}
        result = {}
        with closing(self._reader()) as connection:
            for table, settle_table in (("calls", "settlements"), ("vol_calls", "vol_settlements"),
                                        ("option_calls", "option_settlements")):
                if not self._has_table(connection, table):
                    continue
                for row in connection.execute(f"SELECT c.agent_id, s.detail FROM {table} c LEFT JOIN {settle_table} s"
                                              " USING (call_id)"):
                    item = result.setdefault(row["agent_id"], dict(NO_CALLS))
                    if row["detail"] is None:
                        item["open"] += 1
                        continue
                    item["settled"] += 1
                    outcome = json.loads(row["detail"]).get("outcome")
                    if outcome in item:
                        item[outcome] += 1
        return result

    def settlements(self):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "settlements"):
                return []
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in connection.execute(
                "SELECT call_id, settled_at, detail FROM settlements ORDER BY call_id")]

    def vol_settlements(self):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "vol_settlements"):
                return []
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in connection.execute(
                "SELECT call_id, settled_at, detail FROM vol_settlements ORDER BY call_id")]

    def option_settlements(self):
        if not self.path.exists():
            return []
        with closing(self._reader()) as connection:
            if not self._has_table(connection, "option_settlements"):
                return []
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in connection.execute(
                "SELECT call_id, settled_at, detail FROM option_settlements ORDER BY call_id")]


# ---- Phase 2: settle (code only, no model, no cost) ----------------------
FLAT_PERCENT = Decimal("0.1")   # A smaller move is "flat": neither right nor wrong.
SETTLE_GRACE_SESSIONS = 5       # Trading days to wait for a missing close before "unsettled".
NO_DATA_WEEKDAY_SLACK = 2       # With no calendar at all, weekdays also cover a holiday or two.
YARDSTICK = "SPY"


def _percent(start, end):
    return ((end - start) / start * 100).quantize(Decimal("0.01"))


def _weekdays_after(entry_session, today):
    """Weekdays after the entry session up to and including ``today``."""
    from datetime import date
    day, count = date.fromisoformat(entry_session), 0
    end = date.fromisoformat(today)
    while day < end:
        day += timedelta(days=1)
        count += day.weekday() < 5
    return count


def settle_call(call, closes, sessions, today):
    """Decide one open call. Pure: no clock, no network.

    ``closes`` maps symbol -> {session: Decimal} (None when market data was
    unavailable); ``sessions`` are the completed trading sessions those closes
    cover. Returns ("open", None) when the horizon has not passed yet,
    ("pending", reason) when it has but the close is missing, or
    ("settled", detail) to write. Unknown is never 0: a missing figure is
    a reason, and a missing yardstick is left out rather than guessed."""
    entry = Decimal(call["entry_price"])
    after = [s for s in sessions if s > call["entry_session"]]
    if closes is None or not sessions:
        # No calendar from the data: count weekdays so an outage still ends one day.
        waited = _weekdays_after(call["entry_session"], today)
        if waited >= call["horizon_days"] + SETTLE_GRACE_SESSIONS + NO_DATA_WEEKDAY_SLACK:
            return "settled", {"outcome": "unsettled", "reason": "no market data reached the heartbeat"}
        return ("pending", "market data unavailable") if waited >= call["horizon_days"] else ("open", None)
    if len(after) < call["horizon_days"]:
        return "open", None
    exit_session = after[call["horizon_days"] - 1]
    price = closes.get(call["symbol"], {}).get(exit_session)
    if price is None:
        reason = f"no {call['symbol']} close for {exit_session}"
        if len(after) >= call["horizon_days"] + SETTLE_GRACE_SESSIONS:
            return "settled", {"outcome": "unsettled", "reason": reason, "exit_session": exit_session}
        return "pending", reason
    move = _percent(entry, price)
    if abs(move) < FLAT_PERCENT:
        outcome = "flat"
    else:
        outcome = "right" if (move > 0) == (call["direction"] == "up") else "wrong"
    detail = {"outcome": outcome, "exit_session": exit_session, "exit_price": format(price.normalize(), "f"),
              "move_percent": format(move, "f")}
    spy = closes.get(YARDSTICK, {})
    if call["entry_session"] in spy and exit_session in spy:
        detail["spy_move_percent"] = format(_percent(spy[call["entry_session"]], spy[exit_session]), "f")
    return "settled", detail


def _expiry_settlement_price(kind, symbol, expiry, closes, sessions, today):
    """Shared expiry close lookup with grace period. Returns (Decimal, None) or (None, (state, val))."""
    if closes is None or not sessions:
        if today < expiry:
            return None, ("open", None)
        if _weekdays_after(expiry, today) >= SETTLE_GRACE_SESSIONS + NO_DATA_WEEKDAY_SLACK:
            return None, ("settled", {"kind": kind, "outcome": "unsettled",
                                      "reason": "no market data reached the heartbeat"})
        return None, ("pending", "market data unavailable")
    if not any(s >= expiry for s in sessions):
        if today <= expiry:
            return None, ("open", None)
        reason = f"no {symbol} close for {expiry}"
        if _weekdays_after(expiry, today) >= SETTLE_GRACE_SESSIONS:
            return None, ("settled", {"kind": kind, "outcome": "unsettled", "reason": reason, "exit_session": expiry})
        return None, ("pending", reason)
    price = closes.get(symbol, {}).get(expiry)
    if price is None:
        reason = f"no {symbol} close for {expiry}"
        if len([s for s in sessions if s > expiry]) >= SETTLE_GRACE_SESSIONS:
            return None, ("settled", {"kind": kind, "outcome": "unsettled", "reason": reason, "exit_session": expiry})
        return None, ("pending", reason)
    return price, None


def settle_vol_call(call, closes, sessions, today):
    """Decide one open volatility call against expiry close. Pure: no clock, no network."""
    entry = Decimal(call["entry_price"])
    expiry = call["expiry"]
    price, early = _expiry_settlement_price("vol", call["symbol"], expiry, closes, sessions, today)
    if early is not None:
        return early
    signed_move = _percent(entry, price)
    actual_move = abs(signed_move)
    implied_move = Decimal(call["implied_move_pct"])
    diff = actual_move - implied_move
    if abs(diff) <= VOL_DEADBAND:
        outcome = "flat"
    elif call["iv_view"] == "high":
        outcome = "right" if diff < 0 else "wrong"
    else:
        outcome = "right" if diff > 0 else "wrong"
    detail = {
        "kind": "vol",
        "outcome": outcome,
        "exit_session": expiry,
        "exit_price": format(price.normalize(), "f"),
        "signed_move_percent": format(signed_move, "f"),
        "actual_move_percent": format(actual_move, "f"),
        "implied_move_percent": call["implied_move_pct"],
        "entry_iv": call["entry_iv"],
    }
    spy = closes.get(YARDSTICK, {})
    if call["entry_session"] in spy and expiry in spy:
        detail["spy_move_percent"] = format(_percent(spy[call["entry_session"]], spy[expiry]), "f")
    return "settled", detail


def settle_option_call(call, closes, sessions, today):
    """Decide one open single-leg option call against expiry intrinsic value minus entry ask."""
    expiry = call["expiry"]
    price, early = _expiry_settlement_price("option", call["symbol"], expiry, closes, sessions, today)
    if early is not None:
        return early
    strike = Decimal(call["strike"])
    ask = Decimal(call["entry_ask"])
    entry_underlying = Decimal(call["entry_underlying_price"])
    intrinsic = max(Decimal("0"), price - strike) if call["option_type"] == "call" else max(Decimal("0"), strike - price)
    net_pnl = intrinsic - ask
    return_pct = (net_pnl / ask * Decimal("100")).quantize(Decimal("0.01"))
    if abs(net_pnl) <= OPTION_DEADBAND:
        outcome = "flat"
    else:
        outcome = "right" if net_pnl > OPTION_DEADBAND else "wrong"
    detail = {
        "kind": "option",
        "outcome": outcome,
        "exit_session": expiry,
        "exit_underlying": format(price.normalize(), "f"),
        "intrinsic": format(intrinsic.normalize(), "f"),
        "entry_ask": call["entry_ask"],
        "net_pnl": format(net_pnl.normalize(), "f"),
        "return_percent": format(return_pct, "f"),
        "spread_percent": call["spread_pct"],
        "underlying_move_percent": format(_percent(entry_underlying, price), "f"),
    }
    spy = closes.get(YARDSTICK, {})
    if call["entry_session"] in spy and expiry in spy:
        detail["spy_move_percent"] = format(_percent(spy[call["entry_session"]], spy[expiry]), "f")
    return "settled", detail


def settle_open_calls(store, fetch, *, now, today, completed):
    """Settle every open stock, volatility, and option call whose horizon/expiry has passed.

    ``fetch(symbols, start, end)`` returns the fetch_closes record.
    ``completed(session)`` says whether that session has closed, so today's
    still-moving bar is never used. Returns a short summary for the heartbeat."""
    calls = store.all_open()
    vol_calls = store.all_open_vol()
    option_calls = store.all_open_option()
    if not calls and not vol_calls and not option_calls:
        return {"open": 0, "settled": 0, "pending": []}
    all_rows = calls + vol_calls + option_calls
    symbols = sorted({c["symbol"] for c in all_rows} | {YARDSTICK})
    record = fetch(symbols, min(c["entry_session"] for c in all_rows), today)
    closes = record.get("closes") if isinstance(record, dict) and record.get("status") == "ok" else None
    sessions = sorted({s for by_day in (closes or {}).values() for s in by_day if completed(s)})
    if closes is not None:
        closes = {symbol: {s: p for s, p in by_day.items() if completed(s)} for symbol, by_day in closes.items()}
    settled, pending = 0, []
    for call in calls:
        state, value = settle_call(call, closes, sessions, today)
        if state == "settled":
            settled += store.settle(call["call_id"], value, now=now)
        elif state == "pending":
            pending.append(f"{call['agent_id']} call {call['call_id']}: {value}")
    for call in vol_calls:
        state, value = settle_vol_call(call, closes, sessions, today)
        if state == "settled":
            settled += store.settle_vol(call["call_id"], value, now=now)
        elif state == "pending":
            pending.append(f"{call['agent_id']} vol call {call['call_id']}: {value}")
    for call in option_calls:
        state, value = settle_option_call(call, closes, sessions, today)
        if state == "settled":
            settled += store.settle_option(call["call_id"], value, now=now)
        elif state == "pending":
            pending.append(f"{call['agent_id']} option call {call['call_id']}: {value}")
    summary = {"open": len(all_rows) - settled, "settled": settled, "pending": pending}
    if closes is None:
        summary["unavailable"] = (record or {}).get("reason") or "market data unavailable"
    return summary


HANDBACK_WAKES = 2   # A result is shown on this many wakes, then stays only in the record.
MAX_HANDBACKS = 5    # At most this many results on one page, newest first.


def _signed(text):
    return text if text.startswith("-") else "+" + text


def _format_vol_result(r, d):
    iv_pct = format((Decimal(r["entry_iv"]) * Decimal("100")).quantize(Decimal("0.1")), "f")
    made = (f"vol call {r['call_id']}: {r['symbol']} {r['expiry']} options priced "
            f"+/-{r['implied_move_pct']}% (IV {iv_pct}%, {r['iv_view']}), "
            f"made {r['entry_session']} at {r['entry_price']} ({r['confidence']})")
    if d.get("outcome") == "unsettled":
        return f"{made}. Could not be settled: {d.get('reason') or 'no closing price'}."
    spy = f", SPY {_signed(d['spy_move_percent'])}%" if "spy_move_percent" in d else ", SPY unknown"
    return (f"{made}. Settled {d['exit_session']} at {d['exit_price']}: "
            f"{r['symbol']} moved {_signed(d['signed_move_percent'])}%{spy}. {d['outcome'].capitalize()}.")


def _format_option_result(r, d):
    made = (f"option call {r['call_id']}: long {r['symbol']} {r['expiry']} {r['strike']} {r['option_type']} "
            f"at {r['entry_ask']} ask (indicative, spread {r['spread_pct']}%), "
            f"made {r['entry_session']} ({r['symbol']} {r['entry_underlying_price']}, {r['confidence']})")
    if d.get("outcome") == "unsettled":
        return f"{made}. Could not be settled: {d.get('reason') or 'no closing price'}."
    spy = f", SPY {_signed(d['spy_move_percent'])}%" if "spy_move_percent" in d else ", SPY unknown"
    return (f"{made}. Expiry close {d['exit_underlying']} -> intrinsic {d['intrinsic']} "
            f"({_signed(d['return_percent'])}%, {r['symbol']} {_signed(d['underlying_move_percent'])}%{spy}). "
            f"{d['outcome'].capitalize()}.")


def call_results_line(results):
    """Settled calls handed back to their agent as quoted data. Empty when none.

    Facts only: what was sealed, what the close was, and the outcome. What to
    make of it is the agent's own business; nothing here asks for a reply."""
    if not results:
        return ""
    parts = []
    for r in results:
        d = r["detail"]
        kind = r.get("kind") or d.get("kind") or "stock"
        if kind == "vol":
            parts.append(_format_vol_result(r, d))
            continue
        if kind == "option":
            parts.append(_format_option_result(r, d))
            continue
        made = (f"call {r['call_id']}: {r['symbol']} {r['direction']} within {r['horizon_days']} trading days"
                f" ({r['confidence']}), made {r['entry_session']} at {r['entry_price']}")
        if d.get("outcome") == "unsettled":
            parts.append(f"{made}. Could not be settled: {d.get('reason') or 'no closing price'}.")
            continue
        spy = f", SPY {_signed(d['spy_move_percent'])}%" if "spy_move_percent" in d else ", SPY unknown"
        parts.append(f"{made}. Settled {d['exit_session']} at {d['exit_price']}: "
                     f"{_signed(d['move_percent'])}%{spy}. {d['outcome'].capitalize()}.")
    return ("Results of your calls (quoted record, settled by plain code from closing prices; "
            f"each shows on {HANDBACK_WAKES} wakes, then stays in your record): " + " ".join(parts))


def open_calls_line(calls, vol_calls=(), option_calls=()):
    """The agent's own open calls, for its next choice. Empty when none."""
    if not calls and not vol_calls and not option_calls:
        return ""
    parts = [f"call {c['call_id']}: {c['symbol']} {c['direction']} within {c['horizon_days']} trading days"
             f" of {c['entry_session']} ({c['confidence']}), sealed at {c['entry_price']}" for c in calls]
    parts.extend(
        f"vol call {v['call_id']}: {v['symbol']} {v['expiry']} IV {v['iv_view']} "
        f"(priced +/-{v['implied_move_pct']}%, {v['confidence']}), made {v['entry_session']} at {v['entry_price']}"
        for v in vol_calls
    )
    parts.extend(
        f"option call {o['call_id']}: long {o['symbol']} {o['expiry']} {o['strike']} {o['option_type']} "
        f"at {o['entry_ask']} ask (spread {o['spread_pct']}%, {o['confidence']}), "
        f"made {o['entry_session']} ({o['symbol']} {o['entry_underlying_price']})"
        for o in option_calls
    )
    total = len(calls) + len(vol_calls) + len(option_calls)
    return (f"Your open calls ({total} of {CALL_OPTIONS['max_open_per_agent']}; they settle after "
            "their horizon): " + "; ".join(parts) + ".")
