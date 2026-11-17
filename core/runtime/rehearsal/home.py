"""One continuing home: a newly prepared run can continue from an earlier one.

Today every run is a separate visit, and its memory ends with it. A run that
continues from a finished earlier run in the same root starts with a copy of
each owner's private memory (journals, episodes, compost) and of the witness's
accounts, so notes and the witness carry from one day into the next.

The earlier run is only read, never changed. The link is a write-once
``home.json``, recorded before any copying so an interrupted step can be
retried. Each copy is made with SQLite's online backup into a temporary file
that is integrity-checked and then renamed into place, so a crash never leaves
a half-written database. Nothing here makes a model call.

Inquiries (trade_queue.sqlite3) are not carried yet.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .store import OWNERS, RehearsalConflict, RehearsalError, _uuid

HOME_FILE = "home.json"
SCHEMA_VERSION = 1
CARRIED_STATUSES = ("completed", "partial", "stopped")
CARRIED_FILES = (*(f"memory/{owner}.sqlite3" for owner in OWNERS), "witness.sqlite3")
MAX_LOOKBACK = 3
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _validate(value):
    if (not isinstance(value, dict) or set(value) != {"schema_version", "previous_run_id"}
            or value["schema_version"] != SCHEMA_VERSION):
        raise RehearsalError("invalid_home_link")
    _uuid(value["previous_run_id"], "previous_run_id")
    return value


def read_home(store, run_id):
    """Return this run's home link, or None when it is a first visit."""
    path = store.safe_run_file(run_id, HOME_FILE)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        raise RehearsalError("invalid_home_link") from None
    if len(raw) > 4096:
        raise RehearsalError("invalid_home_link")
    try:
        return _validate(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeError):
        raise RehearsalError("invalid_home_link") from None


def previous_run_ids(store, run_id, limit=MAX_LOOKBACK):
    """Earlier runs in this home, most recent first, bounded and cycle-safe."""
    result, seen, current = [], {run_id}, run_id
    while len(result) < limit:
        home = read_home(store, current)
        if home is None:
            break
        previous = home["previous_run_id"]
        if previous in seen:
            raise RehearsalError("invalid_home_link")
        seen.add(previous)
        result.append(previous)
        current = previous
    return result


def _write_link(store, run_id, previous_run_id):
    path = store.safe_run_file(run_id, HOME_FILE)
    raw = (json.dumps({"schema_version": SCHEMA_VERSION, "previous_run_id": previous_run_id},
                      sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    except FileExistsError:
        existing = read_home(store, run_id)
        if existing["previous_run_id"] != previous_run_id:
            raise RehearsalConflict("home_link_conflict") from None
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
    return True


def _carry(store, previous_run_id, run_id, relative):
    """Copy one database if the earlier run has it and this run does not yet."""
    source = store.safe_run_file(previous_run_id, relative)
    target = store.safe_run_file(run_id, relative)
    if not source.is_file() or target.exists():
        return False
    temporary = target.with_name(f".{target.name}.carry-{uuid4().hex}")
    store._check_path(temporary)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30)) as reader, \
                closing(sqlite3.connect(str(temporary))) as writer:
            reader.backup(writer)
        with closing(sqlite3.connect(temporary.as_uri() + "?mode=ro", uri=True)) as check:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RehearsalError("home_carry_integrity_failed")
        try:
            os.link(temporary, target)  # Never replaces a file that appeared meanwhile.
        except FileExistsError:
            return False
        except OSError:
            if target.exists():
                return False
            os.replace(temporary, target)
            return True
        return True
    except sqlite3.Error:
        raise RehearsalError("home_carry_unavailable") from None
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def continue_home(store, run_id, previous_run_id):
    """Link a freshly prepared run to an earlier finished run and carry memory.

    Safe to retry with the same previous run. Refuses a different previous run,
    an earlier run that has not finished, a different mode, or a run that has
    already started.
    """
    run_id, previous_run_id = _uuid(run_id), _uuid(previous_run_id, "previous_run_id")
    if run_id == previous_run_id:
        raise RehearsalError("home_cannot_continue_itself")
    current, previous = store.get_run(run_id), store.get_run(previous_run_id)
    if current["status"] != "prepared" or current.get("started_at"):
        raise RehearsalError("home_run_already_started")
    if previous["status"] not in CARRIED_STATUSES:
        raise RehearsalError("home_previous_run_not_finished")
    if store.get_manifest(run_id)["mode"] != store.get_manifest(previous_run_id)["mode"]:
        raise RehearsalError("home_mode_mismatch")
    if run_id in previous_run_ids(store, previous_run_id, limit=1000):
        raise RehearsalError("invalid_home_link")
    _write_link(store, run_id, previous_run_id)
    carried = [relative for relative in CARRIED_FILES if _carry(store, previous_run_id, run_id, relative)]
    present = [relative for relative in CARRIED_FILES if store.safe_run_file(run_id, relative).exists()]
    return {"run_id": run_id, "previous_run_id": previous_run_id,
            "carried_now": carried, "present": present}
