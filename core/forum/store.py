"""
Forum Store — Paradox Edge Trader v2
======================================
The shared deliberation space. All agents can read and post.
The forum is the council chamber — arguments are recorded,
visible to all agents, and referenceable by the Paradox Hunter.

Also handles the Phase 2 countdown display.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.data_dir import db_path as _db_path
FORUM_DB = Path(_db_path("forum.sqlite3"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    content TEXT NOT NULL,
    thread_id TEXT DEFAULT 'general',
    reply_to INTEGER REFERENCES posts(id),
    tags TEXT DEFAULT '[]',
    phase TEXT DEFAULT 'symmetry',
    is_pinned INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_by TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    author TEXT DEFAULT 'SYSTEM',
    is_countdown INTEGER DEFAULT 0,
    countdown_target TEXT,
    created_at TEXT NOT NULL
);
"""

AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]


class ForumStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or FORUM_DB)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # ─── Posts ────────────────────────────────────────────────────────────────

    def post(
        self,
        author: str,
        content: str,
        thread_id: str = "general",
        reply_to: Optional[int] = None,
        tags: Optional[list] = None,
        phase: str = "symmetry",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO posts (author, content, thread_id, reply_to, tags, phase, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (author, content, thread_id, reply_to,
                 json.dumps(tags or []), phase, now)
            )
            conn.commit()
            return cur.lastrowid

    def get_thread(self, thread_id: str = "general", limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, author, content, thread_id, reply_to, tags, phase, is_pinned, created_at
                   FROM posts WHERE thread_id=? ORDER BY created_at ASC LIMIT ?""",
                (thread_id, limit)
            ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def get_recent(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, author, content, thread_id, reply_to, tags, phase, is_pinned, created_at
                   FROM posts ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return [self._row_to_post(r) for r in rows]

    def _row_to_post(self, r) -> dict:
        return {
            "id": r[0], "author": r[1], "content": r[2],
            "thread_id": r[3], "reply_to": r[4],
            "tags": json.loads(r[5]), "phase": r[6],
            "pinned": bool(r[7]), "created_at": r[8],
        }

    # ─── Threads ──────────────────────────────────────────────────────────────

    def create_thread(self, thread_id: str, title: str, created_by: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO threads (id, title, created_by, created_at) VALUES (?, ?, ?, ?)",
                    (thread_id, title, created_by, now)
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def list_threads(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, created_by, is_active, created_at FROM threads ORDER BY created_at DESC"
            ).fetchall()
        return [{"id": r[0], "title": r[1], "created_by": r[2], "active": bool(r[3]), "created_at": r[4]} for r in rows]

    # ─── Announcements / Countdown ────────────────────────────────────────────

    def post_announcement(
        self,
        content: str,
        author: str = "SYSTEM",
        is_countdown: bool = False,
        countdown_target: Optional[str] = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO announcements (content, author, is_countdown, countdown_target, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (content, author, int(is_countdown), countdown_target, now)
            )
            conn.commit()
            return cur.lastrowid

    def get_countdown(self) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, content, countdown_target, created_at FROM announcements WHERE is_countdown=1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        target = row[2]
        remaining = None
        if target:
            try:
                target_dt = datetime.fromisoformat(target)
                now_dt = datetime.now(timezone.utc)
                if target_dt.tzinfo is None:
                    target_dt = target_dt.replace(tzinfo=timezone.utc)
                delta = target_dt - now_dt
                remaining = max(0, int(delta.total_seconds()))
            except Exception:
                pass
        return {
            "id": row[0], "content": row[1],
            "target": target, "seconds_remaining": remaining,
            "created_at": row[3],
        }

    def get_latest_announcements(self, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, content, author, is_countdown, countdown_target, created_at FROM announcements ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {"id": r[0], "content": r[1], "author": r[2],
             "countdown": bool(r[3]), "target": r[4], "created_at": r[5]}
            for r in rows
        ]
