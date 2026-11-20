"""A mechanical factual witness, not a model, agent, or memory writer.

Only witness.sqlite3 is writable. Readers never initialize files or schemas.
Source words stay in separately attributed originals, never in these accounts.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from threading import RLock
from uuid import uuid4

from .calls import CALL_OPTIONS
from .store import (OWNERS, CAPABILITIES, CHOICE_ACTIONS, JOURNAL_OPTIONS, LIMIT_CAPS, MAX_WAKES_PER_AGENT, RehearsalStore,
                    RehearsalError, RehearsalConflict, _integer, _safe, _uuid, _refs)

_LOCKS = {}
_LOCKS_GUARD = RLock()
_TERMINAL = {"completed", "failed", "stopped", "uncertain"}


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _scope(scope):
    if not isinstance(scope, str) or scope not in (*OWNERS, "steward"):
        raise RehearsalError("invalid witness scope")
    return scope


def _facts(snapshot, scope):
    """Project source facts only; unknown fields cannot become witness prose."""
    if (not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int
            or snapshot["schema_version"] != 1):
        raise RehearsalError("invalid witness snapshot")
    owner = None if scope == "steward" else scope
    if snapshot.get("owner") != owner:
        raise RehearsalError("witness snapshot scope mismatch")
    raw = snapshot["run"]
    run = {"run_id": _uuid(raw["run_id"]), "mode": raw["mode"], "status": raw["status"]}
    if run["mode"] not in ("offline", "real") or run["status"] not in ("prepared", "running", "completed", "stopped", "partial", "uncertain"):
        raise RehearsalError("invalid witness run")
    prepared = raw["prepared_owners"]
    expected = list(OWNERS) if owner is None else [owner]
    if prepared != expected:
        raise RehearsalError("invalid witness prepared owners")
    run["prepared_owners"] = prepared
    for field in ("created_at", "started_at", "ended_at"):
        value = raw.get(field)
        if value is not None and (not isinstance(value, str) or len(value) > 64):
            raise RehearsalError("invalid witness timestamp")
        run[field] = value
    jobs, requests = [], []
    if not isinstance(snapshot.get("jobs"), list) or len(snapshot["jobs"]) > 7 * MAX_WAKES_PER_AGENT:
        raise RehearsalError("invalid witness jobs")
    for raw in snapshot["jobs"]:
        agent = raw["agent_id"]
        if agent not in expected:
            raise RehearsalError("witness foreign owner")
        round_number = _integer(raw["round"], "round", 0, MAX_WAKES_PER_AGENT)
        wake = _safe(raw["wake_id"], "wake_id")
        if wake != f"{agent}-r{round_number}":
            raise RehearsalError("invalid witness wake")
        status, action = raw["status"], raw["action"]
        if status not in (*_TERMINAL, "pending", "running") or action not in (*CHOICE_ACTIONS, None):
            raise RehearsalError("invalid witness job")
        job = {"wake_id": wake, "agent_id": agent, "round": round_number,
               "status": status, "action": action,
               "choice_committed": raw.get("choice_committed") is True,
               "failure_code": _safe(raw.get("failure_code"), "failure_code", nullable=True),
               "record_refs": json.loads(_refs(raw.get("record_refs", [])))}
        mode = raw.get("journal_mode")
        if mode is not None:
            if action != "journal" or mode not in JOURNAL_OPTIONS["modes"]:
                raise RehearsalError("invalid witness journal mode")
            job["journal_mode"] = mode
        if "channels" in raw:
            channels = raw["channels"]
            if (not isinstance(channels, list) or not 1 <= len(channels) <= 3
                    or any(not isinstance(c, str) or c not in JOURNAL_OPTIONS["channels"] for c in channels)
                    or len(set(channels)) != len(channels)):
                raise RehearsalError("invalid witness channels")
            job["channels"] = channels
        context = raw.get("decision_context")
        job["offered_actions"] = None
        job["offered_journal_modes"] = None
        if context is not None:
            if context.get("offered_actions") != list(CAPABILITIES):
                raise RehearsalError("invalid witness offers")
            job["offered_actions"] = list(CAPABILITIES)
            if context.get("journal_options") is not None:
                if _dump(context["journal_options"]) != _dump(JOURNAL_OPTIONS):
                    raise RehearsalError("invalid witness journal offers")
                job["offered_journal_modes"] = list(JOURNAL_OPTIONS["modes"])
                job["offered_journal_options"] = dict(JOURNAL_OPTIONS)
            # A call is offered beside the five frozen offers, never among them.
            if context.get("call_options") is not None:
                if _dump(context["call_options"]) != _dump(CALL_OPTIONS):
                    raise RehearsalError("invalid witness call offers")
                job["call_offered"] = True
        jobs.append(job)
    if len({j["wake_id"] for j in jobs}) != len(jobs):
        raise RehearsalError("duplicate witness wake")
    if not isinstance(snapshot.get("requests"), list) or len(snapshot["requests"]) > LIMIT_CAPS["max_requests"]:
        raise RehearsalError("invalid witness requests")
    for raw in snapshot["requests"]:
        if not any(j["wake_id"] == raw["wake_id"] and j["agent_id"] == raw["agent_id"] for j in jobs):
            raise RehearsalError("witness request linkage mismatch")
        outcome = raw["outcome"]
        if outcome not in ("in_flight", "success", "http_error", "transport_error", "invalid_response", "failed", "uncertain", "not_sent"):
            raise RehearsalError("invalid witness request outcome")
        if raw["activity"] not in (*CAPABILITIES, "choice", "choose_action", "inquiry") or raw["dispatched"] not in (0, 1):
            raise RehearsalError("invalid witness request")
        requests.append({"request_id": _uuid(raw["request_id"], "request_id"),
                         "wake_id": raw["wake_id"], "agent_id": raw["agent_id"],
                         "activity": raw["activity"], "dispatched": bool(raw["dispatched"]),
                         "outcome": outcome,
                         "failure_code": _safe(raw.get("failure_code"), "failure_code", nullable=True)})
    if len({r["request_id"] for r in requests}) != len(requests):
        raise RehearsalError("duplicate witness request")
    return {"run": run, "jobs": jobs, "requests": requests}


def _render(facts):
    run, jobs, requests = facts["run"], facts["jobs"], facts["requests"]
    refs = [{"kind": "run", "id": run["run_id"]}]
    began = {r["agent_id"] for r in requests if r["dispatched"]}
    per_owner = {owner: [j for j in jobs if j["agent_id"] == owner] for owner in run["prepared_owners"]}
    complete_both = {owner for owner, owned in per_owner.items()
                     if owned and all(j["status"] == "completed" for j in owned)
                     and (len(owned) == 2 or any(len(o) != 2 for o in per_owner.values()))}
    # A rehearsal has exactly two wakes per owner; a day run has any number.
    wakes_phrase = "both wakes" if all(len(o) == 2 for o in per_owner.values()) else "every wake so far"
    counts = {status: sum(j["status"] == status for j in jobs)
              for status in ("completed", "failed", "stopped", "uncertain", "pending", "running")}
    lines = ["I keep only recorded facts; reasons and unrecorded events remain unknown.",
             f"This {run['mode']} run is {run['status']}.",
             f"Prepared owners: {len(run['prepared_owners'])}; owners with a dispatched request (actually began): {len(began)}; owners with {wakes_phrase} completed: {len(complete_both)}.",
             "Wake outcomes: " + "; ".join(f"{key}={value}" for key, value in counts.items() if value) + "."]
    record_counts = {}
    for job in jobs:
        refs.append({"kind": "wake", "id": job["wake_id"], "agent_id": job["agent_id"]})
        for ref in job["record_refs"]:
            owned = {**ref, "agent_id": job["agent_id"]}
            if owned not in refs:
                refs.append(owned)
    for request in requests:
        refs.append({"kind": "request", "id": request["request_id"], "agent_id": request["agent_id"]})
    uncertain = sum(r["outcome"] in ("in_flight", "uncertain") for r in requests)
    lines.append(f"Requests recorded: {len(requests)}; unresolved/uncertain: {uncertain}.")
    offered = [j for j in jobs if j["offered_actions"] is not None]
    if offered:
        lines.append("Recorded menu: " + ", ".join(CAPABILITIES) + ".")
    if any(j["offered_journal_modes"] is not None for j in jobs):
        lines.append("Journal submodes offered: " + ", ".join(JOURNAL_OPTIONS["modes"]) + ".")
    call_offers = sum(j.get("call_offered") is True for j in jobs)
    if call_offers:
        lines.append(f"Call offered beside the market window on {call_offers} wakes.")
    if len(offered) < len(jobs):
        lines.append(f"Historical offers unknown (no historical offer snapshot) for {len(jobs) - len(offered)} wakes.")
    if len(run["prepared_owners"]) == 1:
        for job in jobs:
            selected = str(job["action"]) if job["choice_committed"] else "unknown (no committed choice)"
            line = f"{job['wake_id']}: selected {selected}; outcome: {job['status']}."
            if job["choice_committed"] and job["action"] == "journal":
                line += " Journal mode: " + job.get("journal_mode", "legacy plain journal (no explicit mode recorded)") + "."
            if "channels" in job:
                line += " Channels: " + ", ".join(job["channels"]) + "."
            if job["failure_code"]:
                line += f" Recorded code: {job['failure_code']}."
            lines.append(line)
    else:
        actions = {action: sum(j["choice_committed"] and j["action"] == action for j in jobs) for action in CHOICE_ACTIONS}
        modes = {mode: sum(j["choice_committed"] and j.get("journal_mode") == mode for j in jobs) for mode in JOURNAL_OPTIONS["modes"]}
        lines.append("Committed choices (wake counts): " + (", ".join(f"{k}={v}" for k, v in actions.items() if v) or "0") + ".")
        if any(modes.values()):
            lines.append("Journal modes (wake counts): " + ", ".join(f"{k}={v}" for k, v in modes.items() if v) + ".")
        legacy = sum(j["choice_committed"] and j["action"] == "journal" and "journal_mode" not in j for j in jobs)
        if legacy:
            lines.append(f"Plain journals without an explicit mode recorded: {legacy}.")
    unchosen = sum(not j["choice_committed"] for j in jobs)
    if unchosen:
        lines.append(f"No committed choice recorded for {unchosen} wakes; this is not evidence of rest.")
    for ref in refs:
        if ref["kind"] not in ("run", "wake", "request"):
            record_counts[ref["kind"]] = record_counts.get(ref["kind"], 0) + 1
    lines.append("Distinct attached source references: " + (", ".join(f"{k}={v}" for k, v in sorted(record_counts.items())) or "0") + ". Full facts and identifiers are kept alongside this account; source words remain with their authors.")
    return "\n".join(lines), refs


class WitnessStore:
    def __init__(self, db_path):
        raw = Path(db_path)
        if ".." in raw.parts or raw.name != "witness.sqlite3":
            raise RehearsalError("invalid witness file")
        self.db_path = Path(os.path.abspath(raw))
        self._check()
        with _LOCKS_GUARD:
            self._writer_lock = _LOCKS.setdefault(str(self.db_path), RLock())

    def _check(self):
        for path in [self.db_path, *(Path(str(self.db_path) + s) for s in ("-wal", "-shm", "-journal"))]:
            RehearsalStore._check_path(path)
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue  # A normal transient SQLite sidecar may disappear.
            if not stat.S_ISREG(mode):
                raise RehearsalError("invalid witness file")

    @contextmanager
    def _connection(self, write=False):
        self._check()
        if write:
            missing = []
            parent = self.db_path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for parent in reversed(missing):
                try:
                    parent.mkdir(mode=0o700)
                except FileExistsError:
                    self._check()
            try:
                fd = os.open(self.db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                self._check()
            else:
                os.close(fd)
        elif not self.db_path.is_file():
            yield None
            return
        conn = None
        try:
            conn = sqlite3.connect(self.db_path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write:
                for path in [self.db_path, *(Path(str(self.db_path) + s) for s in ("-wal", "-shm", "-journal"))]:
                    try:
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                    except FileNotFoundError:
                        continue
                    try:
                        if not stat.S_ISREG(os.fstat(fd).st_mode):
                            raise RehearsalError("invalid witness file")
                        os.fchmod(fd, 0o600)
                    finally:
                        os.close(fd)
                conn.execute("CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, operation_key TEXT UNIQUE NOT NULL, scope TEXT NOT NULL, content TEXT NOT NULL, source_refs TEXT NOT NULL, source_digest TEXT NOT NULL, created_at TEXT NOT NULL, source_facts TEXT)")
                columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
                if "source_facts" not in columns:
                    conn.execute("ALTER TABLE accounts ADD COLUMN source_facts TEXT")
                conn.execute("CREATE TRIGGER IF NOT EXISTS immutable_witness BEFORE UPDATE ON accounts BEGIN SELECT RAISE(ABORT,'append only witness'); END")
                conn.execute("CREATE TRIGGER IF NOT EXISTS no_delete_witness BEFORE DELETE ON accounts BEGIN SELECT RAISE(ABORT,'append only witness'); END")
            else:
                conn.execute("PRAGMA query_only=ON")
            yield conn
            if write:
                conn.commit()
        except sqlite3.Error:
            raise RehearsalError("unavailable witness state") from None
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _account(row):
        return {"id": row["id"], "scope": row["scope"], "content": row["content"],
                "source_refs": json.loads(row["source_refs"]), "source_digest": row["source_digest"],
                "source_facts": json.loads(row["source_facts"]) if "source_facts" in row.keys() and row["source_facts"] is not None else None,
                "author": "witness", "method": "mechanical", "created_at": row["created_at"]}

    def record(self, snapshot, *, scope="steward", operation_key):
        scope = _scope(scope)
        if (not isinstance(operation_key, str) or not 1 <= len(operation_key) <= 256
                or any(ord(c) < 32 for c in operation_key)):
            raise RehearsalError("invalid witness operation key")
        facts = _facts(snapshot, scope)
        digest = hashlib.sha256(_dump(facts).encode("utf-8")).hexdigest()
        content, refs = _render(facts)
        with self._writer_lock, self._connection(write=True) as conn:
            prior = conn.execute("SELECT id,scope,content,source_refs,source_digest,created_at,source_facts FROM accounts WHERE operation_key=? LIMIT 1", (operation_key,)).fetchone()
            if prior is not None:
                if prior["scope"] != scope or prior["source_digest"] != digest or prior["content"] != content or prior["source_refs"] != _dump(refs) or prior["source_facts"] != _dump(facts):
                    raise RehearsalConflict("witness operation conflict")
                return self._account(prior)
            ident, now = str(uuid4()), datetime.now(timezone.utc).isoformat()
            conn.execute("INSERT INTO accounts(id,operation_key,scope,content,source_refs,source_digest,created_at,source_facts) VALUES (?,?,?,?,?,?,?,?)", (ident, operation_key, scope, content, _dump(refs), digest, now, _dump(facts)))
            row = conn.execute("SELECT id,scope,content,source_refs,source_digest,created_at,source_facts FROM accounts WHERE id=? LIMIT 1", (ident,)).fetchone()
            return self._account(row)

    def list_accounts(self, scope, limit=3, offset=0):
        scope = _scope(scope)
        _integer(limit, "limit", 1, 20)
        _integer(offset, "offset", 0, 1_000_000)
        with self._connection() as conn:
            if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts' LIMIT 1").fetchone():
                return {"status": "missing", "accounts": [], "total": 0}
            total = conn.execute("SELECT COUNT(*) FROM accounts WHERE scope=?", (scope,)).fetchone()[0]
            columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
            facts = "source_facts" if "source_facts" in columns else "NULL AS source_facts"
            rows = conn.execute("SELECT id,scope,content,source_refs,source_digest,created_at," + facts + " FROM accounts WHERE scope=? ORDER BY rowid DESC LIMIT ? OFFSET ?", (scope, limit, offset)).fetchall()
            return {"status": "ok", "accounts": [self._account(row) for row in rows], "total": total}

    def get_account(self, ident, scope):
        scope, ident = _scope(scope), _uuid(ident, "account id")
        with self._connection() as conn:
            if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts' LIMIT 1").fetchone():
                return None
            columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
            facts = "source_facts" if "source_facts" in columns else "NULL AS source_facts"
            row = conn.execute("SELECT id,scope,content,source_refs,source_digest,created_at," + facts + " FROM accounts WHERE id=? AND scope=? LIMIT 1", (ident, scope)).fetchone()
            return None if row is None else self._account(row)
