"""Private append-only request metadata ledger with exact partial-cost coverage.

Only explicit record/read operations open SQLite; imports and construction do
not create files. Every provider HTTP attempt is one event, including failures.
The adapter, not this ledger, decides whether an HTTP attempt actually happened.
No payload, prompt, query, response text, credentials or exception is persisted.

Reporting aggregates in SQL. Nullable token sums are known subtotals, not totals
for requests with missing usage; coverage counters make that distinction explicit.
Missing cost never becomes zero, including empty results. Group lists are capped
at 100, and groups_truncated flags any omitted groups. Reads never reprice rows.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock
from uuid import UUID, uuid4
import warnings

from .context import current_usage_context
from .pricing import (PricingTable, decimal_add, decimal_text, decimal_value,
                      get_default_pricing, validate_model, validate_provider)

_SAFE_ID = re.compile(r"[a-zA-Z0-9_.:-]{1,128}\Z")
_SAFE_LABEL = re.compile(r"[a-zA-Z0-9_.:-]{1,80}\Z")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
_OUTCOMES = frozenset({"success", "http_error", "transport_error", "invalid_response"})
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens")
_EVENT_FIELDS = (
    "event_id", "call_id", "wake_id", "agent_id", "activity", "provider", "model", "response_model",
    "attempt", "created_at", "duration_ms", "outcome", "http_status", *_TOKEN_FIELDS,
    "provider_cost_usd", "cost_usd", "cost_status", "cost_scope", "cost_reason", "pricing_snapshot",
)


def _identifier(value, field: str, *, nullable: bool = False, short: bool = False):
    if value is None and nullable:
        return None
    pattern = _SAFE_LABEL if short else _SAFE_ID
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid {field}")
    return value


def _integer(value, field: str, minimum: int, maximum: int, nullable: bool = False):
    if value is None and nullable:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid {field}")
    return value


def normalize_timestamp(value, field: str = "created_at") -> str:
    """Accept timezone-aware ISO seconds and normalize to sortable UTC text."""
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise ValueError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, OverflowError):
        raise ValueError(f"invalid {field}") from None


def _normalize_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("invalid usage event")
    context = current_usage_context()
    event = {}
    event_id = raw.get("event_id", str(uuid4()))
    if not isinstance(event_id, str) or len(event_id) > 36:
        raise ValueError("invalid event_id")
    try:
        event["event_id"] = str(UUID(event_id))
    except (ValueError, AttributeError):
        raise ValueError("invalid event_id") from None
    event["call_id"] = _identifier(raw.get("call_id"), "call_id")
    event["wake_id"] = _identifier(raw.get("wake_id", context["wake_id"]), "wake_id", nullable=True)
    event["agent_id"] = _identifier(raw.get("agent_id"), "agent_id", nullable=True, short=True)
    event["activity"] = _identifier(raw.get("activity", context["activity"]), "activity", short=True)
    event["provider"] = validate_provider(raw.get("provider"))
    event["model"] = validate_model(raw.get("model"))
    response_model = raw.get("response_model")
    event["response_model"] = None if response_model is None else validate_model(response_model)
    event["attempt"] = _integer(raw.get("attempt"), "attempt", 1, 100)
    created_at = raw.get("created_at", datetime.now(timezone.utc).isoformat())
    event["created_at"] = normalize_timestamp(created_at)
    duration = raw.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("invalid duration_ms")
    try:
        duration = float(duration)
    except (ValueError, OverflowError):
        raise ValueError("invalid duration_ms") from None
    if not math.isfinite(duration) or not 0 <= duration <= 86_400_000:
        raise ValueError("invalid duration_ms")
    event["duration_ms"] = duration
    outcome = raw.get("outcome")
    if not isinstance(outcome, str) or outcome not in _OUTCOMES:
        raise ValueError("invalid outcome")
    event["outcome"] = outcome
    event["http_status"] = _integer(raw.get("http_status"), "http_status", 100, 599, nullable=True)
    for field in _TOKEN_FIELDS:
        event[field] = _integer(raw.get(field), field, 0, 10_000_000_000, nullable=True)
    if (event["cached_input_tokens"] is not None and event["input_tokens"] is not None
            and event["cached_input_tokens"] > event["input_tokens"]):
        raise ValueError("invalid cached_input_tokens")
    if (event["reasoning_tokens"] is not None and event["output_tokens"] is not None
            and event["reasoning_tokens"] > event["output_tokens"]):
        raise ValueError("invalid reasoning_tokens")
    cost = raw.get("provider_cost_usd")
    event["provider_cost_usd"] = None if cost is None else decimal_text(decimal_value(cost, "provider_cost_usd"))
    # Deliberately construct an allowlist; never serialize the input dictionary.
    return event


class _DecimalSum:
    def __init__(self):
        self.total = None

    def step(self, value):
        if value is not None:
            amount = Decimal(value)
            self.total = amount if self.total is None else decimal_add(self.total, amount)

    def finalize(self):
        return None if self.total is None else decimal_text(self.total)


_SUMMARY_SQL = """
COUNT(*) AS requests,
COALESCE(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END), 0) AS successful_requests,
COALESCE(SUM(CASE WHEN outcome != 'success' THEN 1 ELSE 0 END), 0) AS failed_requests,
decimal_sum(CASE WHEN cost_status = 'reported' THEN cost_usd END) AS reported_cost_usd,
decimal_sum(CASE WHEN cost_status = 'estimated' THEN cost_usd END) AS estimated_cost_usd,
COALESCE(SUM(CASE WHEN cost_status = 'reported' THEN 1 ELSE 0 END), 0) AS reported_cost_requests,
COALESCE(SUM(CASE WHEN cost_status = 'estimated' THEN 1 ELSE 0 END), 0) AS estimated_cost_requests,
COALESCE(SUM(CASE WHEN cost_status = 'unknown' THEN 1 ELSE 0 END), 0) AS unknown_cost_requests,
SUM(input_tokens) AS input_tokens,
SUM(output_tokens) AS output_tokens,
SUM(cached_input_tokens) AS cached_input_tokens,
SUM(reasoning_tokens) AS reasoning_tokens,
COALESCE(SUM(CASE WHEN input_tokens IS NOT NULL AND output_tokens IS NOT NULL THEN 1 ELSE 0 END), 0) AS usage_known_requests,
COALESCE(SUM(CASE WHEN input_tokens IS NULL OR output_tokens IS NULL THEN 1 ELSE 0 END), 0) AS usage_unknown_requests
"""


class UsageStore:
    """Metadata-only SQLite store. An explicit path is useful for offline tests.

    Optional pricing_table is a fixed local snapshot. With no override, each
    record loads optional local pricing afresh, permitting operator updates
    without changing historical rows. Initialization is lazy, even on reads.
    """

    def __init__(self, db_path: str | Path, pricing_table: PricingTable | None = None):
        self.db_path = str(db_path)
        if pricing_table is not None and not isinstance(pricing_table, PricingTable):
            raise ValueError("invalid pricing table")
        self.pricing_table = pricing_table
        self._initialized = False
        self._init_lock = Lock()

    @contextmanager
    def _connection(self):
        with self._init_lock:
            if not self._initialized:
                path = Path(self.db_path)
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                try:
                    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    pass
                else:
                    os.close(fd)
                conn = sqlite3.connect(self.db_path, timeout=10)
                try:
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS usage_events (
                            event_id TEXT PRIMARY KEY,
                            call_id TEXT NOT NULL,
                            wake_id TEXT,
                            agent_id TEXT,
                            activity TEXT NOT NULL,
                            provider TEXT NOT NULL,
                            model TEXT NOT NULL,
                            response_model TEXT,
                            attempt INTEGER NOT NULL,
                            created_at TEXT NOT NULL,
                            duration_ms REAL NOT NULL,
                            outcome TEXT NOT NULL,
                            http_status INTEGER,
                            input_tokens INTEGER,
                            output_tokens INTEGER,
                            cached_input_tokens INTEGER,
                            reasoning_tokens INTEGER,
                            total_tokens INTEGER,
                            provider_cost_usd TEXT,
                            cost_usd TEXT,
                            cost_status TEXT NOT NULL,
                            cost_scope TEXT,
                            cost_reason TEXT,
                            pricing_snapshot TEXT,
                            UNIQUE(provider, call_id, attempt)
                        );
                        CREATE INDEX IF NOT EXISTS usage_events_time
                            ON usage_events(created_at DESC, event_id DESC);
                        CREATE INDEX IF NOT EXISTS usage_events_agent_time
                            ON usage_events(agent_id, created_at DESC, event_id DESC);
                        CREATE TRIGGER IF NOT EXISTS usage_events_no_update
                            BEFORE UPDATE ON usage_events BEGIN
                            SELECT RAISE(ABORT, 'usage events are immutable'); END;
                        CREATE TRIGGER IF NOT EXISTS usage_events_no_delete
                            BEFORE DELETE ON usage_events BEGIN
                            SELECT RAISE(ABORT, 'usage events are immutable'); END;
                    """)
                    conn.commit()
                    self._initialized = True
                finally:
                    conn.close()
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.create_aggregate("decimal_sum", 1, _DecimalSum)
        try:
            yield conn
        finally:
            conn.close()

    def record(self, event: dict) -> str:
        """Validate and append once, returning the persisted event UUID.

        Duplicate event IDs or provider/call/attempt keys return the original
        ID without overwriting it. Failures raise; record_usage is the adapter's
        best-effort boundary and must never cause a provider request replay.
        """
        normalized = _normalize_event(event)
        table = self.pricing_table if self.pricing_table is not None else get_default_pricing()
        normalized.update(table.resolve(normalized))
        values = [normalized.get(field) for field in _EVENT_FIELDS]
        snapshot_index = _EVENT_FIELDS.index("pricing_snapshot")
        if values[snapshot_index] is not None:
            values[snapshot_index] = json.dumps(values[snapshot_index], sort_keys=True, separators=(",", ":"))
        with self._connection() as conn:
            with conn:
                cursor = conn.execute(
                    f"INSERT INTO usage_events ({','.join(_EVENT_FIELDS)}) VALUES ({','.join('?' for _ in _EVENT_FIELDS)}) ON CONFLICT DO NOTHING",
                    values,
                )
                if cursor.rowcount:
                    return normalized["event_id"]
                row = conn.execute(
                    "SELECT event_id FROM usage_events WHERE event_id = ? OR (provider = ? AND call_id = ? AND attempt = ?) ORDER BY CASE WHEN event_id = ? THEN 0 ELSE 1 END LIMIT 1",
                    (normalized["event_id"], normalized["provider"], normalized["call_id"], normalized["attempt"], normalized["event_id"]),
                ).fetchone()
                return row["event_id"]

    @staticmethod
    def _filters(agent_id=None, since=None, until=None):
        agent_id = _identifier(agent_id, "agent_id", nullable=True, short=True)
        since = None if since is None else normalize_timestamp(since, "since")
        until = None if until is None else normalize_timestamp(until, "until")
        if since is not None and until is not None and since > until:
            raise ValueError("invalid time range")
        filters = {"agent_id": agent_id, "since": since, "until": until}
        clauses, parameters = [], []
        if agent_id is not None:
            clauses.append("agent_id = ?")
            parameters.append(agent_id)
        if since is not None:
            clauses.append("created_at >= ?")
            parameters.append(since)
        if until is not None:
            clauses.append("created_at < ?")
            parameters.append(until)
        return filters, (" WHERE " + " AND ".join(clauses) if clauses else ""), parameters

    def list_events(self, agent_id=None, limit=50, offset=0, since=None, until=None) -> dict:
        """Bounded metadata page ordered by newest UTC time, then event UUID."""
        limit = _integer(limit, "limit", 1, 100)
        offset = _integer(offset, "offset", 0, 2_147_483_647)
        filters, where, parameters = self._filters(agent_id, since, until)
        with self._connection() as conn:
            # One read transaction ensures total and page use the same snapshot.
            conn.execute("BEGIN")
            total = conn.execute("SELECT COUNT(*) AS total FROM usage_events" + where, parameters).fetchone()["total"]
            rows = conn.execute(
                f"SELECT {','.join(_EVENT_FIELDS)} FROM usage_events" + where
                + " ORDER BY created_at DESC, event_id DESC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            if event["pricing_snapshot"] is not None:
                event["pricing_snapshot"] = json.loads(event["pricing_snapshot"])
            events.append(event)
        return {"status": "ok", "events": events, "total": total, "offset": offset,
                "limit": limit, "filters": filters}

    def summary(self, agent_id=None, since=None, until=None) -> dict:
        """SQL aggregate known subtotals and coverage; cap each grouping at 100."""
        filters, where, parameters = self._filters(agent_id, since, until)
        result = {"status": "ok", "currency": "USD", "filters": filters}
        truncated = {}
        with self._connection() as conn:
            conn.execute("BEGIN")
            result["summary"] = dict(conn.execute("SELECT " + _SUMMARY_SQL + " FROM usage_events" + where, parameters).fetchone())
            for dimension, key in (("agent_id", "by_agent"), ("provider", "by_provider"), ("activity", "by_activity")):
                # Fetch one sentinel group, never fetch all events into Python.
                groups = conn.execute(
                    f"SELECT {dimension}, {_SUMMARY_SQL} FROM usage_events" + where
                    + f" GROUP BY {dimension} ORDER BY requests DESC, {dimension} ASC LIMIT 101",
                    parameters,
                ).fetchall()
                result[key] = [dict(row) for row in groups[:100]]
                truncated[key] = len(groups) > 100
        result["groups_truncated"] = any(truncated.values())
        return result


_default_store: UsageStore | None = None
_default_store_lock = Lock()


def get_usage_store() -> UsageStore:
    """Lazy singleton using the dedicated private db_path('usage.sqlite3')."""
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                from core.data_dir import db_path
                _default_store = UsageStore(db_path("usage.sqlite3"))
    return _default_store


def record_usage(event: dict) -> bool:
    """Best effort: metadata failure is visible, never leaks or replays calls.

    Catch ordinary exceptions only; interrupts/cancellation retain their normal
    semantics. Warning text is fixed and bounded and contains no raw exception.
    Even warning-as-error policy must not turn accounting into a provider retry.
    """
    try:
        get_usage_store().record(event)
        return True
    except Exception:
        try:
            warnings.warn("usage_recording_failed", RuntimeWarning, stacklevel=2)
        except Exception:
            pass
        return False
