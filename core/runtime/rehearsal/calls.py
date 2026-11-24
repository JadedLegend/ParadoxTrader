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
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import re
import sqlite3

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
                 _session(moment), stamp.isoformat()))
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

    def all_open(self):
        """Every agent's open calls, oldest first, for settling."""
        if not self.path.exists():
            return []
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT c.call_id, c.agent_id, c.symbol, c.direction, c.horizon_days, c.entry_price,"
                " c.entry_session FROM calls c LEFT JOIN settlements s USING (call_id)"
                " WHERE s.call_id IS NULL ORDER BY c.call_id")]

    def settle(self, call_id, detail, *, now):
        """Write one settlement. A call already settled is left as it was."""
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO settlements (call_id, settled_at, detail) VALUES (?,?,?)",
                (call_id, now.astimezone(timezone.utc).isoformat(), json.dumps(detail, sort_keys=True)))
            return cursor.rowcount == 1

    def settlements(self):
        if not self.path.exists():
            return []
        with closing(self._connect()) as connection:
            return [{**dict(row), "detail": json.loads(row["detail"])} for row in connection.execute(
                "SELECT call_id, settled_at, detail FROM settlements ORDER BY call_id")]


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


def settle_open_calls(store, fetch, *, now, today, completed):
    """Settle every open call whose horizon has passed.

    ``fetch(symbols, start, end)`` returns the fetch_closes record.
    ``completed(session)`` says whether that session has closed, so today's
    still-moving bar is never used. Returns a short summary for the heartbeat."""
    calls = store.all_open()
    if not calls:
        return {"open": 0, "settled": 0, "pending": []}
    symbols = sorted({c["symbol"] for c in calls} | {YARDSTICK})
    record = fetch(symbols, min(c["entry_session"] for c in calls), today)
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
    summary = {"open": len(calls) - settled, "settled": settled, "pending": pending}
    if closes is None:
        summary["unavailable"] = (record or {}).get("reason") or "market data unavailable"
    return summary


def open_calls_line(calls):
    """The agent's own open calls, for its next choice. Empty when none."""
    if not calls:
        return ""
    parts = [f"call {c['call_id']}: {c['symbol']} {c['direction']} within {c['horizon_days']} trading days"
             f" of {c['entry_session']} ({c['confidence']}), sealed at {c['entry_price']}" for c in calls]
    return (f"Your open calls ({len(calls)} of {CALL_OPTIONS['max_open_per_agent']}; they settle after "
            "their horizon): " + "; ".join(parts) + ".")
