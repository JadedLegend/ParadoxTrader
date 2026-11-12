"""
Messaging Store — Paradox Edge Trader v2
==========================================
Agent-to-agent and user-to-agent direct messaging.
All messages are persisted. Unread tracking per recipient.
The user's agent_id is 'user' for DM purposes.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.data_dir import db_path as _db_path
MSG_DB = Path(_db_path("messages.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    content TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    thread_key TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recipient ON messages(recipient, is_read);
CREATE INDEX IF NOT EXISTS idx_thread ON messages(thread_key);
"""


class MessagingStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or MSG_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def send(
        self,
        sender: str,
        recipient: str,
        content: str,
        thread_key: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        # Auto-generate thread key from sorted pair if not provided
        if not thread_key:
            pair = sorted([sender, recipient])
            thread_key = f"{pair[0]}::{pair[1]}"
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO messages (sender, recipient, content, thread_key, created_at) VALUES (?, ?, ?, ?, ?)",
                (sender, recipient, content, thread_key, now)
            )
            conn.commit()
            return cur.lastrowid

    def get_thread(self, agent_a: str, agent_b: str, limit: int = 50) -> list[dict]:
        pair = sorted([agent_a, agent_b])
        thread_key = f"{pair[0]}::{pair[1]}"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, sender, recipient, content, is_read, created_at FROM messages WHERE thread_key=? ORDER BY created_at ASC LIMIT ?",
                (thread_key, limit)
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_inbox(
        self, recipient: str, unread_only: bool = False, limit: int = 20,
        sender: Optional[str] = None,
    ) -> list[dict]:
        query = "SELECT id, sender, recipient, content, is_read, created_at FROM messages WHERE recipient=?"
        params = [recipient]
        if unread_only:
            query += " AND is_read=0"
        if sender is not None:
            query += " AND sender=?"
            params.append(sender)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row(r) for r in rows]

    def mark_read(self, message_ids: list[int]):
        if not message_ids:
            return
        placeholders = ",".join("?" * len(message_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE messages SET is_read=1 WHERE id IN ({placeholders})",
                message_ids
            )
            conn.commit()

    def mark_thread_read(self, agent_a: str, agent_b: str, reader: str):
        pair = sorted([agent_a, agent_b])
        thread_key = f"{pair[0]}::{pair[1]}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE messages SET is_read=1 WHERE thread_key=? AND recipient=?",
                (thread_key, reader)
            )
            conn.commit()

    def unread_count(self, recipient: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE recipient=? AND is_read=0",
                (recipient,)
            ).fetchone()
        return row[0] if row else 0

    def _row(self, r) -> dict:
        return {
            "id": r[0], "sender": r[1], "recipient": r[2],
            "content": r[3], "read": bool(r[4]), "created_at": r[5],
        }
