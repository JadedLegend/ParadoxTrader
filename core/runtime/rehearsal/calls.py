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
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import sqlite3
from zoneinfo import ZoneInfo

CALLS_FILE = "calls.sqlite3"
CALL_OPTIONS = {
    "directions": ["up", "down"],
    "min_horizon_days": 1, "max_horizon_days": 20, "horizon_unit": "trading_days",
    "confidences": ["low", "medium", "high"],
    "max_reason_chars": 400, "max_open_per_agent": 5,
    "symbols": "this wake's market window",
}
CALL_FIELDS = ("symbol", "direction", "horizon_days", "confidence", "reason")
_SYMBOL = re.compile(r"[A-Z]{1,5}(?:[.][A-Z]{1,2})?")
_EASTERN = ZoneInfo("America/New_York")

CALL_INSTRUCTIONS = (
    "\nCALL (offered on this wake): you may instead choose action call to write down one "
    "forecast, sealed with the price you were shown below. Fields: symbol (a ticker in this "
    "wake's window), direction up|down, horizon_days an integer 1-20 (trading days), "
    "confidence low|medium|high, and an optional reason of at most 400 characters. "
    # A shape, not sample values: a concrete example would be copied by every agent.
    "Shape: {\"action\":\"call\",\"symbol\":<ticker>,\"direction\":<up|down>,\"horizon_days\":<1-20>,"
    "\"confidence\":<low|medium|high>,\"reason\":<your words>}. A call is a forecast, not a trade: it buys "
    "nothing. After the horizon, the actual close is recorded beside it and shown to you. "
    "It can never be edited; a changed view is a new call or a journal note. At most five "
    "open calls per agent. No call is owed."
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
"""


class CallRefused(ValueError):
    """A call the runtime declines, with a short code for the wake record."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def validate_call_fields(value):
    """Shape only. Raises ValueError; the ticker is checked against the window later."""
    if value.get("action") != "call":
        if set(value) & set(CALL_FIELDS):
            raise ValueError("invalid call fields")
        return
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


class CallStore:
    def __init__(self, path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.executescript(_SCHEMA)
        return connection

    def record(self, *, agent_id, run_id, wake_id, choice, market, now=None):
        """Seal one call. Retrying the same wake returns the same call."""
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT call_id FROM calls WHERE run_id=? AND wake_id=?",
                                          (run_id, wake_id)).fetchone()
            if existing is not None:
                return existing["call_id"]
            price, moment, status = _entry(market, choice["symbol"])
            if len(self._open(connection, agent_id)) >= CALL_OPTIONS["max_open_per_agent"]:
                raise CallRefused("call_too_many_open")
            cursor = connection.execute(
                "INSERT INTO calls (agent_id, run_id, wake_id, symbol, direction, horizon_days, confidence,"
                " reason, entry_price, price_as_of, window_status, entry_session, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (agent_id, run_id, wake_id, choice["symbol"], choice["direction"], choice["horizon_days"],
                 choice["confidence"], choice.get("reason", ""), price, moment.isoformat(), status,
                 moment.astimezone(_EASTERN).date().isoformat(), stamp.isoformat()))
            return cursor.lastrowid

    @staticmethod
    def _open(connection, agent_id):
        return [dict(row) for row in connection.execute(
            "SELECT c.call_id, c.symbol, c.direction, c.horizon_days, c.confidence, c.entry_price,"
            " c.price_as_of, c.entry_session FROM calls c LEFT JOIN settlements s USING (call_id)"
            " WHERE c.agent_id=? AND s.call_id IS NULL ORDER BY c.call_id", (agent_id,))]

    def open_calls(self, agent_id):
        if not self.path.exists():
            return []
        with closing(self._connect()) as connection:
            return self._open(connection, agent_id)


def open_calls_line(calls):
    """The agent's own open calls, for its next choice. Empty when none."""
    if not calls:
        return ""
    parts = [f"call {c['call_id']}: {c['symbol']} {c['direction']} within {c['horizon_days']} trading days"
             f" of {c['entry_session']} ({c['confidence']}), sealed at {c['entry_price']}" for c in calls]
    return (f"Your open calls ({len(calls)} of {CALL_OPTIONS['max_open_per_agent']}; they settle after "
            "their horizon): " + "; ".join(parts) + ".")
