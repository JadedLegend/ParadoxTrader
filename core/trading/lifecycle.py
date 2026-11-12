"""Explicit owner-side mock execution; never an agent loop or HTTP dispatcher.

Only the Alchemist pilot is supported. Queue authorization, durable intent,
closing reservations, fill identities and position projections belong solely to
LineageStore. Reconciliation reads an existing intent and never dispatches;
``submit`` is the explicit same-ID retry after authoritative venue absence.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .lineage.errors import LineageAccessError, LineageError
from .lineage.validation import integer, validate_structure
from .mock_broker import BrokerConflict, BrokerUnavailable, MockBroker, _price


_SNAPSHOT_FIELDS = frozenset({"broker", "client_order_id", "broker_order_id", "status", "revision",
                              "structure", "qty", "filled_qty", "fills", "created_at", "updated_at"})
_FILL_FIELDS = frozenset({"fill_id", "qty", "price", "created_at"})
_FINAL = frozenset({"filled", "rejected", "canceled"})
PILOT_SYMBOL = "DEMO270115C00100000"


def _iso_timestamp(value):
    if not isinstance(value, str) or len(value) > 40 or not value.endswith("Z"):
        raise LineageError("invalid mock snapshot timestamp")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise LineageError("invalid mock snapshot timestamp") from None
    if result.utcoffset().total_seconds() != 0:
        raise LineageError("invalid mock snapshot timestamp")
    return result


def _uuid(value):
    if not isinstance(value, str):
        raise LineageError("invalid mock snapshot identity")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise LineageError("invalid mock snapshot identity") from None
    if str(parsed) != value:
        raise LineageError("invalid mock snapshot identity")


def validate_mock_snapshot(snapshot, order):
    """Validate transport evidence before the store's transactional validation.

    This does not project a fill, position, review, or event. The store remains
    authoritative for historical revision/fill consistency and closing holds.
    Return an isolated value, so mutable adapter results cannot alter evidence.
    """
    if not isinstance(snapshot, dict) or set(snapshot) != _SNAPSHOT_FIELDS:
        raise LineageError("invalid mock snapshot fields")
    value = deepcopy(snapshot)
    if value["broker"] != "mock" or value["client_order_id"] != order["client_order_id"]:
        raise LineageError("mock snapshot belongs to a different intent")
    _uuid(value["broker_order_id"])
    if order.get("broker_order_id") not in (None, value["broker_order_id"]):
        raise LineageError("mock venue identity changed")
    value["structure"] = validate_structure(value["structure"])
    if value["structure"] != validate_structure(order["structure"]):
        raise LineageError("mock request structure changed")
    integer(value["revision"], "revision", maximum=2147483647)
    integer(value["qty"], "qty")
    integer(value["filled_qty"], "filled_qty", minimum=0)
    if value["qty"] != order["qty"] or value["qty"] != value["structure"]["qty"] or value["filled_qty"] > value["qty"]:
        raise LineageError("invalid mock snapshot quantities")
    created = _iso_timestamp(value["created_at"])
    updated = _iso_timestamp(value["updated_at"])
    if updated < created:
        raise LineageError("mock snapshot time reversed")
    if not isinstance(value["fills"], list) or len(value["fills"]) > value["qty"]:
        raise LineageError("invalid mock fill history")
    ids = set()
    total = 0
    limit = Decimal(value["structure"]["limit_price"])
    last_fill_time = created
    for fill in value["fills"]:
        if not isinstance(fill, dict) or set(fill) != _FILL_FIELDS:
            raise LineageError("invalid mock fill fields")
        _uuid(fill["fill_id"])
        if fill["fill_id"] in ids:
            raise LineageError("duplicate mock fill identity")
        ids.add(fill["fill_id"])
        integer(fill["qty"], "fill quantity")
        if not isinstance(fill["price"], str):
            raise LineageError("invalid mock fill price")
        price = _price(fill["price"])
        if (value["structure"]["side"] == "buy" and price > limit) or (value["structure"]["side"] == "sell" and price < limit):
            raise LineageError("mock fill violates limit")
        timestamp = _iso_timestamp(fill["created_at"])
        if timestamp < last_fill_time or timestamp > updated:
            raise LineageError("invalid mock fill time")
        last_fill_time = timestamp
        total += fill["qty"]
    if total != value["filled_qty"]:
        raise LineageError("mock fill total mismatch")
    status = value["status"]
    if not isinstance(status, str) or status not in ("accepted", "rejected", "partially_filled", "filled", "canceled"):
        raise LineageError("invalid mock venue status")
    if ((status in ("accepted", "rejected") and total != 0)
            or (status == "partially_filled" and not 0 < total < value["qty"])
            or (status == "filled" and total != value["qty"])
            or (status == "canceled" and total == value["qty"])):
        raise LineageError("inconsistent mock venue status")
    if value["revision"] < len(value["fills"]) + 1:
        raise LineageError("inconsistent mock revision")
    return value


class PaperLifecycle:
    """Explicit paper-only lifecycle with fail-closed pilot authorization."""

    def __init__(self, store, broker, *, agent_id="alchemist"):
        if not isinstance(broker, MockBroker):
            raise LineageAccessError("paper lifecycle requires MockBroker")
        if agent_id != "alchemist":
            raise LineageAccessError("only the alchemist mock pilot is supported")
        self.store = store
        self.broker = broker
        self.agent_id = agent_id

    def _owner(self, value):
        if value.get("agent_id") != "alchemist" or self.agent_id != "alchemist":
            raise LineageAccessError("only the alchemist owner may execute the mock pilot")
        if not isinstance(value.get("structure"), dict) or value["structure"].get("symbol") != PILOT_SYMBOL:
            raise LineageAccessError("only the fictional DEMO pilot contract may execute")
        return value

    def _issue(self, order, category):
        return self.store.mark_order_issue(order["order_id"], self.agent_id, category)

    def _apply(self, order, snapshot):
        try:
            validated = validate_mock_snapshot(snapshot, order)
            return self.store.apply_snapshot(order["order_id"], self.agent_id, validated)
        except Exception:
            # A failed store transaction is retried by reading the durable venue
            # snapshot; never manually duplicate fills or position arithmetic.
            return self._issue(order, "failed")

    def _lookup(self, order):
        try:
            return self.broker.lookup_order(order["client_order_id"]), None
        except BrokerUnavailable:
            return None, self._issue(order, "unavailable")
        except Exception:
            return None, self._issue(order, "failed")

    def submit(self, proposal_id):
        proposal = self._owner(self.store.get_proposal(proposal_id, self.agent_id))
        # prepare_order checks the existing reviewed queue and closing holds,
        # and commits immutable client identity BEFORE any venue interaction.
        order = self._owner(self.store.prepare_order(proposal["proposal_id"], self.agent_id))
        snapshot, issue = self._lookup(order)
        if issue is not None:
            return issue
        if snapshot is not None:
            return self._apply(order, snapshot)
        # Only authoritative absence permits this same-client-ID submission.
        # A previously confirmed order disappearing is not a fresh order.
        if order.get("broker_order_id") is not None:
            return self._issue(order, "submission_unknown")
        try:
            snapshot = self.broker.submit_order(order["client_order_id"], order["structure"])
        except BrokerConflict:
            return self._issue(order, "failed")
        except Exception:
            # Timeouts and failures after dispatch can be ambiguous, including
            # a BrokerUnavailable raised *after* the venue commits acceptance.
            return self._issue(order, "submission_unknown")
        return self._apply(order, snapshot)

    def reconcile(self, order_id):
        order = self._owner(self.store.get_order(order_id, self.agent_id))
        snapshot, issue = self._lookup(order)
        if issue is not None:
            return issue
        if snapshot is None:
            return self._issue(order, "submission_unknown")
        return self._apply(order, snapshot)

    def cancel(self, order_id):
        order = self._owner(self.store.get_order(order_id, self.agent_id))
        snapshot, issue = self._lookup(order)
        if issue is not None:
            return issue
        if snapshot is None:
            return self._issue(order, "submission_unknown")
        order = self._apply(order, snapshot)
        if order["sync_state"] != "ok" or order["status"] in _FINAL:
            return order
        try:
            snapshot = self.broker.cancel_order(order["client_order_id"])
        except BrokerConflict:
            return self._issue(order, "failed")
        except Exception:
            return self._issue(order, "submission_unknown")
        if snapshot is None:
            return self._issue(order, "submission_unknown")
        return self._apply(order, snapshot)
