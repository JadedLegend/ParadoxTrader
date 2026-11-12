"""Bounded lineage reads with explicit stored-phase privacy.

These functions never consult private journals, memories, model messages or
configuration. `operator=True` is an internal capability, not a client role.
"""
import json

from .errors import LineageAccessError, LineageError, LineageNotFound
from .validation import integer, text


def access_context(viewer_agent_id, phase, operator):
    if type(operator) is not bool:
        raise LineageAccessError("operator capability must be explicitly boolean")
    integer(phase, "phase", minimum=0, maximum=100)
    if not operator:
        if not isinstance(viewer_agent_id, str) or not viewer_agent_id.strip() or len(viewer_agent_id) > 100:
            raise LineageAccessError("explicit viewer identity is required")


def visible(inquiry, viewer_agent_id, phase, operator):
    return (operator is True or inquiry["agent_id"] == viewer_agent_id
            or (phase >= 1 and inquiry["phase"] >= 1 and inquiry["visibility"] == "community"))


def position_dto(row):
    return {"position_id": row["position_id"], "agent_id": row["agent_id"], "symbol": row["symbol"],
            "qty": row["qty"], "average_entry_price": row["average_entry_price"],
            "gross_realized_pnl": row["gross_realized_pnl"], "market_value": None,
            "unrealized_pnl": None, "fees": None, "mark_status": "unavailable", "status": row["status"],
            "multiplier": row["multiplier"]}


def list_inquiries(store, agent_id, *, viewer_agent_id=None, phase=0, operator=False, limit=50, offset=0):
    store._agent(agent_id)
    access_context(viewer_agent_id, phase, operator)
    integer(limit, "limit", maximum=2147483647)
    integer(offset, "offset", minimum=0, maximum=2147483647)
    limit = min(limit, 100)
    where, params = "agent_id=?", [agent_id]
    if not operator and agent_id != viewer_agent_id:
        where += " AND phase>=1 AND visibility='community'" if phase >= 1 else " AND 0"
    with store._connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM lineage_inquiries WHERE " + where, params).fetchone()[0]
        rows = conn.execute("SELECT inquiry_id,agent_id,title,state,phase,visibility,created_at,updated_at "
                            "FROM lineage_inquiries WHERE " + where + " ORDER BY created_at,inquiry_id LIMIT ? OFFSET ?",
                            [*params, limit, offset]).fetchall()
        return {"status": "ok", "inquiries": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_inquiry(store, inquiry_id, *, viewer_agent_id=None, phase=0, operator=False):
    access_context(viewer_agent_id, phase, operator)
    text(inquiry_id, "inquiry_id", maximum=100, empty=False)
    with store._connection() as conn:
        inquiry = conn.execute("SELECT inquiry_id,agent_id,title,state,phase,visibility,created_at,updated_at "
                               "FROM lineage_inquiries WHERE inquiry_id=? LIMIT 1", (inquiry_id,)).fetchone()
        if inquiry is None:
            raise LineageNotFound("inquiry_id not found")
        if not visible(inquiry, viewer_agent_id, phase, operator):
            raise LineageAccessError("inquiry is private to its original owner/phase")
        result = {"status": "ok", "inquiry": dict(inquiry), "truncated": False}
        agent_id = inquiry["agent_id"]
        for category, key in (("entries", "entry_id"), ("proposals", "proposal_id"), ("orders", "order_id"),
                              ("fills", "fill_id"), ("reviews", "review_id"), ("events", "event_id")):
            rows = conn.execute(f"SELECT * FROM lineage_{category} WHERE inquiry_id=? AND agent_id=? "
                                f"ORDER BY created_at,{key} LIMIT 101", (inquiry_id, agent_id)).fetchall()
            if len(rows) > 100:
                result["truncated"] = True
            values = []
            for row in rows[:100]:
                if category == "orders":
                    value = store._order_dto(row)
                elif category == "proposals":
                    value = store._proposal(conn, row["proposal_id"], agent_id)
                else:
                    value = dict(row)
                    if category == "events":
                        value["payload"] = json.loads(value["payload"])
                values.append(value)
            result[category] = values
        # Do not join through symbols alone: positions must be related by own fills.
        # Peer views also suppress aggregates with any private contributing inquiry.
        rows = conn.execute("SELECT p.* FROM lineage_positions p WHERE p.agent_id=? AND EXISTS "
                            "(SELECT 1 FROM lineage_fills f WHERE f.position_id=p.position_id AND f.agent_id=? AND f.inquiry_id=?) "
                            "ORDER BY p.created_at,p.position_id LIMIT 101", (agent_id, agent_id, inquiry_id)).fetchall()
        positions = []
        for position in rows:
            if not operator and viewer_agent_id != agent_id:
                linked = conn.execute("SELECT DISTINCT i.agent_id,i.phase,i.visibility FROM lineage_inquiries i "
                                      "JOIN lineage_fills f ON f.inquiry_id=i.inquiry_id "
                                      "WHERE f.position_id=? AND f.agent_id=?", (position["position_id"], agent_id)).fetchall()
                if any(not visible(other, viewer_agent_id, phase, operator) for other in linked):
                    continue
            positions.append(position_dto(position))
        if len(rows) > 100 or len(positions) > 100:
            result["truncated"] = True
        result["positions"] = positions[:100]
        return result
