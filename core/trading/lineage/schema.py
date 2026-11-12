"""Additive lineage schema in the existing queue database."""
from core.trading.queue import ensure_queue_schema

STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS lineage_inquiries (
        inquiry_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, title TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('open','paused','abandoned')),
        phase INTEGER NOT NULL CHECK(phase>=0), visibility TEXT NOT NULL CHECK(visibility IN ('owner','community')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_entries (
        entry_id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id),
        agent_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('observation','interpretation')),
        content TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('agent','operator','external')),
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_proposals (
        proposal_id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id),
        agent_id TEXT NOT NULL, queue_id INTEGER NOT NULL UNIQUE REFERENCES trade_queue(id),
        structure TEXT NOT NULL, thesis TEXT NOT NULL, horizon TEXT NOT NULL,
        uncertainty TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_orders (
        order_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE REFERENCES lineage_proposals(proposal_id),
        inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id), agent_id TEXT NOT NULL,
        queue_id INTEGER NOT NULL REFERENCES trade_queue(id), client_order_id TEXT NOT NULL UNIQUE,
        broker_order_id TEXT UNIQUE, broker TEXT NOT NULL DEFAULT 'mock', status TEXT NOT NULL,
        sync_state TEXT NOT NULL, broker_revision INTEGER NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL CHECK(qty>0), filled_qty INTEGER NOT NULL DEFAULT 0 CHECK(filled_qty>=0 AND filled_qty<=qty),
        structure TEXT NOT NULL, snapshot TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_positions (
        position_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, symbol TEXT NOT NULL,
        qty INTEGER NOT NULL CHECK(qty>=0), average_entry_price TEXT, cost_basis TEXT NOT NULL,
        gross_realized_pnl TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('open','closed')),
        multiplier INTEGER NOT NULL DEFAULT 100, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(agent_id,symbol))""",
    """CREATE TABLE IF NOT EXISTS lineage_fills (
        fill_id TEXT PRIMARY KEY, broker_fill_id TEXT NOT NULL UNIQUE,
        order_id TEXT NOT NULL REFERENCES lineage_orders(order_id),
        proposal_id TEXT NOT NULL REFERENCES lineage_proposals(proposal_id),
        inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id),
        position_id TEXT NOT NULL REFERENCES lineage_positions(position_id), agent_id TEXT NOT NULL,
        qty INTEGER NOT NULL CHECK(qty>0), price TEXT NOT NULL, side TEXT NOT NULL,
        created_at TEXT NOT NULL, authority TEXT NOT NULL DEFAULT 'mock_broker')""",
    """CREATE TABLE IF NOT EXISTS lineage_reviews (
        review_id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id),
        agent_id TEXT NOT NULL, content TEXT NOT NULL,
        proposal_id TEXT REFERENCES lineage_proposals(proposal_id),
        order_id TEXT REFERENCES lineage_orders(order_id), position_id TEXT REFERENCES lineage_positions(position_id),
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_events (
        event_id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES lineage_inquiries(inquiry_id),
        agent_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lineage_operations (
        agent_id TEXT NOT NULL, operation_key TEXT NOT NULL, kind TEXT NOT NULL,
        payload TEXT NOT NULL, result_id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(agent_id,operation_key))""",
    "CREATE INDEX IF NOT EXISTS lineage_inquiries_owner ON lineage_inquiries(agent_id,created_at,inquiry_id)",
    "CREATE INDEX IF NOT EXISTS lineage_orders_owner ON lineage_orders(agent_id,inquiry_id)",
    "CREATE INDEX IF NOT EXISTS lineage_fills_inquiry ON lineage_fills(inquiry_id,created_at,fill_id)",
)

IMMUTABLE = ("entries", "proposals", "fills", "reviews", "events", "operations")


def ensure_lineage_schema(conn):
    ensure_queue_schema(conn)
    for statement in STATEMENTS:
        conn.execute(statement)
    for name in IMMUTABLE:
        for action in ("UPDATE", "DELETE"):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS lineage_{name}_no_{action.lower()} "
                         f"BEFORE {action} ON lineage_{name} BEGIN "
                         "SELECT RAISE(ABORT, 'lineage history is immutable'); END")
