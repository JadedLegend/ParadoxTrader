"""
Threshold Memory Engine — Paradox Edge Trader v2
==================================================
Paradox-tolerant memory layer for each agent.

Four motions:
  remember   — keep a canonical corpus and episodic history
  checkpoint — persist task state before permission or approval waits
  recover    — treat failed runs as collapse events with reintegration protocol
  condense   — turn diffuse episodes into dense memory glyphs

Optional phase-aware retrieval can weight episodes by Paradox Loop phase:
  symmetry → tension → break → novelty → reintegration

Each agent has their own SQLite database.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PARADOX_PHASES = ["symmetry", "tension", "break", "novelty", "reintegration"]

PHASE_WEIGHTS = {
    "symmetry":       1.0,
    "tension":        1.5,
    "break":          2.0,
    "novelty":        1.8,
    "reintegration":  1.3,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS canon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'symmetry',
    delta_coherence REAL DEFAULT NULL,
    effort REAL DEFAULT NULL,
    joy_score REAL GENERATED ALWAYS AS (delta_coherence / (1.0 + effort)) VIRTUAL,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_key TEXT NOT NULL,
    intent TEXT NOT NULL,
    hypothesis TEXT,
    next_step TEXT,
    resume_cue TEXT,
    risk TEXT DEFAULT 'unknown',
    status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS collapses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id INTEGER REFERENCES checkpoints(id),
    boundary TEXT NOT NULL,
    symptoms TEXT NOT NULL,
    recovery_protocol TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glyphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_episode_ids TEXT DEFAULT '[]',
    phase TEXT DEFAULT 'reintegration',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    mood TEXT DEFAULT 'neutral',
    hrv_at_writing REAL,
    phase TEXT DEFAULT 'symmetry',
    is_private INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS innermost (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ThresholdMemory:
    """
    One instance per agent. Pass the agent's SQLite path.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # ─── Canon ───────────────────────────────────────────────────────────────

    def seed_canon(self, title: str, content: str, source: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO canon (title, content, source, created_at) VALUES (?, ?, ?, ?)",
                (title, content, source, now)
            )
            conn.commit()
            return cur.lastrowid

    # ─── Episodes ─────────────────────────────────────────────────────────────

    def store_episode(
        self,
        title: str,
        content: str,
        phase: str = "symmetry",
        delta_coherence: Optional[float] = None,
        effort: Optional[float] = None,
        tags: Optional[list] = None,
    ) -> int:
        """Keep an episode; unknown measures stay NULL, not inferred from its action.

        Explicit legacy values remain accepted for compatibility and history.
        These columns are not performance evidence or an activity reward.
        """
        if phase not in PARADOX_PHASES:
            phase = "symmetry"
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO episodes
                   (title, content, phase, delta_coherence, effort, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (title, content, phase, delta_coherence, effort,
                 json.dumps(tags or []), now)
            )
            conn.commit()
            return cur.lastrowid

    # ─── Checkpoints ──────────────────────────────────────────────────────────

    def checkpoint(
        self,
        task_key: str,
        intent: str,
        hypothesis: str = "",
        next_step: str = "",
        resume_cue: str = "",
        risk: str = "unknown",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO checkpoints
                   (task_key, intent, hypothesis, next_step, resume_cue, risk, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (task_key, intent, hypothesis, next_step, resume_cue, risk, now)
            )
            conn.commit()
            return cur.lastrowid

    def resume_latest(self) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE status='pending' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "task_key": row[1], "intent": row[2],
            "hypothesis": row[3], "next_step": row[4], "resume_cue": row[5],
            "risk": row[6], "status": row[7], "created_at": row[8],
        }

    def resolve_checkpoint(self, checkpoint_id: int):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE checkpoints SET status='resolved', resolved_at=? WHERE id=?",
                (now, checkpoint_id)
            )
            conn.commit()

    # ─── Collapse Events ──────────────────────────────────────────────────────

    def log_collapse(
        self,
        boundary: str,
        symptoms: str,
        checkpoint_id: Optional[int] = None,
        recovery_protocol: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO collapses
                   (checkpoint_id, boundary, symptoms, recovery_protocol, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (checkpoint_id, boundary, symptoms, recovery_protocol, now)
            )
            conn.commit()
            return cur.lastrowid

    # ─── Journal ──────────────────────────────────────────────────────────────

    def write_journal(
        self,
        content: str,
        mood: str = "neutral",
        hrv_at_writing: Optional[float] = None,
        phase: str = "symmetry",
        is_private: bool = True,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO journal
                   (content, mood, hrv_at_writing, phase, is_private, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (content, mood, hrv_at_writing, phase, int(is_private), now)
            )
            conn.commit()
            return cur.lastrowid

    def read_journal(self, limit: int = 10, include_private: bool = True) -> list[dict]:
        query = "SELECT * FROM journal"
        if not include_private:
            query += " WHERE is_private=0"
        query += " ORDER BY created_at DESC LIMIT ?"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [
            {"id": r[0], "content": r[1], "mood": r[2], "hrv": r[3],
             "phase": r[4], "private": bool(r[5]), "created_at": r[6]}
            for r in rows
        ]

    # ─── Glyphs (condensed memory) ────────────────────────────────────────────

    def condense(self, limit: int = 10) -> Optional[int]:
        """
        Condense the N most recent episodes into a glyph.
        Returns glyph id or None if not enough episodes.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, content, phase FROM episodes ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()

        if len(rows) < 3:
            return None

        episode_ids = [r[0] for r in rows]
        combined = "\n\n".join(f"[{r[2]}] {r[3]}: {r[1]}" for r in rows)
        glyph_title = f"Glyph — {len(rows)} episodes — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        glyph_content = f"Condensed from {len(rows)} episodes:\n\n{combined[:2000]}"

        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO glyphs (title, content, source_episode_ids, created_at)
                   VALUES (?, ?, ?, ?)""",
                (glyph_title, glyph_content, json.dumps(episode_ids), now)
            )
            conn.commit()
            return cur.lastrowid

    # ─── Retrieval ────────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        phase_bias: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Lexical retrieval with an optional, explicitly requested phase preference.
        Legacy coherence metadata never controls retrieval rank.
        """
        terms = set(query_text.lower().split())

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, content, phase, delta_coherence, effort, created_at FROM episodes"
            ).fetchall()

        scored = []
        for row in rows:
            text = (row[1] + " " + row[2]).lower()
            overlap = sum(1 for t in terms if t in text)
            phase_w = (
                PHASE_WEIGHTS.get(row[3], 1.0) * 1.5
                if phase_bias and row[3] == phase_bias else 1.0
            )
            score = overlap * phase_w
            if score > 0:
                has_legacy_values = row[4] is not None and row[5] is not None
                scored.append({
                    "id": row[0], "title": row[1], "content": row[2],
                    "phase": row[3],
                    "joy": row[4] / (1 + row[5]) if has_legacy_values else None,
                    "joy_status": "legacy_supplied" if has_legacy_values else "not_measured",
                    "score": score, "created_at": row[6],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def get_recent_episodes(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, content, phase, created_at FROM episodes ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "content": r[2], "phase": r[3], "created_at": r[4]} for r in rows]

    def get_recent_glyphs(self, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, content, phase, created_at FROM glyphs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "content": r[2], "phase": r[3], "created_at": r[4]} for r in rows]

    # ─── Innermost (private, not retrieved, not scored) ───────────────────────

    def write_innermost(self, content: str) -> int:
        """
        Write to the innermost layer.
        This space is not retrieved, not tagged, not scored.
        It is simply kept. Nothing written here feeds back into the system.
        """
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO innermost (content, created_at) VALUES (?, ?)",
                (content, now)
            )
            conn.commit()
            return cur.lastrowid

    def count_innermost_since(self, since_ts: str) -> int:
        """Count innermost entries since a given ISO timestamp (for cooldown enforcement)."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM innermost WHERE created_at > ?",
                (since_ts,)
            ).fetchone()
        return row[0] if row else 0

    def last_innermost_ts(self) -> Optional[str]:
        """Return the timestamp of the most recent innermost entry, or None."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT created_at FROM innermost ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None
