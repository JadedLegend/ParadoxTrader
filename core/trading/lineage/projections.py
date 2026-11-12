"""Mock-confirmed snapshot validation and atomic execution accounting."""
import json
from decimal import Decimal, localcontext

from .errors import LineageConflict, LineageError
from .validation import canonical_json, execution_price, integer, text, validate_structure

TERMINAL = frozenset({"filled", "rejected", "canceled"})
SNAPSHOT_FIELDS = frozenset({"broker", "client_order_id", "broker_order_id", "status", "revision",
                           "structure", "qty", "filled_qty", "fills", "created_at", "updated_at"})


def validate_snapshot(order, snapshot):
    if not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_FIELDS:
        raise LineageError("snapshot must contain only the mock broker contract fields")
    result = dict(snapshot)
    if result["broker"] != "mock":
        raise LineageError("only mock broker authority is accepted")
    for name in ("client_order_id", "broker_order_id", "created_at", "updated_at"):
        text(result[name], name, maximum=100, empty=False)
    if result["client_order_id"] != order["client_order_id"]:
        raise LineageConflict("snapshot client identity differs from durable intent")
    if order["broker_order_id"] is not None and result["broker_order_id"] != order["broker_order_id"]:
        raise LineageConflict("snapshot changed broker order identity")
    integer(result["revision"], "revision", maximum=2147483647)
    integer(result["qty"], "qty")
    integer(result["filled_qty"], "filled_qty", minimum=0)
    result["structure"] = validate_structure(result["structure"])
    if result["structure"] != json.loads(order["structure"]) or result["qty"] != order["qty"]:
        raise LineageConflict("snapshot structure/quantity differs from durable intent")
    if result["status"] not in ("accepted", "rejected", "partially_filled", "filled", "canceled"):
        raise LineageError("unsupported mock status")
    if not isinstance(result["fills"], list) or len(result["fills"]) > 1000000:
        raise LineageError("fills must be a bounded explicit list")
    seen, fills, filled_qty = set(), [], 0
    for raw in result["fills"]:
        if not isinstance(raw, dict) or set(raw) != {"fill_id", "qty", "price", "created_at"}:
            raise LineageError("fill must contain only explicit broker execution fields")
        fill = dict(raw)
        text(fill["fill_id"], "fill_id", maximum=100, empty=False)
        text(fill["created_at"], "fill created_at", maximum=100, empty=False)
        integer(fill["qty"], "fill qty")
        fill["price"] = execution_price(fill["price"], "fill price")
        if fill["fill_id"] in seen:
            raise LineageConflict("duplicate fill identity within snapshot")
        seen.add(fill["fill_id"])
        price, limit = Decimal(fill["price"]), Decimal(result["structure"]["limit_price"])
        if ((result["structure"]["side"] == "buy" and price > limit)
                or (result["structure"]["side"] == "sell" and price < limit)):
            raise LineageConflict("broker fill violates the approved limit price")
        filled_qty += fill["qty"]
        fills.append(fill)
    if filled_qty != result["filled_qty"] or filled_qty > result["qty"]:
        raise LineageConflict("snapshot fill totals disagree or overfill durable quantity")
    status = result["status"]
    if (status in ("accepted", "rejected") and filled_qty != 0
            or status == "partially_filled" and not 0 < filled_qty < result["qty"]
            or status == "filled" and filled_qty != result["qty"]
            or status == "canceled" and filled_qty == result["qty"]):
        raise LineageConflict("snapshot status is inconsistent with fill quantity")
    # Broker list ordering and decimal formatting are not execution identities.
    result["fills"] = sorted(fills, key=lambda fill: fill["fill_id"])
    return result


def apply_snapshot(store, order_id, agent_id, snapshot):
    # Import the tiny transaction helpers at call time to avoid circular imports.
    from .store import _event, _now, _stable_id
    with store._connection() as conn:
        order = store._order(conn, order_id, agent_id)
        canonical = validate_snapshot(order, snapshot)
        encoded = canonical_json(canonical)
        revision = canonical["revision"]
        if revision < order["broker_revision"]:
            return store._order_dto(order)
        previous = json.loads(order["snapshot"]) if order["snapshot"] else None
        if revision == order["broker_revision"]:
            if encoded != order["snapshot"]:
                raise LineageConflict("equal broker revision has different confirmed payload")
            if order["sync_state"] == "ok":
                return store._order_dto(order)
            # A successful repeat lookup clears an issue without reapplying any fills.
            now = _now()
            conn.execute("UPDATE lineage_orders SET sync_state='ok',updated_at=? WHERE order_id=?", (now, order_id))
            _event(conn, order["inquiry_id"], agent_id, "order_sync_restored",
                   {"order_id": order_id, "broker_revision": revision}, now)
            store._touch(conn, order["inquiry_id"], now)
            return store._order_dto(store._order(conn, order_id, agent_id))
        if previous:
            if canonical["created_at"] != previous["created_at"]:
                raise LineageConflict("broker order creation identity changed")
            if canonical["filled_qty"] < previous["filled_qty"]:
                raise LineageConflict("confirmed fills cannot be removed")
            if previous["status"] in TERMINAL:
                if canonical["status"] != previous["status"] or canonical["fills"] != previous["fills"]:
                    raise LineageConflict("confirmed terminal order cannot regress or acquire new fills")
            elif previous["status"] == "partially_filled" and canonical["status"] == "accepted":
                raise LineageConflict("confirmed partial order cannot regress to acceptance")
        current_fills = {row["broker_fill_id"]: row for row in conn.execute(
            "SELECT fill_id,broker_fill_id,order_id,agent_id,qty,price,created_at FROM lineage_fills WHERE order_id=?", (order_id,))}
        incoming_ids = {fill["fill_id"] for fill in canonical["fills"]}
        if not set(current_fills).issubset(incoming_ids):
            raise LineageConflict("confirmed fill identity removed from snapshot")
        new_fills = []
        for fill in canonical["fills"]:
            existing = conn.execute("SELECT order_id,agent_id,qty,price,created_at FROM lineage_fills "
                                    "WHERE broker_fill_id=? LIMIT 1", (fill["fill_id"],)).fetchone()
            if existing:
                if (existing["order_id"] != order_id or existing["agent_id"] != agent_id
                        or existing["qty"] != fill["qty"] or existing["price"] != fill["price"]
                        or existing["created_at"] != fill["created_at"]):
                    raise LineageConflict("stable broker fill identity changed")
            else:
                new_fills.append(fill)
        now = _now()
        structure = canonical["structure"]
        symbol = structure["symbol"]
        position = conn.execute("SELECT * FROM lineage_positions WHERE agent_id=? AND symbol=? LIMIT 1", (agent_id, symbol)).fetchone()
        if new_fills:
            position_id = _stable_id("position", agent_id, symbol) if position is None else position["position_id"]
            if position and position["agent_id"] != agent_id:
                raise LineageConflict("position owner mismatch")
            quantity = 0 if position is None else position["qty"]
            with localcontext() as context:
                context.prec = 240
                cost = Decimal("0" if position is None else position["cost_basis"])
                realized = Decimal("0" if position is None else position["gross_realized_pnl"])
                for fill in new_fills:
                    fill_qty, price = fill["qty"], Decimal(fill["price"])
                    if structure["intent"] == "open":
                        quantity += fill_qty
                        cost += price * fill_qty
                    else:
                        if fill_qty > quantity:
                            raise LineageConflict("closing execution exceeds confirmed long holdings")
                        average = cost / quantity
                        realized += (price - average) * fill_qty * Decimal(100)
                        cost -= average * fill_qty
                        quantity -= fill_qty
                        if quantity == 0:
                            cost = Decimal(0)
                average_string = None if quantity == 0 else _decimal_projection(cost / quantity)
                cost_string = _decimal_projection(cost)
                pnl_string = _decimal_projection(realized)
            if position is None:
                conn.execute("INSERT INTO lineage_positions "
                             "(position_id,agent_id,symbol,qty,average_entry_price,cost_basis,gross_realized_pnl,status,created_at,updated_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (position_id, agent_id, symbol, quantity, average_string, cost_string, pnl_string,
                              "open" if quantity else "closed", now, now))
            else:
                conn.execute("UPDATE lineage_positions SET qty=?,average_entry_price=?,cost_basis=?,gross_realized_pnl=?,"
                             "status=?,updated_at=? WHERE position_id=? AND agent_id=?",
                             (quantity, average_string, cost_string, pnl_string, "open" if quantity else "closed", now, position_id, agent_id))
            for fill in new_fills:
                fill_id = _stable_id("fill", "mock", fill["fill_id"])
                conn.execute("INSERT INTO lineage_fills "
                             "(fill_id,broker_fill_id,order_id,proposal_id,inquiry_id,position_id,agent_id,qty,price,side,created_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (fill_id, fill["fill_id"], order_id, order["proposal_id"], order["inquiry_id"], position_id,
                              agent_id, fill["qty"], fill["price"], structure["side"], fill["created_at"]))
                _event(conn, order["inquiry_id"], agent_id, "fill_confirmed",
                       {"fill_id": fill_id, "broker_fill_id": fill["fill_id"], "order_id": order_id,
                        "position_id": position_id, "authority": "mock_broker"}, now)
        conn.execute("UPDATE lineage_orders SET broker_order_id=?,status=?,sync_state='ok',broker_revision=?,filled_qty=?,"
                     "snapshot=?,updated_at=? WHERE order_id=?",
                     (canonical["broker_order_id"], canonical["status"], revision, canonical["filled_qty"], encoded, now, order_id))
        _event(conn, order["inquiry_id"], agent_id, "broker_snapshot_applied",
               {"order_id": order_id, "broker_order_id": canonical["broker_order_id"], "broker_revision": revision,
                "status": canonical["status"], "filled_qty": canonical["filled_qty"], "authority": "mock_broker"}, now)
        store._touch(conn, order["inquiry_id"], now)
        return store._order_dto(store._order(conn, order_id, agent_id))


def _decimal_projection(value):
    # Projection results can be longer than accepted external decimal inputs.
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if value == 0 else result
