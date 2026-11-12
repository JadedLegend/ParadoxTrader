"""A persistent, explicitly local options venue simulator. Never a live adapter.

An explicit file path is mandatory. The three test-driver flags are persisted in
this *venue* database; this is not an approval queue. Every returned snapshot is a
fresh value read from SQLite, including after a process restart.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


class BrokerUnavailable(Exception):
    """The mock venue cannot authoritatively answer this operation."""


class BrokerConflict(Exception):
    """An invalid request or conflicting immutable client identity."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _price(value) -> Decimal:
    # Bound input and arithmetic before Decimal allocation/quantization. Prices
    # are USD/share, never float arithmetic; the same structure validator is used
    # by proposals and submissions.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise BrokerConflict("invalid mock fill price")
    text = str(value)
    if len(text) > 64:
        raise BrokerConflict("invalid mock fill price")
    if isinstance(value, str):
        from .lineage.validation import decimal_string
        try:
            text = decimal_string(value, "fill price")
        except ValueError:
            raise BrokerConflict("invalid mock fill price") from None
    try:
        price = Decimal(text)
    except InvalidOperation:
        raise BrokerConflict("invalid mock fill price") from None
    if not price.is_finite() or price <= 0 or price > Decimal("1000000"):
        raise BrokerConflict("invalid mock fill price")
    parts = price.as_tuple()
    scale = parts.exponent
    for digit in reversed(parts.digits):
        if digit:
            break
        scale += 1
    if scale < -8:
        raise BrokerConflict("invalid mock fill price precision")
    return price


def _decimal_text(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if value.as_tuple().exponent < 0 else format(value, "f")


def _structure(structure) -> dict:
    # Lazy import avoids constructor imports or any dependency on runtime,
    # provider accounts, configuration, or the legacy execution adapter.
    from .lineage.validation import validate_structure
    try:
        return validate_structure(structure)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise BrokerConflict("invalid mock order structure") from None
    except Exception as exc:
        from .lineage.errors import LineageError
        if isinstance(exc, LineageError):
            raise BrokerConflict("invalid mock order structure") from None
        raise


def _client_id(client_order_id) -> str:
    if not isinstance(client_order_id, str) or not client_order_id.strip() or len(client_order_id) > 128:
        raise BrokerConflict("invalid mock client order identity")
    return client_order_id


class MockBroker:
    """Separate SQLite venue with transactional order/fill idempotency.

    ``reject_next`` durably rejects the next *new* valid submission.
    ``fail_after_accept_once`` commits the next new accepted order, then raises
    BrokerUnavailable to emulate a lost acknowledgement. ``unavailable`` raises
    before any lookup/submission/cancellation/fill, without adding an order.
    Flags can be cleared explicitly after restart. No default database exists.
    """

    def __init__(self, db_path):
        raw = os.fspath(db_path)
        if not isinstance(raw, str) or not raw.strip() or raw == ":memory:" or raw.startswith("file:"):
            raise ValueError("MockBroker requires an explicit persistent file path")
        self.db_path = Path(raw)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.db_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        with self._transaction() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS mock_venue_orders (
                client_order_id TEXT PRIMARY KEY, broker_order_id TEXT NOT NULL UNIQUE,
                structure_json TEXT NOT NULL, status TEXT NOT NULL,
                revision INTEGER NOT NULL, qty INTEGER NOT NULL,
                filled_qty INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS mock_venue_fills (
                fill_id TEXT PRIMARY KEY, client_order_id TEXT NOT NULL,
                sequence INTEGER NOT NULL, qty INTEGER NOT NULL,
                price TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(client_order_id, sequence),
                FOREIGN KEY(client_order_id) REFERENCES mock_venue_orders(client_order_id)
            )""")
            for action in ("UPDATE", "DELETE"):
                conn.execute(f"CREATE TRIGGER IF NOT EXISTS mock_venue_fills_no_{action.lower()} "
                             f"BEFORE {action} ON mock_venue_fills BEGIN "
                             "SELECT RAISE(ABORT, 'mock fills are immutable'); END")
            conn.execute("""CREATE TABLE IF NOT EXISTS mock_venue_controls (
                name TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0, 1))
            )""")
            for flag in ("reject_next", "fail_after_accept_once", "unavailable"):
                conn.execute("INSERT OR IGNORE INTO mock_venue_controls VALUES (?, 0)", (flag,))

    @contextmanager
    def _transaction(self):
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _flag(conn, name):
        return bool(conn.execute("SELECT enabled FROM mock_venue_controls WHERE name = ?", (name,)).fetchone()[0])

    def _get_flag(self, name):
        with self._transaction() as conn:
            return self._flag(conn, name)

    def _set_flag(self, name, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("mock fault flags require bool")
        with self._transaction() as conn:
            conn.execute("UPDATE mock_venue_controls SET enabled = ? WHERE name = ?", (int(enabled), name))

    reject_next = property(lambda self: self._get_flag("reject_next"), lambda self, value: self._set_flag("reject_next", value))
    fail_after_accept_once = property(lambda self: self._get_flag("fail_after_accept_once"), lambda self, value: self._set_flag("fail_after_accept_once", value))
    unavailable = property(lambda self: self._get_flag("unavailable"), lambda self, value: self._set_flag("unavailable", value))

    def _check_available(self, conn):
        if self._flag(conn, "unavailable"):
            raise BrokerUnavailable("mock venue unavailable")

    @staticmethod
    def _row(conn, client_order_id):
        return conn.execute("SELECT * FROM mock_venue_orders WHERE client_order_id = ?", (client_order_id,)).fetchone()

    @classmethod
    def _snapshot(cls, conn, row):
        fills = conn.execute(
            "SELECT fill_id, qty, price, created_at FROM mock_venue_fills WHERE client_order_id = ? ORDER BY sequence",
            (row["client_order_id"],),
        ).fetchall()
        return {
            "broker": "mock", "client_order_id": row["client_order_id"],
            "broker_order_id": row["broker_order_id"], "status": row["status"],
            "revision": row["revision"], "structure": json.loads(row["structure_json"]),
            "qty": row["qty"], "filled_qty": row["filled_qty"],
            "fills": [dict(fill) for fill in fills],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def lookup_order(self, client_order_id):
        client_order_id = _client_id(client_order_id)
        with self._transaction() as conn:
            self._check_available(conn)
            row = self._row(conn, client_order_id)
            return None if row is None else self._snapshot(conn, row)

    def submit_order(self, client_order_id, structure):
        client_order_id = _client_id(client_order_id)
        lost_ack = False
        with self._transaction() as conn:
            self._check_available(conn)
            normalized = _structure(structure)
            payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
            row = self._row(conn, client_order_id)
            if row is not None:
                if row["structure_json"] != payload:
                    raise BrokerConflict("mock client identity already has a different request")
                return self._snapshot(conn, row)
            rejected = self._flag(conn, "reject_next")
            now = _timestamp()
            conn.execute("INSERT INTO mock_venue_orders VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)", (
                client_order_id, str(uuid4()), payload, "rejected" if rejected else "accepted",
                normalized["qty"], now, now,
            ))
            if rejected:
                conn.execute("UPDATE mock_venue_controls SET enabled = 0 WHERE name = 'reject_next'")
            elif self._flag(conn, "fail_after_accept_once"):
                conn.execute("UPDATE mock_venue_controls SET enabled = 0 WHERE name = 'fail_after_accept_once'")
                lost_ack = True
            snapshot = self._snapshot(conn, self._row(conn, client_order_id))
        # Crucially outside the transaction: accepted intent survives lost ACK.
        if lost_ack:
            raise BrokerUnavailable("mock submission acknowledgement unavailable")
        return snapshot

    def cancel_order(self, client_order_id):
        client_order_id = _client_id(client_order_id)
        with self._transaction() as conn:
            self._check_available(conn)
            row = self._row(conn, client_order_id)
            if row is None:
                return None  # Authoritative absence, not an empty canceled order.
            if row["status"] not in ("filled", "rejected", "canceled"):
                conn.execute("UPDATE mock_venue_orders SET status = 'canceled', revision = revision + 1, updated_at = ? WHERE client_order_id = ?", (_timestamp(), client_order_id))
            return self._snapshot(conn, self._row(conn, client_order_id))

    def fill_order(self, client_order_id, qty, price):
        client_order_id = _client_id(client_order_id)
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise BrokerConflict("mock fills require positive whole contracts")
        execution_price = _price(price)
        with self._transaction() as conn:
            self._check_available(conn)
            row = self._row(conn, client_order_id)
            if row is None:
                raise BrokerConflict("mock order not found")
            if row["status"] in ("rejected", "canceled", "filled"):
                raise BrokerConflict("mock order is final")
            new_qty = row["filled_qty"] + qty
            if new_qty > row["qty"]:
                raise BrokerConflict("mock fill exceeds order quantity")
            structure = json.loads(row["structure_json"])
            limit = _price(structure["limit_price"])
            if (structure["side"] == "buy" and execution_price > limit) or (structure["side"] == "sell" and execution_price < limit):
                raise BrokerConflict("mock fill violates limit price")
            now = _timestamp()
            conn.execute("INSERT INTO mock_venue_fills VALUES (?, ?, ?, ?, ?, ?)", (
                str(uuid4()), client_order_id, row["revision"], qty, _decimal_text(execution_price), now,
            ))
            conn.execute("UPDATE mock_venue_orders SET status = ?, revision = revision + 1, filled_qty = ?, updated_at = ? WHERE client_order_id = ?", (
                "filled" if new_qty == row["qty"] else "partially_filled", new_qty, now, client_order_id,
            ))
            return self._snapshot(conn, self._row(conn, client_order_id))
