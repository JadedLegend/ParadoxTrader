"""The existing review queue, independent of broker/configuration imports.

This is an additive extension of data/trade_queue.sqlite3, not another queue.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

def _queue_dir() -> Path:
    """DATA_DIR when set, else <repo>/data, resolved without touching the disk.

    core.data_dir creates directories at import, which this broker-free module
    must not do; the directory is created only when the queue is opened.
    """
    explicit = os.environ.get("DATA_DIR")
    return Path(explicit) if explicit else Path(__file__).parent.parent.parent / "data"


# Follows DATA_DIR like the other stores. With DATA_DIR unset this is still
# <repo>/data/trade_queue.sqlite3, so existing local queues are not moved.
QUEUE_DB = _queue_dir() / "trade_queue.sqlite3"
QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    proposal TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    reviewer_notes TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    lineage_proposal_id TEXT
);
"""


def ensure_queue_schema(conn: sqlite3.Connection) -> None:
    """Add nullable linkage without moving the database or rewriting old rows.

    Do not use executescript here: it can commit a caller's transaction.
    """
    conn.execute(QUEUE_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(trade_queue)")}
    if "lineage_proposal_id" not in columns:
        conn.execute("ALTER TABLE trade_queue ADD COLUMN lineage_proposal_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS trade_queue_lineage_link "
        "ON trade_queue(lineage_proposal_id) WHERE lineage_proposal_id IS NOT NULL"
    )


def ensure_private_db_file(db_path) -> None:
    """Secure a newly created file; never chmod or migrate an existing database."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(db_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    os.close(fd)


class TradeQueue:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or QUEUE_DB)
        ensure_private_db_file(self.db_path)
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute("BEGIN IMMEDIATE")
            ensure_queue_schema(conn)

    def enqueue(self, agent_id: str, proposal: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            cur = conn.execute(
                "INSERT INTO trade_queue (agent_id, proposal, created_at) VALUES (?, ?, ?)",
                (agent_id, json.dumps(proposal), now),
            )
            return cur.lastrowid

    def get_pending(self, *, include_lineage: bool = False) -> list[dict]:
        """Legacy list excludes protected lineage; opt-in is trusted internal use."""
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            linkage_filter = "" if include_lineage else " AND lineage_proposal_id IS NULL"
            rows = conn.execute(
                "SELECT id, agent_id, proposal, status, created_at FROM trade_queue "
                "WHERE status='pending'" + linkage_filter + " ORDER BY created_at ASC"
            ).fetchall()
        # Preserve the exact legacy shape, including no new linkage field.
        return [{"id": r[0], "agent_id": r[1], "proposal": json.loads(r[2]),
                 "status": r[3], "created_at": r[4]} for r in rows]

    def get_entry(self, trade_id: int) -> Optional[dict]:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT id, agent_id, proposal, status, reviewer_notes, "
                               "created_at, reviewed_at, lineage_proposal_id FROM trade_queue "
                               "WHERE id=? LIMIT 1", (trade_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["proposal"] = json.loads(result["proposal"])
        return result

    def approve(self, trade_id: int, notes: str = "") -> bool:
        return self._review(trade_id, "approved", notes)

    def reject(self, trade_id: int, notes: str = "") -> bool:
        return self._review(trade_id, "rejected", notes)

    def _review(self, trade_id: int, status: str, notes: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id, agent_id, status, lineage_proposal_id "
                               "FROM trade_queue WHERE id=? LIMIT 1", (trade_id,)).fetchone()
            if row and row["lineage_proposal_id"] is not None:
                valid_link = conn.execute(
                    "SELECT p.proposal_id FROM lineage_proposals p "
                    "JOIN lineage_inquiries i ON i.inquiry_id=p.inquiry_id "
                    "WHERE p.proposal_id=? AND p.queue_id=? AND p.agent_id=? AND i.agent_id=? LIMIT 1",
                    (row["lineage_proposal_id"], row["id"], row["agent_id"], row["agent_id"]),
                ).fetchone()
                if valid_link is None:
                    return False
                if not isinstance(notes, str) or len(notes) > 2000:
                    return False
                if row["status"] == status:
                    return True
                if row["status"] != "pending":
                    return False
                # The helper verifies both sides of the ownership/linkage before writing.
                from core.trading.lineage.store import append_proposal_review
                if not append_proposal_review(conn, row, status, notes, now):
                    return False
            # Preserve unlinked legacy behavior (including missing-ID success).
            conn.execute("UPDATE trade_queue SET status=?, reviewer_notes=?, reviewed_at=? WHERE id=?",
                         (status, notes, now, trade_id))
        return True
