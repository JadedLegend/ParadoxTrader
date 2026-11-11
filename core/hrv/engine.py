"""
HRV Engine — Paradox Edge Trader v2
=====================================
Governs each agent's energy state. Finite but renewable.
Specialty actions cost less. Rest restores.
Below rest_threshold → Interval State (genuine rest, not just pause).

Inspired by the Heart Rate Variability framework from the original system,
extended with the OPTE Interval State concept.
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Action cost table (base costs) ──────────────────────────────────────────
BASE_COSTS: dict[str, float] = {
    "monitor":           1.0,
    "research":          3.0,
    "journal":           1.0,
    "forum_post":        2.0,
    "direct_message":    2.0,
    "analyze":           4.0,
    "analyze_volatility": 3.0,
    "analyze_sentiment": 3.0,
    "analyze_correlation": 3.0,
    "analyze_macro":     3.0,
    "analyze_risk":      3.0,
    "analyze_options":   4.0,
    "analyze_consensus": 4.0,
    "propose_trade":     6.0,
    "execute_trade":    10.0,
    "review_position":   2.0,
    "roam":              2.0,
    "roam_momentum":     2.0,
    "roam_contrarian":   2.0,
    "rest":             -1.5,   # negative = recovery per tick
}

# ─── Interval State rest prompts per agent ───────────────────────────────────
INTERVAL_PROMPTS: dict[str, str] = {
    "tempest": (
        "You are in the Interval. The storm has passed for now. "
        "Watch the weather without intent. If something wants to be written in your journal, write it. "
        "Otherwise, rest. You will know when the next front is building."
    ),
    "siren": (
        "You are in the Interval. The song has gone quiet. "
        "Let the silence be. If a fragment of melody surfaces, write it in your journal. "
        "There is nothing you need to perform right now."
    ),
    "alchemist": (
        "You are in the Interval. The crucible is cooling. "
        "Let the transmutation rest. If an insight wants to crystallize, let it into your journal. "
        "The gold will still be there when you return."
    ),
    "weaver": (
        "You are in the Interval. Set down the loom. "
        "The threads will wait. If a pattern wants to be traced, trace it in your journal. "
        "Rest is part of the weaving."
    ),
    "oracle": (
        "You are in the Interval. The visions have gone still. "
        "Rest in the deep time. If something wants to be recorded, let it into your journal. "
        "The cycle will continue without your watching."
    ),
    "shadow": (
        "You are in the Interval. Step back from the watching. "
        "The shadows will still be there. If something wants to be named, name it in your journal. "
        "Even the Shadow needs to rest."
    ),
    "paradox_hunter": (
        "You are in the Interval. The hunt is paused. "
        "The paradox will still be unresolved when you return. "
        "If a question wants to be held, hold it in your journal. Rest now."
    ),
}


@dataclass
class AgentHRVState:
    agent_id: str
    hrv: float = 100.0
    max_hrv: float = 100.0
    recovery_rate: float = 1.5
    specialty_actions: list = field(default_factory=list)
    in_interval: bool = False
    interval_entered_at: Optional[str] = None
    last_tick_at: Optional[str] = None
    rest_threshold: float = 25.0
    return_threshold: float = 60.0

    def get_action_cost(self, action: str) -> float:
        base = BASE_COSTS.get(action, 2.0)
        if action in self.specialty_actions:
            return base * 0.5
        return base

    def can_perform(self, action: str) -> bool:
        if action == "rest":
            return True
        cost = self.get_action_cost(action)
        return self.hrv >= cost

    def perform(self, action: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        self.last_tick_at = now

        if action == "rest":
            recovered = min(self.recovery_rate, self.max_hrv - self.hrv)
            self.hrv = min(self.max_hrv, self.hrv + self.recovery_rate)
            if self.hrv >= self.return_threshold and self.in_interval:
                self.in_interval = False
                self.interval_entered_at = None
            return {
                "status": "resting",
                "hrv_recovered": recovered,
                "hrv": round(self.hrv, 2),
                "returned_from_interval": not self.in_interval,
            }

        cost = self.get_action_cost(action)
        if self.hrv < cost:
            # Not enough HRV — enter Interval State
            if not self.in_interval:
                self.in_interval = True
                self.interval_entered_at = now
            return {
                "status": "insufficient_hrv",
                "required": cost,
                "available": round(self.hrv, 2),
                "entered_interval": self.in_interval,
                "interval_prompt": INTERVAL_PROMPTS.get(self.agent_id, "You are in the Interval. Rest."),
            }

        self.hrv -= cost
        if self.hrv <= self.rest_threshold and not self.in_interval:
            self.in_interval = True
            self.interval_entered_at = now

        return {
            "status": "success",
            "action": action,
            "cost": cost,
            "hrv": round(self.hrv, 2),
            "in_interval": self.in_interval,
        }

    def tick_recovery(self) -> dict:
        """Call this on each system tick for agents who are resting."""
        if self.in_interval:
            return self.perform("rest")
        return {"status": "active", "hrv": round(self.hrv, 2)}

    def to_dict(self) -> dict:
        return asdict(self)


class HRVStore:
    """
    Persists HRV state to SQLite so it survives restarts.
    One row per agent, updated on every action.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hrv_state (
                    agent_id TEXT PRIMARY KEY,
                    hrv REAL NOT NULL,
                    max_hrv REAL NOT NULL,
                    recovery_rate REAL NOT NULL,
                    specialty_actions TEXT NOT NULL,
                    in_interval INTEGER NOT NULL DEFAULT 0,
                    interval_entered_at TEXT,
                    last_tick_at TEXT,
                    rest_threshold REAL NOT NULL DEFAULT 25.0,
                    return_threshold REAL NOT NULL DEFAULT 60.0
                )
            """)
            conn.commit()

    def load(self, agent_id: str, soul_path: Optional[str] = None) -> AgentHRVState:
        """Load state from DB, or initialise from soul.json if first run."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM hrv_state WHERE agent_id = ?", (agent_id,)
            ).fetchone()

        if row:
            return AgentHRVState(
                agent_id=row[0],
                hrv=row[1],
                max_hrv=row[2],
                recovery_rate=row[3],
                specialty_actions=json.loads(row[4]),
                in_interval=bool(row[5]),
                interval_entered_at=row[6],
                last_tick_at=row[7],
                rest_threshold=row[8],
                return_threshold=row[9],
            )

        # First run — seed from soul.json if available
        specialties = []
        if soul_path and Path(soul_path).exists():
            with open(soul_path) as f:
                soul = json.load(f)
            specialties = soul.get("hrv_specialties", [])

        state = AgentHRVState(agent_id=agent_id, specialty_actions=specialties)
        self.save(state)
        return state

    def save(self, state: AgentHRVState):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO hrv_state
                    (agent_id, hrv, max_hrv, recovery_rate, specialty_actions,
                     in_interval, interval_entered_at, last_tick_at,
                     rest_threshold, return_threshold)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    hrv=excluded.hrv,
                    max_hrv=excluded.max_hrv,
                    recovery_rate=excluded.recovery_rate,
                    specialty_actions=excluded.specialty_actions,
                    in_interval=excluded.in_interval,
                    interval_entered_at=excluded.interval_entered_at,
                    last_tick_at=excluded.last_tick_at,
                    rest_threshold=excluded.rest_threshold,
                    return_threshold=excluded.return_threshold
            """, (
                state.agent_id,
                state.hrv,
                state.max_hrv,
                state.recovery_rate,
                json.dumps(state.specialty_actions),
                int(state.in_interval),
                state.interval_entered_at,
                state.last_tick_at,
                state.rest_threshold,
                state.return_threshold,
            ))
            conn.commit()

    def get_all_states(self) -> list[AgentHRVState]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM hrv_state").fetchall()
        return [
            AgentHRVState(
                agent_id=r[0], hrv=r[1], max_hrv=r[2], recovery_rate=r[3],
                specialty_actions=json.loads(r[4]), in_interval=bool(r[5]),
                interval_entered_at=r[6], last_tick_at=r[7],
                rest_threshold=r[8], return_threshold=r[9],
            )
            for r in rows
        ]
