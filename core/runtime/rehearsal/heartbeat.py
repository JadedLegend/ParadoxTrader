"""The heartbeat: each agent wakes on its own staggered clock through the day.

Every agent has its own wake times, offset from the others so that posts,
replies and market moves meet different agents at different moments. A wake
is an opportunity, not a demand: the agent can still rest.

A day is one "day run" (store kind ``day``). The heartbeat opens it at the
first wake of the local day, continues the home from the previous day, adds
each wake as it falls due (``store.add_wake``), and closes the day once the
local date moves on.

Its limits are enforced here and in the store, never in a prompt:

- **Wake times only.** Slots come from the saved schedule and today's date,
  each with a stable key, so a restart recomputes the same slots. Nights are
  quiet unless a window is configured there.
- **No catch-up storm.** A slot past its grace window is recorded as missed
  and never run later. At most ``max_wakes_per_tick`` wakes start per tick.
- **Daily budget.** The day run's budget is the daily budget. The store
  reserves the most each request could cost before sending it and refuses any
  request that would pass the budget. When the day is spent, slots are
  recorded as over budget without creating wakes.
- **Clock-only mode** computes and records slots but dispatches nothing.
- **Pause and stop.** A pause marker stops new wakes. ``stop`` also stops any
  prepared, open or running day, and a tick re-checks the marker before each
  wake, so a stop is never lost.
- **One wake at a time per agent.** An agent whose previous wake is
  unfinished or uncertain is recorded as blocked for that slot; others go on.
- **One tick at a time.** An exclusive lock; an overlapping tick reports busy.

Every decision goes to ``heartbeat.sqlite3`` (one row per agent slot), and
``status`` always says why nothing is happening.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

from .home import CARRIED_STATUSES, continue_home, read_home
from .store import MAX_WAKES_PER_AGENT, OWNERS, RehearsalConflict, RehearsalError

LEDGER = "heartbeat.sqlite3"
PAUSE = "heartbeat.paused"
LOCK = "heartbeat.lock"
MIN_REMAINING_USD = Decimal("0.01")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _clock(value):
    hour, minute = value.split(":")
    if len(hour) != 2 or len(minute) != 2 or not 0 <= int(hour) < 24 or not 0 <= int(minute) < 60:
        raise ValueError
    return int(hour) * 60 + int(minute)


@dataclass(frozen=True)
class Schedule:
    timezone: str
    windows: tuple            # ((start_min, end_min, interval_min, name), ...)
    grace_minutes: int
    daily_budget_usd: Decimal
    mode: str
    dispatch: str             # "clock-only" or "live"
    max_wakes_per_tick: int
    models_file: str = None

    @classmethod
    def from_config(cls, raw):
        allowed = {"timezone", "active_window", "active_interval_minutes", "quiet_window",
                   "quiet_interval_minutes", "grace_minutes", "daily_budget_usd", "mode",
                   "dispatch", "max_wakes_per_tick", "models_file"}
        if not isinstance(raw, dict) or set(raw) - allowed:
            raise RehearsalError("invalid_heartbeat_config")
        try:
            name = raw.get("timezone", "UTC")
            try:
                ZoneInfo(name)
            except Exception:
                raise ValueError from None
            windows = []
            for window, interval, label in (("active_window", "active_interval_minutes", "active"),
                                            ("quiet_window", "quiet_interval_minutes", "quiet")):
                if raw.get(window) is None:
                    continue
                start, end = map(_clock, raw[window])
                step = int(raw[interval])
                if not start < end or not 5 <= step <= 240:
                    raise ValueError
                windows.append((start, end, step, label))
            windows.sort()
            if not windows or any(a[1] > b[0] for a, b in zip(windows, windows[1:])):
                raise ValueError
            grace = int(raw.get("grace_minutes", 10))
            budget = Decimal(str(raw["daily_budget_usd"]))
            mode = raw.get("mode", "offline")
            dispatch = raw.get("dispatch", "clock-only")
            per_tick = int(raw.get("max_wakes_per_tick", 3))
            models_file = raw.get("models_file")
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise RehearsalError("invalid_heartbeat_config") from None
        if (not 1 <= grace <= 60 or mode not in ("offline", "real")
                or dispatch not in ("clock-only", "live") or not 1 <= per_tick <= 7
                or not Decimal("0") <= budget <= Decimal("100")
                or (mode == "real") != isinstance(models_file, str)):
            raise RehearsalError("invalid_heartbeat_config")
        schedule = cls(name, tuple(windows), grace, budget, mode, dispatch, per_tick, models_file)
        if schedule.wakes_per_agent() > MAX_WAKES_PER_AGENT:
            raise RehearsalError("invalid_heartbeat_config")
        return schedule

    def wakes_per_agent(self):
        return sum(len(range(start, end, step)) for start, end, step, _ in self.windows)

    def slots(self, local_date):
        """Every agent's wake times on ``local_date``, as (aware local time, agent, window).

        Agent i is offset by i/7 of each window's interval, so no two agents
        share a minute when the interval allows it.
        """
        zone = ZoneInfo(self.timezone)
        midnight = datetime(local_date.year, local_date.month, local_date.day)
        result = []
        for start, end, step, label in self.windows:
            for index, owner in enumerate(OWNERS):
                offset = (index * step) // len(OWNERS)
                for minute in range(start + offset, end, step):
                    naive = midnight + timedelta(minutes=minute)
                    moment = naive.replace(tzinfo=zone).astimezone(timezone.utc).astimezone(zone)
                    if moment.replace(tzinfo=None) != naive:
                        continue  # This local time does not exist (spring forward): no wake.
                    result.append((moment, owner, label))
        result.sort(key=lambda item: (item[0], OWNERS.index(item[1])))
        return result


def _secure_create(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
    except FileExistsError:
        return
    os.close(fd)


def load_schedule(path):
    raw = Path(path).read_bytes()
    if len(raw) > 65536:
        raise RehearsalError("invalid_heartbeat_config")
    try:
        return Schedule.from_config(json.loads(raw.decode("utf-8")))
    except (ValueError, UnicodeError):
        raise RehearsalError("invalid_heartbeat_config") from None


class Heartbeat:
    def __init__(self, store, schedule, *, prepare_day, run_wake, now=None):
        """``prepare_day(budget_usd, wakes_per_agent) -> run_id`` creates a
        prepared day run (no profiles yet). ``run_wake(run_id, owner) -> job``
        adds and runs one wake. ``now()`` returns an aware datetime."""
        self.store = store
        self.schedule = schedule
        self.prepare_day = prepare_day
        self.run_wake = run_wake
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.root = store.root

    # ---- files, ledger, lock --------------------------------------------
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
            conn.execute("""CREATE TABLE IF NOT EXISTS wake_slots (
                slot_key TEXT PRIMARY KEY, local_date TEXT NOT NULL, agent_id TEXT NOT NULL,
                scheduled_at TEXT NOT NULL, window TEXT NOT NULL, outcome TEXT NOT NULL,
                run_id TEXT, wake_id TEXT, wake_status TEXT, note TEXT,
                recorded_at TEXT NOT NULL, finished_at TEXT)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS days (
                local_date TEXT NOT NULL, run_id TEXT PRIMARY KEY, opened_at TEXT NOT NULL,
                continued_from TEXT)""")
            yield conn
            conn.commit()

    def _record(self, conn, slot, outcome, **fields):
        moment, owner, window = slot
        conn.execute("INSERT INTO wake_slots(slot_key,local_date,agent_id,scheduled_at,window,outcome,"
                     "run_id,wake_id,note,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (self._key(slot), moment.date().isoformat(), owner, moment.isoformat(), window,
                      outcome, fields.get("run_id"), fields.get("wake_id"), fields.get("note"),
                      self.now().isoformat()))
        conn.commit()

    @staticmethod
    def _key(slot):
        moment, owner, _ = slot
        return f"{moment.isoformat()}|{owner}"

    @contextmanager
    def _exclusive(self):
        try:
            import fcntl
        except ImportError:  # Windows development machines: single user, no timer.
            yield True
            return
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self._path(LOCK)
        _secure_create(path)
        with open(path, "r+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
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
        """Pause, and stop any prepared, open or running day.

        The pause marker is written before runs are listed. A tick re-checks it
        before every wake, so whichever happens first, no new wake starts.
        """
        self.pause()
        stopped = [run["run_id"] for run in self._runs() if run["status"] in ("prepared", "open", "running")]
        for run_id in stopped:
            self.store.request_stop(run_id)
        return {"paused": True, "stop_requested": stopped}

    # ---- days -------------------------------------------------------------
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

    def _close_earlier_days(self, conn, today):
        closed = []
        for row in conn.execute("SELECT run_id FROM days WHERE local_date < ?", (today,)).fetchall():
            run = self.store.get_run(row["run_id"])
            if run["status"] in ("open", "prepared"):
                try:
                    self.store.close_day(row["run_id"])
                    closed.append(row["run_id"])
                except RehearsalConflict:
                    pass  # A wake is still running; close on a later tick.
        return closed

    def _today(self, conn, today):
        """Today's open day run, opening (and continuing the home) if needed."""
        for row in conn.execute("SELECT run_id FROM days WHERE local_date=? ORDER BY opened_at DESC", (today,)):
            if self.store.get_run(row["run_id"])["status"] in ("prepared", "open"):
                return row["run_id"], None
        runs = self._runs()
        previous = self._previous(runs)
        run_id = self.prepare_day(format(self.schedule.daily_budget_usd, "f"),
                                  self.schedule.wakes_per_agent())
        if previous is not None:
            continue_home(self.store, run_id, previous)
        conn.execute("INSERT INTO days(local_date,run_id,opened_at,continued_from) VALUES (?,?,?,?)",
                     (today, run_id, self.now().isoformat(), previous))
        conn.commit()
        return run_id, previous

    # ---- decisions --------------------------------------------------------
    def _local_now(self):
        return self.now().astimezone(ZoneInfo(self.schedule.timezone))

    def _due(self, conn, local):
        """Slots at or before now that are not yet recorded, oldest first."""
        done = {row[0] for row in conn.execute("SELECT slot_key FROM wake_slots WHERE local_date=?",
                                               (local.date().isoformat(),))}
        return [slot for slot in self.schedule.slots(local.date())
                if slot[0] <= local and self._key(slot) not in done]

    def tick(self):
        """Decide this moment once; never raises for a normal outcome."""
        if self.paused():
            return {"outcome": "paused"}
        with self._exclusive() as acquired:
            if not acquired:
                return {"outcome": "busy"}
            local = self._local_now()
            today = local.date().isoformat()
            grace = timedelta(minutes=self.schedule.grace_minutes)
            with self._ledger() as conn:
                self._close_earlier_days(conn, today)
                fresh = []
                missed = 0
                for slot in self._due(conn, local):
                    if local - slot[0] > grace:
                        self._record(conn, slot, "missed", note="grace window passed; never caught up")
                        missed += 1
                    else:
                        fresh.append(slot)
                if not fresh:
                    return {"outcome": "quiet", "missed": missed}
                if self.schedule.dispatch == "clock-only":
                    for slot in fresh:
                        self._record(conn, slot, "clock_only", note="clock-only mode: recorded, not dispatched")
                    return {"outcome": "clock_only", "slots": len(fresh), "missed": missed}
                run_id, previous = self._today(conn, today)
                started = []
                for slot in fresh[:self.schedule.max_wakes_per_tick]:
                    _, owner, _ = slot
                    if self.paused():
                        break  # A stop or pause arrived; leave the rest unrecorded.
                    run = self.store.get_run(run_id)
                    if run["status"] not in ("prepared", "open"):
                        self._record(conn, slot, "day_stopped", run_id=run_id, note=f"day is {run['status']}")
                        continue
                    remaining = self.schedule.daily_budget_usd - Decimal(run["reserved_usd"])
                    if remaining < MIN_REMAINING_USD:
                        self._record(conn, slot, "over_budget", run_id=run_id,
                                     note=f"{remaining} USD left of today's budget")
                        continue
                    try:
                        job = self.run_wake(run_id, owner)
                    except RehearsalConflict as error:
                        self._record(conn, slot, "blocked", run_id=run_id, note=str(error))
                        continue
                    except RehearsalError as error:
                        self._record(conn, slot, "not_started", run_id=run_id, note=str(error))
                        continue
                    self._record(conn, slot, "woke", run_id=run_id, wake_id=job["wake_id"])
                    conn.execute("UPDATE wake_slots SET wake_status=?,finished_at=? WHERE slot_key=?",
                                 (job["status"], self.now().isoformat(), self._key(slot)))
                    conn.commit()
                    started.append({"agent_id": owner, "wake_id": job["wake_id"], "status": job["status"]})
            return {"outcome": "woke" if started else "nothing_started", "run_id": run_id,
                    "continued_from": previous, "wakes": started, "missed": missed}

    # ---- status -----------------------------------------------------------
    def status(self):
        """What the heartbeat is doing, and in plain terms why nothing is."""
        local = self._local_now()
        today = local.date().isoformat()
        with self._ledger() as conn:
            rows = [dict(row) for row in conn.execute(
                "SELECT agent_id,scheduled_at,outcome,wake_id,wake_status,note FROM wake_slots "
                "WHERE local_date=? ORDER BY scheduled_at", (today,))]
            day = conn.execute("SELECT run_id FROM days WHERE local_date=? ORDER BY opened_at DESC LIMIT 1",
                               (today,)).fetchone()
        run = self.store.get_run(day["run_id"]) if day else None
        upcoming = [slot for slot in self.schedule.slots(local.date()) if slot[0] > local]
        next_wakes = {}
        for moment, owner, _ in upcoming:
            next_wakes.setdefault(owner, moment.isoformat())
        if self.paused():
            reason = "paused"
        elif self.schedule.dispatch == "clock-only":
            reason = "clock-only mode: wake times are recorded, nothing is dispatched"
        elif run is not None and run["status"] not in ("prepared", "open"):
            reason = f"today's day is {run['status']}"
        elif run is not None and self.schedule.daily_budget_usd - Decimal(run["reserved_usd"]) < MIN_REMAINING_USD:
            reason = "today's budget is spent"
        elif not upcoming:
            reason = "quiet: no more wakes today"
        else:
            reason = "running: next wake " + min(next_wakes.values())
        counts = {}
        for row in rows:
            counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
        return {"reason": reason, "paused": self.paused(), "dispatch": self.schedule.dispatch,
                "mode": self.schedule.mode, "local_time": local.isoformat(),
                "today": {"run_id": run["run_id"] if run else None,
                          "status": run["status"] if run else None,
                          "reserved_usd": run["reserved_usd"] if run else "0",
                          "daily_budget_usd": format(self.schedule.daily_budget_usd, "f"),
                          "slot_outcomes": counts},
                "next_wake_by_agent": next_wakes}
