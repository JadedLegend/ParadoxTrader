"""The heartbeat: offers the agents a gathering at a few chosen times each day.

Each scheduled slot can start one gathering: a run that continues the home
from the previous finished run. The heartbeat is an availability mechanism,
not a demand to work; agents can still rest through every wake.

Its limits are enforced here, in code, never in a prompt:

- **Schedule.** Gatherings start only at the configured slot times, within a
  short grace window. Nights are quiet unless a slot is configured there.
- **No catch-up storm.** A slot whose grace window has passed is recorded as
  missed and never run later. One tick starts at most one gathering.
- **Daily budget.** Today's reserved spend (the conservative upper bound the
  store reserves before every model call) is summed across today's runs. A new
  gathering gets the smaller of the per-gathering budget and what is left of
  the day. When too little is left, the slot is recorded as over budget.
- **Pause.** A pause marker stops every new gathering until it is removed.
  ``stop`` also stops any prepared or running gathering. A stopped run can
  never be started afterwards, and a tick re-checks the pause marker after
  preparing its run, so a stop arriving during preparation is never lost.
- **Manual recovery.** If the latest run is unfinished or uncertain, the
  heartbeat records the slot as blocked and waits for the operator.
- **One at a time.** An exclusive lock prevents overlapping ticks.

Every decision is written to a small ledger (``heartbeat.sqlite3`` beside the
runs), one row per slot, which later feeds the witness's daily account.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from .home import CARRIED_STATUSES, continue_home, read_home
from .store import RehearsalError

LEDGER = "heartbeat.sqlite3"
PAUSE = "heartbeat.paused"
LOCK = "heartbeat.lock"
UNFINISHED = ("prepared", "running", "uncertain")
MIN_GATHERING_USD = Decimal("0.01")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


@dataclass(frozen=True)
class Schedule:
    timezone: str
    slots: tuple          # "HH:MM" local times, sorted
    grace_minutes: int
    daily_budget_usd: Decimal
    gathering_budget_usd: Decimal
    mode: str
    models_file: str = None  # Required for real mode: the owner-chosen model per agent.

    @classmethod
    def from_config(cls, raw):
        allowed = {"timezone", "slots", "grace_minutes", "daily_budget_usd",
                   "gathering_budget_usd", "mode", "models_file"}
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise RehearsalError("invalid_heartbeat_config")
        try:
            try:
                ZoneInfo(raw.get("timezone", "UTC"))
            except Exception:
                raise ValueError from None
            slots = tuple(sorted(raw["slots"]))
            for slot in slots:
                hour, minute = slot.split(":")
                if len(hour) != 2 or len(minute) != 2 or not 0 <= int(hour) < 24 or not 0 <= int(minute) < 60:
                    raise ValueError
            if not 1 <= len(slots) <= 48 or len(set(slots)) != len(slots):
                raise ValueError
            grace = int(raw.get("grace_minutes", 20))
            daily = Decimal(str(raw["daily_budget_usd"]))
            gathering = Decimal(str(raw["gathering_budget_usd"]))
            mode = raw.get("mode", "offline")
            models_file = raw.get("models_file")
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise RehearsalError("invalid_heartbeat_config") from None
        if (not 1 <= grace <= 120 or mode not in ("offline", "real")
                or not Decimal("0") < gathering <= daily <= Decimal("100")
                or (mode == "real") != isinstance(models_file, str)):
            raise RehearsalError("invalid_heartbeat_config")
        return cls(raw.get("timezone", "UTC"), slots, grace, daily, gathering, mode, models_file)


def _secure_create(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    except FileExistsError:
        return
    os.close(fd)


class Heartbeat:
    def __init__(self, store, schedule, *, prepare_run, run_gathering, now=None):
        """``prepare_run(budget_usd) -> run_id`` creates a prepared run (no
        profiles yet); ``run_gathering(run_id) -> summary`` prepares profiles
        and runs it. ``now()`` returns an aware datetime (tests inject it)."""
        self.store = store
        self.schedule = schedule
        self.prepare_run = prepare_run
        self.run_gathering = run_gathering
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.root = store.root

    # ---- ledger -----------------------------------------------------------
    def _path(self, name):
        path = self.root / name
        self.store._check_path(path)
        return path

    @contextmanager
    def _ledger(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(LEDGER)
        _secure_create(path)
        with closing(sqlite3.connect(path, timeout=30)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("""CREATE TABLE IF NOT EXISTS slots (
                slot_key TEXT PRIMARY KEY, local_date TEXT NOT NULL, slot TEXT NOT NULL,
                outcome TEXT NOT NULL, run_id TEXT, budget_usd TEXT, run_status TEXT,
                note TEXT, recorded_at TEXT NOT NULL, finished_at TEXT)""")
            yield conn
            conn.commit()

    def _record(self, conn, key, date, slot, outcome, **fields):
        conn.execute("INSERT INTO slots(slot_key,local_date,slot,outcome,run_id,budget_usd,note,recorded_at) "
                     "VALUES (?,?,?,?,?,?,?,?)",
                     (key, date, slot, outcome, fields.get("run_id"), fields.get("budget_usd"),
                      fields.get("note"), self.now().isoformat()))
        conn.commit()

    @contextmanager
    def _exclusive(self):
        try:
            import fcntl
        except ImportError:  # Windows development machines: single user, no timer.
            yield
            return
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(LOCK)
        _secure_create(path)
        with open(path, "r+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RehearsalError("heartbeat_already_running") from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # ---- controls ---------------------------------------------------------
    def paused(self):
        return self._path(PAUSE).exists()

    def pause(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        _secure_create(self._path(PAUSE))
        return {"paused": True}

    def resume(self):
        try:
            self._path(PAUSE).unlink()
        except FileNotFoundError:
            pass
        return {"paused": False}

    def stop(self):
        """Pause, and stop any prepared or running gathering.

        The pause marker is written before runs are listed. A tick re-checks it
        after creating its run, so whichever happens first, the run is stopped.
        """
        self.pause()
        stopped = [run["run_id"] for run in self._runs() if run["status"] in ("prepared", "running")]
        for run_id in stopped:
            self.store.request_stop(run_id)
        return {"paused": True, "stop_requested": stopped}

    # ---- decisions --------------------------------------------------------
    def _runs(self):
        """Every run in this root, newest first (paged, never truncated)."""
        runs, offset = [], 0
        while True:
            page = self.store.list_runs(limit=100, offset=offset)
            runs.extend(page["runs"])
            offset += 100
            if offset >= page["total"]:
                return runs

    def _previous(self, runs):
        """The newest finished run that belongs to the home: one that started,
        or one that was linked (and so carried the home) before it was stopped."""
        for run in runs:
            if run["status"] in CARRIED_STATUSES and (
                    run.get("started_at") or read_home(self.store, run["run_id"]) is not None):
                return run["run_id"]
        return None

    def _local(self, moment):
        return moment.astimezone(ZoneInfo(self.schedule.timezone))

    def _spent_today(self, today):
        spent = Decimal(0)
        for run in self._runs():
            created = datetime.fromisoformat(run["created_at"])
            if self._local(created).date().isoformat() == today:
                spent += Decimal(run["reserved_usd"])
        return spent

    def status(self):
        local = self._local(self.now())
        today = local.date().isoformat()
        with self._ledger() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT slot,outcome,run_id,budget_usd,run_status,note FROM slots WHERE local_date=? ORDER BY slot",
                (today,))]
        spent = self._spent_today(today)
        return {"paused": self.paused(), "local_time": local.isoformat(), "today": rows,
                "slots": list(self.schedule.slots), "mode": self.schedule.mode,
                "reserved_today_usd": str(spent),
                "daily_budget_usd": str(self.schedule.daily_budget_usd)}

    def tick(self):
        """Decide this moment once. Returns what happened; never raises for a
        normal outcome (quiet, paused, missed, blocked, over budget)."""
        if self.paused():
            return {"outcome": "paused"}
        with self._exclusive():
            local = self._local(self.now())
            today = local.date().isoformat()
            grace = timedelta(minutes=self.schedule.grace_minutes)
            with self._ledger() as conn:
                done = {row["slot"] for row in conn.execute("SELECT slot FROM slots WHERE local_date=?", (today,))}
                due = None
                for slot in self.schedule.slots:
                    hour, minute = map(int, slot.split(":"))
                    start = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if start > local or slot in done:
                        continue
                    key = f"{today}T{slot}"
                    if local - start > grace:
                        self._record(conn, key, today, slot, "missed",
                                     note="grace window passed; missed slots are never caught up")
                        continue
                    due = (key, slot)
                if due is None:
                    return {"outcome": "quiet"}
                key, slot = due
                runs = self._runs()
                unfinished = [run["run_id"] for run in runs if run["status"] in UNFINISHED]
                if unfinished:
                    self._record(conn, key, today, slot, "blocked",
                                 note="an earlier run is unfinished or uncertain; operator recovery needed")
                    return {"outcome": "blocked", "slot": slot, "runs": unfinished}
                remaining = self.schedule.daily_budget_usd - self._spent_today(today)
                budget = min(self.schedule.gathering_budget_usd, remaining)
                if budget < MIN_GATHERING_USD:
                    self._record(conn, key, today, slot, "over_budget",
                                 note=f"{remaining} USD left of today's budget")
                    return {"outcome": "over_budget", "slot": slot}
                previous = self._previous(runs)
                # Round down: a gathering is never allowed more than either limit.
                budget = budget.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                if budget < MIN_GATHERING_USD:
                    self._record(conn, key, today, slot, "over_budget",
                                 note=f"{remaining} USD left of today's budget")
                    return {"outcome": "over_budget", "slot": slot}
                budget_text = format(budget, "f")
                run_id = self.prepare_run(budget_text)
                if previous is not None:
                    try:
                        continue_home(self.store, run_id, previous)
                    except RehearsalError as error:
                        if self.store.get_run(run_id)["status"] == "stopped":
                            # A stop arrived before the home was carried; this
                            # unlinked, never-started run is not part of the home.
                            self._record(conn, key, today, slot, "stopped", run_id=run_id,
                                         budget_usd=budget_text, note="stopped before it began")
                            return {"outcome": "stopped", "slot": slot, "run_id": run_id}
                        # The prepared run stays as it is, so later slots are
                        # blocked until the operator looks: fail closed.
                        self._record(conn, key, today, slot, "failed", run_id=run_id,
                                     budget_usd=budget_text, note=f"home continuation refused: {error}")
                        return {"outcome": "failed", "slot": slot, "run_id": run_id}
                self._record(conn, key, today, slot, "started", run_id=run_id, budget_usd=budget_text)
                if self.paused():
                    # A stop or pause arrived while this run was being prepared.
                    self.store.request_stop(run_id)
            summary = None
            try:
                if self.store.get_run(run_id)["status"] == "stopped":
                    summary = self.store.get_run(run_id)
                else:
                    summary = self.run_gathering(run_id)
            except RehearsalError:
                if self.store.get_run(run_id)["status"] != "stopped":
                    raise
                summary = self.store.get_run(run_id)  # Stopped before it could begin.
            finally:
                status = summary["status"] if summary else self.store.get_run(run_id)["status"]
                with self._ledger() as conn:
                    conn.execute("UPDATE slots SET run_status=?,finished_at=? WHERE slot_key=?",
                                 (status, self.now().isoformat(), key))
            return {"outcome": "stopped" if status == "stopped" and not summary.get("started_at") else "started",
                    "slot": slot, "run_id": run_id,
                    "continued_from": previous, "budget_usd": budget_text, "run_status": status}


def load_schedule(path):
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise RehearsalError("invalid_heartbeat_config")
    try:
        return Schedule.from_config(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeError):
        raise RehearsalError("invalid_heartbeat_config") from None
