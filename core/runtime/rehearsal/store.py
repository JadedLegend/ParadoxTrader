"""Explicit, private finite rehearsal state. Importing/reading never prepares a run.

The control database has immutable manifest/jobs, write-once private choice and
output checkpoints, and a metadata-only admission ledger. A controller token is
not an expiring lease: only explicit operator recovery can revoke it. Admission
reservations remain charged even when the result is unknown (or fails).
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from uuid import UUID, uuid4

from core.usage.pricing import (decimal_add as _decimal_add, decimal_text as _decimal_text,
                                decimal_value, validate_model)

AGENT_IDS = OWNERS = (
    "tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter",
)
CAPABILITIES = ("rest", "journal", "inquire", "library", "roam")
DEFAULT_LIMITS = {
    "wakes_per_agent": 2, "max_requests": 28, "max_output_tokens": 1024,
    "max_input_bytes": 24000, "max_runtime_seconds": 900,
    "request_timeout_seconds": 60, "max_parallelism": 3,
}
_SAFE = re.compile(r"[a-zA-Z0-9_.:-]{1,128}\Z")
_LABEL = re.compile(r"[a-zA-Z0-9_.:/+@ -]{1,128}\Z")
_TERMINAL = frozenset({"completed", "failed", "stopped", "uncertain"})
_OUTCOMES = frozenset({"success", "http_error", "transport_error", "invalid_response", "failed", "uncertain", "not_sent"})
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens")
_RUN_FILES = frozenset({
    "control.sqlite3", "usage.sqlite3", "trade_queue.sqlite3", "library.sqlite3",
    "library_corpus.json", "profiles/snapshot.json",
    *(f"profiles/{owner}_{kind}.json" for owner in OWNERS for kind in ("soul", "living")),
    *(f"memory/{owner}.sqlite3" for owner in OWNERS),
    *(f"memory/{owner}-{owner}-r{round_number}-library.json" for owner in OWNERS for round_number in (1, 2)),
})


class RehearsalError(ValueError):
    """Bounded safe error, with no provider content or credentials."""


class RehearsalConflict(RehearsalError):
    pass


class RehearsalStopped(RehearsalError):
    pass


class RehearsalBudgetExceeded(RehearsalError):
    pass


def decimal_add(left, right):
    # Reuse exact bounded helpers, but do not inherit a caller's tiny exponent
    # range. Valid leaf decimals have magnitude/exponent in [-100, 100].
    with localcontext() as context:
        context.Emax, context.Emin, context.clamp = 999, -999, 0
        return _decimal_add(left, right)


def decimal_text(value):
    with localcontext() as context:
        context.Emax, context.Emin, context.clamp = 999, -999, 0
        return _decimal_text(value)


def _integer(value, field, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise RehearsalError(f"invalid {field}")
    return value


def _safe(value, field, *, nullable=False, label=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not (_LABEL if label else _SAFE).fullmatch(value):
        raise RehearsalError(f"invalid {field}")
    return value


def _money(value, field):
    try:
        return decimal_value(value, field)
    except (ValueError, OverflowError):
        raise RehearsalError(f"invalid {field}") from None


def _model(value):
    try:
        return validate_model(value)
    except ValueError:
        raise RehearsalError("invalid model") from None


def _uuid(value, field="run_id"):
    if not isinstance(value, str) or len(value) != 36:
        raise RehearsalError(f"invalid {field}")
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise RehearsalError(f"invalid {field}") from None
    return value


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _validate_manifest(raw):
    """Local pure validation; no provider/network/scheduler import is needed.

    The provider may perform additional real-catalog readiness validation before
    prepare. This store independently enforces all persisted finite bounds.
    """
    keys = {"schema_version", "mode", "agent_models", "limits", "catalog_snapshot", "capabilities"}
    if not isinstance(raw, dict) or set(raw) != keys or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
        raise RehearsalError("invalid manifest")
    if raw["mode"] not in ("offline", "real"):
        raise RehearsalError("invalid mode")
    models = raw["agent_models"]
    if not isinstance(models, dict) or set(models) != set(OWNERS):
        raise RehearsalError("invalid agent_models")
    models = {owner: _model(models[owner]) for owner in OWNERS}
    limits = raw["limits"]
    if not isinstance(limits, dict) or set(limits) != set(DEFAULT_LIMITS) | {"budget_usd"}:
        raise RehearsalError("invalid limits")
    limits = {name: _integer(limits[name], name, 1, cap) for name, cap in DEFAULT_LIMITS.items()} | {"budget_usd": raw["limits"]["budget_usd"]}
    if limits["wakes_per_agent"] != 2:
        raise RehearsalError("two rounds required")
    if not isinstance(limits["budget_usd"], str):
        raise RehearsalError("invalid budget_usd")
    budget = _money(limits["budget_usd"], "budget_usd")
    if raw["mode"] == "real" and budget == 0:
        raise RehearsalError("real budget must be positive")
    limits["budget_usd"] = decimal_text(budget)
    caps = raw["capabilities"]
    if caps != list(CAPABILITIES):
        raise RehearsalError("invalid capabilities")
    catalog = raw["catalog_snapshot"]
    if not isinstance(catalog, dict) or set(catalog) - {"models", "source", "captured_at"} or not isinstance(catalog.get("models"), list):
        raise RehearsalError("invalid catalog_snapshot")
    source = catalog.get("source")
    if raw["mode"] == "offline" and source != "synthetic":
        raise RehearsalError("explicit synthetic catalog required")
    if raw["mode"] == "real" and source not in (None, "openrouter"):
        raise RehearsalError("real catalog required")
    selected = set(models.values())
    frozen = []
    seen = set()
    for item in catalog["models"]:
        required = {"id", "context_length", "max_completion_tokens", "supported_parameters", "pricing"}
        if not isinstance(item, dict) or set(item) != required:
            raise RehearsalError("invalid catalog model")
        model = _model(item["id"])
        if model not in selected or model in seen:
            raise RehearsalError("invalid catalog selection")
        seen.add(model)
        context = _integer(item["context_length"], "context_length", 1, 100_000_000)
        completion = _integer(item["max_completion_tokens"], "max_completion_tokens", 1, 100_000_000)
        if completion < limits["max_output_tokens"] or context < limits["max_output_tokens"] + limits["max_input_bytes"]:
            raise RehearsalError("insufficient model context or completion cap")
        parameters = item["supported_parameters"]
        if (not isinstance(parameters, list) or not 1 <= len(parameters) <= 100
                or any(not isinstance(p, str) or not re.fullmatch(r"[a-z_]{1,80}", p) for p in parameters)
                or len(parameters) != len(set(parameters)) or "max_tokens" not in parameters):
            raise RehearsalError("unsupported model parameters")
        pricing = item["pricing"]
        if not isinstance(pricing, dict) or not {"prompt", "completion", "request"} <= set(pricing):
            raise RehearsalError("unsupported catalog pricing")
        normalized_prices = {}
        for name, value in pricing.items():
            rate = _money(value, "pricing")
            if rate > Decimal("1000") or (name not in ("prompt", "completion", "request") and rate != 0):
                raise RehearsalError("unsupported catalog pricing")
            if name in ("prompt", "completion", "request"):
                normalized_prices[name] = decimal_text(rate)
        frozen.append({"id": model, "context_length": context, "max_completion_tokens": completion,
                       "supported_parameters": sorted(parameters), "pricing": normalized_prices})
    if seen != selected:
        raise RehearsalError("catalog missing selected models")
    snapshot = {"models": sorted(frozen, key=lambda item: item["id"])}
    if source is not None:
        snapshot["source"] = source
    if "captured_at" in catalog:
        captured = catalog["captured_at"]
        try:
            if not isinstance(captured, str) or len(captured) > 64:
                raise ValueError()
            stamp = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError()
        except ValueError:
            raise RehearsalError("invalid catalog capture time") from None
        snapshot["captured_at"] = captured
    return {"schema_version": 1, "mode": raw["mode"], "agent_models": models,
            "limits": limits, "catalog_snapshot": snapshot, "capabilities": list(CAPABILITIES)}


def _choice(value):
    if not isinstance(value, dict) or set(value) - {"action", "query"} or value.get("action") not in CAPABILITIES:
        raise RehearsalError("invalid choice")
    if "query" in value:
        query = value["query"]
        if value["action"] != "library" or not isinstance(query, str) or not query.strip():
            raise RehearsalError("invalid library query")
        try:
            if len(query.encode("utf-8")) > 2000:
                raise RehearsalError("invalid library query")
        except UnicodeError:
            raise RehearsalError("invalid library query") from None
    return _dump(value)


def _refs(value):
    if value is None:
        return "[]"
    if not isinstance(value, list) or len(value) > 128:
        raise RehearsalError("invalid record_refs")
    result = []
    for ref in value:
        if not isinstance(ref, dict) or set(ref) != {"kind", "id"} or ref["kind"] not in ("journal", "episode", "inquiry", "library"):
            raise RehearsalError("invalid record ref")
        ident = ref["id"]
        if type(ident) is int:
            _integer(ident, "record id", 1, 2**63 - 1)
        elif ref["kind"] == "inquiry":
            _uuid(ident, "record id")
        else:
            _safe(ident, "record id")
        result.append({"kind": ref["kind"], "id": ident})
    return _dump(result)


def _usage(raw):
    # Only explicitly recognized numeric metadata survives; raw content is never stored.
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise RehearsalError("invalid usage")
    aliases = {"input_tokens": "prompt_tokens", "output_tokens": "completion_tokens"}
    result = {}
    for field in _TOKEN_FIELDS:
        value = raw.get(field, raw.get(aliases.get(field, "")))
        result[field] = None if value is None else _integer(value, field, 0, 10_000_000_000)
    value = raw.get("provider_cost_usd", raw.get("cost_usd", raw.get("cost")))
    result["cost_usd"] = None if value is None else decimal_text(_money(value, "cost_usd"))
    status = raw.get("cost_status", "reported")
    if status not in ("reported", "estimated", "unknown"):
        raise RehearsalError("invalid cost_status")
    result["cost_status"] = "unknown" if value is None else status
    if value is not None and status == "unknown":
        raise RehearsalError("invalid cost coverage")
    return result


_SCHEMA = """
CREATE TABLE runs (
 run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, status TEXT NOT NULL,
 created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
 stop_requested INTEGER NOT NULL DEFAULT 0, controller_token TEXT, deadline REAL
);
CREATE TABLE jobs (
 wake_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, round INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', action TEXT, failure_code TEXT,
 requested_model TEXT NOT NULL, response_model TEXT, provider TEXT,
 request_count INTEGER NOT NULL DEFAULT 0, duration_ms REAL NOT NULL DEFAULT 0,
 record_refs TEXT NOT NULL DEFAULT '[]', updated_at TEXT NOT NULL,
 choice TEXT, output TEXT
);
CREATE TABLE requests (
 request_id TEXT PRIMARY KEY, wake_id TEXT NOT NULL REFERENCES jobs(wake_id),
 agent_id TEXT NOT NULL, activity TEXT NOT NULL, requested_model TEXT NOT NULL,
 input_bytes INTEGER NOT NULL, max_output_tokens INTEGER NOT NULL,
 reserved_usd TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT,
 outcome TEXT NOT NULL DEFAULT 'in_flight', response_model TEXT, provider TEXT,
 duration_ms REAL NOT NULL DEFAULT 0, usage TEXT NOT NULL, failure_code TEXT,
 dispatched INTEGER NOT NULL DEFAULT 0, controller_token TEXT NOT NULL
);
CREATE TRIGGER immutable_manifest BEFORE UPDATE OF run_id,manifest,created_at ON runs
 BEGIN SELECT RAISE(ABORT,'immutable run'); END;
CREATE TRIGGER immutable_job BEFORE UPDATE OF wake_id,agent_id,round,requested_model ON jobs
 BEGIN SELECT RAISE(ABORT,'immutable job'); END;
CREATE TRIGGER immutable_choice BEFORE UPDATE OF choice ON jobs WHEN OLD.choice IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable choice'); END;
CREATE TRIGGER immutable_output BEFORE UPDATE OF output ON jobs WHEN OLD.output IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'immutable output'); END;
CREATE TRIGGER immutable_request BEFORE UPDATE OF request_id,wake_id,agent_id,activity,requested_model,input_bytes,max_output_tokens,reserved_usd,created_at,controller_token ON requests
 BEGIN SELECT RAISE(ABORT,'immutable request'); END;
CREATE TRIGGER no_delete_requests BEFORE DELETE ON requests
 BEGIN SELECT RAISE(ABORT,'append only requests'); END;
"""


class RehearsalStore:
    def __init__(self, root):
        try:
            raw = Path(root).expanduser()
        except (TypeError, ValueError):
            raise RehearsalError("invalid run root") from None
        if ".." in raw.parts:
            raise RehearsalError("run root traversal forbidden")
        self.root = Path(os.path.abspath(raw))
        self._check_path(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise RehearsalError("invalid run root")

    @staticmethod
    def _check_path(path):
        # Check every existing component before resolving/opening. Reads never mkdir.
        for item in reversed((path, *path.parents)):
            try:
                mode = item.lstat().st_mode
            except FileNotFoundError:
                continue
            except OSError:
                raise RehearsalError("unavailable run path") from None
            if stat.S_ISLNK(mode):
                raise RehearsalError("symlink run path forbidden")
            if item != path and not stat.S_ISDIR(mode):
                raise RehearsalError("invalid run path")
        return path

    def run_path(self, run_id):
        path = self.root / _uuid(run_id)
        self._check_path(path)
        if path.exists() and not path.is_dir():
            raise RehearsalError("invalid run directory")
        return path

    def safe_run_file(self, run_id, relative):
        """Check fixed run-local files and SQLite sidecars, without creating them.

        This rejects preexisting symlinks, not concurrent tampering by the owner
        of the private (0700) run directories. It does not create missing files.
        """
        if isinstance(relative, Path):
            relative = relative.as_posix()
        if not isinstance(relative, str) or relative not in _RUN_FILES:
            raise RehearsalError("invalid run file")
        path = self.run_path(run_id) / relative
        candidates = [path]
        if path.suffix == ".sqlite3":
            candidates.extend(Path(str(path) + suffix) for suffix in ("-journal", "-wal", "-shm"))
        for candidate in candidates:
            self._check_path(candidate)
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError:
                # SQLite sidecars may disappear normally as another worker
                # commits. One stat result avoids exists()/is_file() races.
                continue
            except OSError:
                raise RehearsalError("unavailable run path") from None
            if not stat.S_ISREG(mode):
                raise RehearsalError("invalid run file")
        return path

    def _db_path(self, run_id):
        path = self.safe_run_file(run_id, "control.sqlite3")
        if not path.is_file():
            raise RehearsalError("run not found")
        return path

    @contextmanager
    def _connection(self, run_id, *, write=False):
        path = self._db_path(run_id)
        connection = None
        try:
            connection = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            if write:
                os.chmod(path, 0o600)
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except sqlite3.Error:
            if connection is not None:
                connection.rollback()
            raise RehearsalError("unavailable rehearsal state") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _private_dirs(path):
        missing = []
        current = path
        while not current.exists():
            missing.append(current)
            current = current.parent
        RehearsalStore._check_path(path)
        for item in reversed(missing):
            try:
                item.mkdir(mode=0o700)
            except FileExistsError:
                RehearsalStore._check_path(item)
        if not path.is_dir():
            raise RehearsalError("invalid run root")
        os.chmod(path, 0o700)

    def prepare(self, manifest, *, run_id=None):
        manifest = _validate_manifest(manifest)
        run_id = str(uuid4()) if run_id is None else _uuid(run_id)
        path = self.run_path(run_id)
        self._private_dirs(self.root)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            raise RehearsalConflict("run already exists") from None
        for name in ("memory", "profiles", "library"):
            (path / name).mkdir(mode=0o700)
        db = path / "control.sqlite3"
        fd = os.open(db, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        connection = sqlite3.connect(db)
        try:
            connection.executescript(_SCHEMA)
            now = _now()
            connection.execute("INSERT INTO runs(run_id,manifest,status,created_at) VALUES(?,?,?,?)",
                               (run_id, _dump(manifest), "prepared", now))
            for round_number in range(1, manifest["limits"]["wakes_per_agent"] + 1):
                for owner in OWNERS:
                    connection.execute("INSERT INTO jobs(wake_id,agent_id,round,requested_model,updated_at) VALUES(?,?,?,?,?)",
                                       (f"{owner}-r{round_number}", owner, round_number, manifest["agent_models"][owner], now))
            connection.commit()
        except sqlite3.Error:
            raise RehearsalError("unable to prepare rehearsal") from None
        finally:
            connection.close()
        return self.get_run(run_id)

    @staticmethod
    def _run(connection):
        row = connection.execute("SELECT * FROM runs LIMIT 1").fetchone()
        if row is None:
            raise RehearsalError("run not found")
        return row

    @staticmethod
    def _job(connection, wake_id):
        _safe(wake_id, "wake_id")
        row = connection.execute("SELECT * FROM jobs WHERE wake_id=?", (wake_id,)).fetchone()
        if row is None:
            raise RehearsalError("job not found")
        return row

    @staticmethod
    def _token(row, token):
        _uuid(token, "controller token")
        if row["controller_token"] != token:
            raise RehearsalConflict("controller token is not current")

    @classmethod
    def _active(cls, row, token):
        cls._token(row, token)
        if row["stop_requested"] or row["status"] != "running":
            raise RehearsalStopped("rehearsal is stopped")
        if row["deadline"] is None or time.time() >= row["deadline"]:
            raise RehearsalStopped("rehearsal deadline exceeded")

    @staticmethod
    def _public_job(row):
        fields = ("wake_id", "agent_id", "round", "status", "action", "failure_code", "requested_model",
                  "response_model", "provider", "request_count", "duration_ms", "record_refs", "updated_at")
        result = {field: row[field] for field in fields}
        result["record_refs"] = json.loads(result["record_refs"])
        return result

    @classmethod
    def _summary(cls, connection):
        row = cls._run(connection)
        manifest = json.loads(row["manifest"])
        reserved = Decimal(0)
        known = Decimal(0)
        unknown = 0
        requests = connection.execute("SELECT reserved_usd,usage FROM requests").fetchall()
        for request in requests:
            reserved = decimal_add(reserved, Decimal(request["reserved_usd"]))
            cost = json.loads(request["usage"])["cost_usd"]
            if cost is None:
                unknown += 1
            else:
                known = decimal_add(known, Decimal(cost))
        agents = []
        for owner in OWNERS:
            counts = {"agent_id": owner, "pending": 0, "completed": 0, "failed": 0, "stopped": 0, "uncertain": 0}
            for job in connection.execute("SELECT status FROM jobs WHERE agent_id=?", (owner,)):
                counts["pending" if job["status"] == "running" else job["status"]] += 1
            agents.append(counts)
        return {"run_id": row["run_id"], "mode": manifest["mode"], "status": row["status"],
                "created_at": row["created_at"], "started_at": row["started_at"], "ended_at": row["ended_at"],
                "stop_requested": bool(row["stop_requested"]), "limits": manifest["limits"],
                "agent_models": manifest["agent_models"], "request_count": len(requests),
                "reserved_usd": decimal_text(reserved), "known_cost_usd": decimal_text(known) if len(requests) > unknown else None,
                "unknown_cost_requests": unknown, "agents": agents, "capabilities": manifest["capabilities"]}

    def get_run(self, run_id):
        with self._connection(run_id) as connection:
            return self._summary(connection)

    def get_manifest(self, run_id):
        with self._connection(run_id) as connection:
            return json.loads(self._run(connection)["manifest"])

    def list_runs(self, limit=20, offset=0):
        _integer(limit, "limit", 1, 100)
        _integer(offset, "offset", 0, 1_000_000)
        self._check_path(self.root)
        if not self.root.exists():
            return {"runs": [], "total": 0, "limit": limit, "offset": offset}
        if not self.root.is_dir():
            raise RehearsalError("invalid run root")
        summaries = []
        for path in self.root.iterdir():
            try:
                _uuid(path.name)
            except RehearsalError:
                continue
            self.run_path(path.name)
            if (path / "control.sqlite3").exists():
                summaries.append(self.get_run(path.name))
        summaries.sort(key=lambda run: (run["created_at"], run["run_id"]), reverse=True)
        return {"runs": summaries[offset:offset + limit], "total": len(summaries), "limit": limit, "offset": offset}

    def list_jobs(self, run_id):
        with self._connection(run_id) as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY round, rowid").fetchall()
            return [self._public_job(row) for row in rows]

    def begin(self, run_id, *, resume=False):
        if type(resume) is not bool:
            raise RehearsalError("invalid resume")
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["controller_token"] is not None:
                raise RehearsalConflict("rehearsal already has a controller; explicit recovery required")
            if row["status"] == "completed":
                raise RehearsalConflict("rehearsal already completed")
            if row["status"] != "prepared" and not resume:
                raise RehearsalConflict("explicit resume required")
            now = time.time()
            manifest = json.loads(row["manifest"])
            deadline = row["deadline"] if row["deadline"] is not None else now + manifest["limits"]["max_runtime_seconds"]
            if now >= deadline:
                raise RehearsalStopped("rehearsal deadline exceeded")
            token = str(uuid4())
            connection.execute("UPDATE runs SET status='running', controller_token=?,started_at=COALESCE(started_at,?),ended_at=NULL,stop_requested=0,deadline=?",
                               (token, _now(), deadline))
            if resume:
                missing, unresolved = self._recovery_guards()
                connection.execute("UPDATE jobs SET status='pending',failure_code=NULL,updated_at=? WHERE status IN ('stopped','uncertain') AND NOT " + unresolved + " AND NOT " + missing, (_now(),))
            return token

    def assert_active(self, run_id, token):
        with self._connection(run_id) as connection:
            self._active(self._run(connection), token)

    @staticmethod
    def _settled_status(connection, row):
        statuses = {job[0] for job in connection.execute("SELECT status FROM jobs")}
        if "uncertain" in statuses or connection.execute("SELECT 1 FROM requests WHERE outcome IN ('in_flight','uncertain') LIMIT 1").fetchone():
            return "uncertain"
        if statuses == {"completed"}:
            return "completed"
        if row["stop_requested"] or (row["deadline"] is not None and time.time() >= row["deadline"]):
            return "stopped"
        return "partial"

    def end(self, run_id, token):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            self._token(row, token)
            # Ending with an unfinished request cannot authorize a retry.
            self._recover_jobs(connection, stopped=self._is_stopped(row))
            status = self._settled_status(connection, row)
            connection.execute("UPDATE runs SET status=?,controller_token=NULL,ended_at=?", (status, _now()))
            return self._summary(connection)

    def request_stop(self, run_id):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["status"] != "completed":
                connection.execute("UPDATE runs SET stop_requested=1,status='stopped',ended_at=?", (_now(),))
                connection.execute("UPDATE jobs SET status='stopped',updated_at=? WHERE status='pending'", (_now(),))
            return self._summary(connection)

    def claim_job(self, run_id, wake_id, token):
        with self._connection(run_id, write=True) as connection:
            self._active(self._run(connection), token)
            job = self._job(connection, wake_id)
            if job["status"] != "pending":
                return None
            if connection.execute("SELECT 1 FROM requests WHERE wake_id=? AND outcome IN ('in_flight','uncertain') LIMIT 1", (wake_id,)).fetchone():
                raise RehearsalConflict("uncertain request must not be resent")
            connection.execute("UPDATE jobs SET status='running',updated_at=? WHERE wake_id=?", (_now(), wake_id))
            return self._public_job(self._job(connection, wake_id))

    def commit_choice(self, run_id, wake_id, token, choice):
        serialized = _choice(choice)
        with self._connection(run_id, write=True) as connection:
            # Persisting an already-returned response is not new dispatch.
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            if row["choice"] is not None:
                if row["choice"] == serialized:
                    return
                raise RehearsalConflict("choice is immutable")
            if row["status"] != "running":
                raise RehearsalConflict("job is not claimed")
            connection.execute("UPDATE jobs SET choice=?,action=?,updated_at=? WHERE wake_id=?", (serialized, choice["action"], _now(), wake_id))

    def get_choice(self, run_id, wake_id):
        with self._connection(run_id) as connection:
            value = self._job(connection, wake_id)["choice"]
            return None if value is None else json.loads(value)

    def commit_output(self, run_id, wake_id, token, content):
        if not isinstance(content, str):
            raise RehearsalError("invalid output")
        try:
            size = len(content.encode("utf-8"))
        except UnicodeError:
            raise RehearsalError("invalid output") from None
        if size > 65536:
            raise RehearsalError("output too large")
        with self._connection(run_id, write=True) as connection:
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            if row["output"] is not None:
                if row["output"] == content:
                    return
                raise RehearsalConflict("output is immutable")
            if row["status"] != "running" or row["choice"] is None:
                raise RehearsalConflict("output requires a claimed choice")
            connection.execute("UPDATE jobs SET output=?,updated_at=? WHERE wake_id=?", (content, _now(), wake_id))

    def get_output(self, run_id, wake_id):
        with self._connection(run_id) as connection:
            return self._job(connection, wake_id)["output"]

    def finish_job(self, run_id, wake_id, token, *, status="completed", action=None, failure_code=None, record_refs=None):
        if not isinstance(status, str) or status not in _TERMINAL:
            raise RehearsalError("invalid job status")
        if action is not None and action not in CAPABILITIES:
            raise RehearsalError("invalid action")
        failure_code = _safe(failure_code, "failure_code", nullable=True)
        refs = _refs(record_refs)
        with self._connection(run_id, write=True) as connection:
            self._token(self._run(connection), token)
            row = self._job(connection, wake_id)
            actual_action = row["action"] if action is None else action
            if row["choice"] is not None and actual_action != row["action"]:
                raise RehearsalConflict("action disagrees with committed choice")
            if row["status"] in _TERMINAL:
                if (row["status"], row["action"], row["failure_code"], row["record_refs"]) == (status, actual_action, failure_code, refs):
                    return
                raise RehearsalConflict("terminal job is immutable")
            if row["status"] != "running":
                raise RehearsalConflict("job is not claimed")
            if status == "completed" and connection.execute("SELECT 1 FROM requests WHERE wake_id=? AND outcome IN ('in_flight','uncertain') LIMIT 1", (wake_id,)).fetchone():
                raise RehearsalConflict("job has an unresolved request")
            connection.execute("UPDATE jobs SET status=?,action=?,failure_code=?,record_refs=?,updated_at=? WHERE wake_id=?",
                               (status, actual_action, failure_code, refs, _now(), wake_id))

    def reserve_request(self, run_id, wake_id, token, *, agent_id, activity, model, input_bytes, max_output_tokens, reserved_usd):
        if agent_id not in OWNERS:
            raise RehearsalError("invalid agent_id")
        if activity not in (*CAPABILITIES, "choice", "choose_action", "inquiry"):
            raise RehearsalError("invalid activity")
        model = _model(model)
        _integer(input_bytes, "input_bytes", 0, 24000)
        _integer(max_output_tokens, "max_output_tokens", 1, 1024)
        amount = _money(reserved_usd, "reserved_usd")
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            self._active(row, token)
            job = self._job(connection, wake_id)
            manifest = json.loads(row["manifest"])
            limits = manifest["limits"]
            if job["status"] != "running" or job["agent_id"] != agent_id or job["requested_model"] != model:
                raise RehearsalConflict("request does not match claimed job")
            if activity in ("choice", "choose_action") and job["choice"] is not None:
                raise RehearsalConflict("committed choice must not be regenerated")
            if activity not in ("choice", "choose_action") and job["output"] is not None:
                raise RehearsalConflict("committed output must not be regenerated")
            if input_bytes > limits["max_input_bytes"] or max_output_tokens > limits["max_output_tokens"]:
                raise RehearsalBudgetExceeded("request input or output limit exceeded")
            requests = connection.execute("SELECT reserved_usd,outcome,wake_id,activity FROM requests").fetchall()
            if any(request["wake_id"] == wake_id and request["outcome"] in ("uncertain", "in_flight") for request in requests):
                raise RehearsalConflict("unresolved request must not be resent")
            choice_request = activity in ("choice", "choose_action")
            if any(request["wake_id"] == wake_id and request["outcome"] == "success"
                   and (request["activity"] in ("choice", "choose_action")) == choice_request for request in requests):
                raise RehearsalConflict("successful request must not be resent")
            if len(requests) >= limits["max_requests"] or job["request_count"] >= 2:
                raise RehearsalBudgetExceeded("request attempt limit exceeded")
            if sum(request["outcome"] == "in_flight" for request in requests) >= limits["max_parallelism"]:
                raise RehearsalConflict("request parallelism limit exceeded")
            total = amount
            for request in requests:
                total = decimal_add(total, Decimal(request["reserved_usd"]))
            if total > _money(limits["budget_usd"], "budget_usd"):
                raise RehearsalBudgetExceeded("USD admission budget exceeded")
            request_id = str(uuid4())
            now = _now()
            connection.execute("INSERT INTO requests(request_id,wake_id,agent_id,activity,requested_model,input_bytes,max_output_tokens,reserved_usd,created_at,usage,controller_token) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (request_id, wake_id, agent_id, activity, model, input_bytes, max_output_tokens, decimal_text(amount), now, _dump(_usage(None)), token))
            connection.execute("UPDATE jobs SET request_count=request_count+1,updated_at=? WHERE wake_id=?", (now, wake_id))
            return request_id

    def mark_dispatched(self, run_id, request_id, token):
        """Atomically commit dispatch immediately before transport, never twice.

        Reservation alone does not authorize transport. Stop/deadline and this
        logical dispatch point serialize through the same write transaction.
        """
        _uuid(request_id, "request_id")
        with self._connection(run_id, write=True) as connection:
            self._active(self._run(connection), token)
            request = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if request is None:
                raise RehearsalError("request not found")
            job = self._job(connection, request["wake_id"])
            if (request["controller_token"] != token or job["status"] != "running"
                    or request["agent_id"] != job["agent_id"]
                    or request["requested_model"] != job["requested_model"]):
                raise RehearsalConflict("request does not match current claimed job")
            if request["dispatched"] or request["outcome"] != "in_flight" or request["finished_at"] is not None:
                raise RehearsalConflict("request is already dispatched or finished")
            connection.execute("UPDATE requests SET dispatched=1 WHERE request_id=?", (request_id,))

    def finish_request(self, run_id, request_id, *, outcome, response_model=None, provider=None, duration_ms=0, usage=None, failure_code=None):
        _uuid(request_id, "request_id")
        if not isinstance(outcome, str) or outcome not in _OUTCOMES:
            raise RehearsalError("invalid outcome")
        response_model = None if response_model is None else _model(response_model)
        provider = _safe(provider, "provider", nullable=True, label=True)
        failure_code = _safe(failure_code, "failure_code", nullable=True)
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)) or not math.isfinite(duration_ms) or not 0 <= duration_ms <= 86_400_000:
            raise RehearsalError("invalid duration_ms")
        serialized = _dump(_usage(usage))
        with self._connection(run_id, write=True) as connection:
            row = connection.execute("SELECT * FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise RehearsalError("request not found")
            values = (outcome, response_model, provider, duration_ms, serialized, failure_code)
            if outcome == "not_sent" and row["dispatched"]:
                raise RehearsalConflict("dispatched request cannot be not sent")
            previous = tuple(row[field] for field in ("outcome", "response_model", "provider", "duration_ms", "usage", "failure_code"))
            if row["outcome"] != "in_flight":
                if previous == values:
                    return
                raise RehearsalConflict("request result is immutable")
            now = _now()
            connection.execute("UPDATE requests SET outcome=?,response_model=?,provider=?,duration_ms=?,usage=?,failure_code=?,finished_at=? WHERE request_id=?", (*values, now, request_id))
            connection.execute("UPDATE jobs SET response_model=COALESCE(?,response_model),provider=COALESCE(?,provider),duration_ms=duration_ms+?,updated_at=? WHERE wake_id=?",
                               (response_model, provider, duration_ms, now, row["wake_id"]))

    def list_requests(self, run_id, limit=50, offset=0, agent_id=None):
        _integer(limit, "limit", 1, 100)
        _integer(offset, "offset", 0, 1_000_000)
        if agent_id is not None and agent_id not in OWNERS:
            raise RehearsalError("invalid agent_id")
        with self._connection(run_id) as connection:
            where = "" if agent_id is None else " WHERE agent_id=?"
            args = () if agent_id is None else (agent_id,)
            total = connection.execute("SELECT COUNT(*) FROM requests" + where, args).fetchone()[0]
            rows = connection.execute("SELECT * FROM requests" + where + " ORDER BY rowid LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
            events = []
            for row in rows:
                result = {field: row[field] for field in ("request_id", "wake_id", "agent_id", "activity", "requested_model", "input_bytes", "max_output_tokens", "reserved_usd", "created_at", "finished_at", "outcome", "response_model", "provider", "duration_ms", "failure_code")}
                result.update(json.loads(row["usage"]))
                events.append(result)
            return {"events": events, "total": total, "limit": limit, "offset": offset}

    @staticmethod
    def _is_stopped(row):
        return bool(row["stop_requested"] or (row["deadline"] is not None and time.time() >= row["deadline"]))

    @staticmethod
    def _recovery_guards():
        # Only returned successful work needs a durable private checkpoint.
        missing = "((choice IS NULL AND EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome='success' AND activity IN ('choice','choose_action'))) OR (output IS NULL AND EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome='success' AND activity NOT IN ('choice','choose_action'))))"
        unresolved = "EXISTS (SELECT 1 FROM requests WHERE requests.wake_id=jobs.wake_id AND outcome IN ('in_flight','uncertain'))"
        return missing, unresolved

    @classmethod
    def _recover_jobs(cls, connection, *, stopped=False):
        now = _now()
        connection.execute("UPDATE requests SET outcome='not_sent',finished_at=?,failure_code=? WHERE outcome='in_flight' AND dispatched=0",
                           (now, "admission_stopped" if stopped else "interrupted_before_dispatch"))
        connection.execute("UPDATE requests SET outcome='uncertain',finished_at=?,failure_code='interrupted' WHERE outcome='in_flight' AND dispatched=1", (now,))
        connection.execute("UPDATE jobs SET status='uncertain',failure_code='interrupted',updated_at=? WHERE status NOT IN ('completed','failed') AND wake_id IN (SELECT wake_id FROM requests WHERE outcome='uncertain')", (now,))
        # A successful response without its private checkpoint is also unsafe:
        # replaying it could cause another paid request. Preserve it as uncertain.
        missing, unresolved = cls._recovery_guards()
        connection.execute("UPDATE jobs SET status='uncertain',failure_code='missing_checkpoint',updated_at=? WHERE status IN ('running','stopped','uncertain') AND NOT " + unresolved + " AND " + missing, (now,))
        if stopped:
            connection.execute("UPDATE jobs SET status='stopped',updated_at=? WHERE status IN ('pending','running') AND NOT " + unresolved + " AND NOT " + missing, (now,))
        else:
            # Existing stopped progress is only unstopped by explicit resume.
            connection.execute("UPDATE jobs SET status='pending',failure_code=NULL,updated_at=? WHERE status IN ('running','uncertain') AND NOT " + unresolved + " AND NOT " + missing, (now,))

    def recover(self, run_id):
        with self._connection(run_id, write=True) as connection:
            row = self._run(connection)
            if row["status"] == "completed":
                return self._summary(connection)
            self._recover_jobs(connection, stopped=self._is_stopped(row))
            status = self._settled_status(connection, row)
            connection.execute("UPDATE runs SET controller_token=NULL,status=?,ended_at=?", (status, _now()))
            return self._summary(connection)
