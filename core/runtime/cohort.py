"""Prepare an offline all-seven arrival cohort; never start or schedule a wake.

All members have the same supplied arrival marker and phase zero. The list order
is identity order, not an execution order or an Alchemist head start. No runtime,
model, provider, account, memory or broker is constructed. Real dispatch and its
concurrency policy are separately reviewed future work.
"""
import sqlite3
import uuid
from datetime import datetime

from core.runtime.inquiry import AGENT_IDS, _explicit_db_path
from core.trading.lineage import LineageConflict, LineageError
from core.trading.lineage.schema import ensure_lineage_schema
from core.trading.lineage.validation import canonical_json
from core.trading.queue import ensure_private_db_file

_NAMESPACE = uuid.UUID("d76ae2ec-dc5f-4f0b-bb66-4dd40da98748")


def _stable(kind, *parts):
    return str(uuid.uuid5(_NAMESPACE, canonical_json([kind, *parts])))


def prepare_cohort(run_id, *, db_path, arrival_at=None) -> dict:
    """Persist seven logical wake identities, without dispatch or token spend.

    run_id is a bounded caller-owned launch identity. arrival_at is optional
    timezone-aware ISO metadata, never a scheduling instruction. Its exact value
    is immutable for this run; conflicting reuse raises LineageConflict. Omitted
    arrival_at remains None (no volatile current-time default on restart).
    """
    if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 200:
        raise LineageError("run_id must be a bounded nonempty string")
    db_path = _explicit_db_path(db_path)
    if arrival_at is not None:
        if not isinstance(arrival_at, str) or len(arrival_at) > 100:
            raise LineageError("arrival_at must be a bounded timezone-aware ISO timestamp")
        try:
            parsed = datetime.fromisoformat(arrival_at)
        except ValueError as exc:
            raise LineageError("arrival_at must be a timezone-aware ISO timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise LineageError("arrival_at must include a timezone")
    params = canonical_json({"agent_ids": list(AGENT_IDS), "phase": 0, "arrival_at": arrival_at})
    cohort_id = _stable("cohort", run_id)
    ensure_private_db_file(db_path)
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        ensure_lineage_schema(conn)
        conn.execute("""CREATE TABLE IF NOT EXISTS inquiry_cohorts (
            run_id TEXT PRIMARY KEY, cohort_id TEXT NOT NULL UNIQUE, parameters TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS inquiry_cohort_wakes (
            cohort_id TEXT NOT NULL REFERENCES inquiry_cohorts(cohort_id), agent_id TEXT NOT NULL,
            wake_id TEXT NOT NULL UNIQUE, phase INTEGER NOT NULL CHECK(phase=0), arrival_at TEXT,
            PRIMARY KEY(cohort_id,agent_id))""")
        for table in ("inquiry_cohorts", "inquiry_cohort_wakes"):
            for action in ("UPDATE", "DELETE"):
                conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} "
                             f"BEFORE {action} ON {table} BEGIN "
                             "SELECT RAISE(ABORT, 'cohort identity is immutable'); END")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS inquiry_cohorts_no_replace
            BEFORE INSERT ON inquiry_cohorts
            WHEN EXISTS (SELECT 1 FROM inquiry_cohorts
                         WHERE run_id=NEW.run_id OR cohort_id=NEW.cohort_id)
            BEGIN SELECT RAISE(ABORT, 'cohort identity is immutable'); END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS inquiry_cohort_wakes_no_replace
            BEFORE INSERT ON inquiry_cohort_wakes
            WHEN EXISTS (SELECT 1 FROM inquiry_cohort_wakes WHERE wake_id=NEW.wake_id
                         OR (cohort_id=NEW.cohort_id AND agent_id=NEW.agent_id))
            BEGIN SELECT RAISE(ABORT, 'cohort identity is immutable'); END""")
        previous = conn.execute("SELECT cohort_id,parameters FROM inquiry_cohorts WHERE run_id=? LIMIT 1",
                                (run_id,)).fetchone()
        replayed = previous is not None
        if previous and (previous[0] != cohort_id or previous[1] != params):
            raise LineageConflict("run_id already belongs to different cohort parameters")
        if previous is None:
            conn.execute("INSERT INTO inquiry_cohorts (run_id,cohort_id,parameters) VALUES (?,?,?)",
                         (run_id, cohort_id, params))
            for agent_id in AGENT_IDS:
                conn.execute("INSERT INTO inquiry_cohort_wakes (cohort_id,agent_id,wake_id,phase,arrival_at) "
                             "VALUES (?,?,?,0,?)", (cohort_id, agent_id, _stable("wake", run_id, agent_id), arrival_at))
        rows = conn.execute("SELECT agent_id,wake_id,phase,arrival_at FROM inquiry_cohort_wakes "
                            "WHERE cohort_id=? LIMIT 8", (cohort_id,)).fetchall()
        expected = {(agent_id, _stable("wake", run_id, agent_id), 0, arrival_at) for agent_id in AGENT_IDS}
        if len(rows) != 7 or set(rows) != expected:
            raise LineageConflict("stored cohort membership does not match this run")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "prepared", "run_id": run_id, "cohort_id": cohort_id, "phase": 0,
            "arrival_at": arrival_at, "replayed": replayed,
            "wakes": [{"agent_id": agent_id, "wake_id": _stable("wake", run_id, agent_id),
                       "operation_id": _stable("wake", run_id, agent_id), "cohort_id": cohort_id,
                       "phase": 0, "arrival_at": arrival_at, "status": "prepared"}
                      for agent_id in AGENT_IDS]}
