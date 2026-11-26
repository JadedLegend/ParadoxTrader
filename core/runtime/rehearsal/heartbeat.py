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

**Owner settings.** When the owner has chosen models or a daily budget on the
Settings page, those win over the config file. A change applies from the next
wake: if today's open day run has different models, or the budget was raised,
the heartbeat closes that run and opens a new segment of the same day that
continues the home. Spending is always summed across all of today's segments.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

from .calls import CALLS_FILE, CallStore, settle_open_calls
from .home import CARRIED_STATUSES, continue_home, read_home
from .provider import ProviderError
from .store import MAX_WAKES_PER_AGENT, OWNERS, RehearsalConflict, RehearsalError

MAX_CHOICES_PER_WAKE = 6  # Moves in one wake; rest ends it early.
LEDGER = "heartbeat.sqlite3"
PAUSE = "heartbeat.paused"
LOCK = "heartbeat.lock"
MIN_REMAINING_USD = Decimal("0.01")
SETTLE_EVERY_MINUTES = 30  # One closing-price read at most this often, only while calls are due.
MARKET_CLOSED_AFTER = (16, 30)  # US Eastern: a session's close is final after this.
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
    settings_dir: str = None   # The owner's Settings page (models, budget, key) wins when set.
    choices_per_wake: int = 1  # Turns in one wake (1-6): choose, do it, then maybe choose again.

    @classmethod
    def from_config(cls, raw):
        allowed = {"timezone", "active_window", "active_interval_minutes", "quiet_window",
                   "quiet_interval_minutes", "grace_minutes", "daily_budget_usd", "mode",
                   "dispatch", "max_wakes_per_tick", "models_file", "settings_dir", "choices_per_wake"}
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
            choices = raw.get("choices_per_wake", 1)
            if type(choices) is not int:
                raise ValueError
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise RehearsalError("invalid_heartbeat_config") from None
        if (not 1 <= grace <= 60 or mode not in ("offline", "real") or not 1 <= choices <= MAX_CHOICES_PER_WAKE
                or dispatch not in ("clock-only", "live") or not 1 <= per_tick <= 7
                or not Decimal("0") <= budget <= Decimal("100")
                or (mode == "real" and not isinstance(models_file, str) and not isinstance(raw.get("settings_dir"), str))
                or (raw.get("settings_dir") is not None and not isinstance(raw.get("settings_dir"), str))):
            raise RehearsalError("invalid_heartbeat_config")
        schedule = cls(name, tuple(windows), grace, budget, mode, dispatch, per_tick, models_file,
                       raw.get("settings_dir"), choices)
        if schedule.rounds_per_agent() > MAX_WAKES_PER_AGENT:
            raise RehearsalError("invalid_heartbeat_config")
        return schedule

    def wakes_per_agent(self):
        return sum(len(range(start, end, step)) for start, end, step, _ in self.windows)

    def rounds_per_agent(self):
        """Stored turns a day can hold: every wake may use all its choices."""
        return self.wakes_per_agent() * self.choices_per_wake

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
    def __init__(self, store, schedule, *, prepare_day, run_wake, now=None, settings=None,
                 key_present=lambda: True, fetch_closes=None):
        """``prepare_day(budget_usd, wakes_per_agent, models) -> run_id`` creates
        a prepared day run (no profiles yet); ``models`` is None to use the
        config. ``run_wake(run_id, owner) -> job`` adds and runs one wake.
        ``now()`` returns an aware datetime. ``settings`` is an OwnerSettings.
        ``fetch_closes(symbols, start, end)`` reads daily closes for settling
        calls (core.market.closes); None leaves calls unsettled."""
        self.store = store
        self.schedule = schedule
        self.settings = settings
        self.key_present = key_present
        self.prepare_day = prepare_day
        self.run_wake = run_wake
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.fetch_closes = fetch_closes
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
            # Why today's day run could not open (for status and the heartbeat page).
            # Slots stay due, so a passing problem is retried until each grace ends.
            conn.execute("""CREATE TABLE IF NOT EXISTS day_errors (
                local_date TEXT NOT NULL, recorded_at TEXT NOT NULL, code TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS days (
                local_date TEXT NOT NULL, run_id TEXT PRIMARY KEY, opened_at TEXT NOT NULL,
                continued_from TEXT)""")
            # Each time the heartbeat read closing prices to settle calls. Counts and
            # short reasons only, never a call's reason text.
            conn.execute("""CREATE TABLE IF NOT EXISTS settle_checks (
                checked_at TEXT NOT NULL, settled INTEGER NOT NULL, still_open INTEGER NOT NULL,
                note TEXT)""")
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

    def daily_budget(self):
        chosen = self.settings.daily_budget() if self.settings is not None else None
        return self.schedule.daily_budget_usd if chosen is None else chosen

    def chosen_models(self):
        return self.settings.agent_models() if self.settings is not None else None

    def _today_runs(self, conn, today):
        return [self.store.get_run(row["run_id"]) for row in conn.execute(
            "SELECT run_id FROM days WHERE local_date=? ORDER BY opened_at", (today,)).fetchall()]

    def _reserved_today(self, conn, today):
        """What today's segments count against the budget: reported charges, plus
        full set-asides for anything not yet confirmed (see counted_usd)."""
        return sum((Decimal(run["counted_usd"]) for run in self._today_runs(conn, today)), Decimal(0))

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
        """Today's open day run, opening (and continuing the home) if needed.

        A run whose models differ from the owner's current choice, or whose
        budget is below what the owner now allows, is closed and a new segment
        of the day opens, so the change applies from this wake.
        """
        models = self.chosen_models()
        segments = self._today_runs(conn, today)
        spent_before = Decimal(0)
        for run in segments:
            if run["status"] in ("prepared", "open"):
                allowed = self.daily_budget() - spent_before
                stale = ((models is not None and run["agent_models"] != models)
                         or Decimal(run["limits"]["budget_usd"]) < allowed
                         or run["limits"]["wakes_per_agent"] < self.schedule.rounds_per_agent())
                if not stale:
                    return run["run_id"], None
                try:
                    self.store.close_day(run["run_id"])
                except RehearsalConflict:
                    return run["run_id"], None  # A wake is running; switch on a later tick.
            spent_before += Decimal(run["counted_usd"])
        runs = self._runs()
        previous = self._previous(runs)
        budget = max(Decimal(0), self.daily_budget() - spent_before)
        run_id = self.prepare_day(format(budget, "f"), self.schedule.rounds_per_agent(), models)
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
            try:
                result = self._decide()
            finally:
                settled = self._settle_calls()  # After the wakes, so it never delays one.
            if settled:
                result["calls"] = settled
            return result

    def _decide(self):
        """The wakes due this moment (tick's body, under the lock)."""
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
            if self.daily_budget() - self._reserved_today(conn, today) < MIN_REMAINING_USD:
                for slot in fresh:  # Spent before opening anything: no new day segment.
                    self._record(conn, slot, "over_budget", note="today's budget is spent")
                return {"outcome": "over_budget", "slots": len(fresh), "missed": missed}
            try:
                run_id, previous = self._today(conn, today)
            except Exception as error:
                # Bounded codes only (manifest codes are fixed strings), never a body or a path.
                text = str(error)
                code = text if re.fullmatch(r"[a-z_]{3,60}", text) else type(error).__name__
                conn.execute("INSERT INTO day_errors(local_date,recorded_at,code) VALUES (?,?,?)",
                             (today, self.now().isoformat(), code))
                conn.commit()
                raise
            conn.execute("DELETE FROM day_errors WHERE local_date=?", (today,))
            conn.commit()
            started = []
            for slot in fresh[:self.schedule.max_wakes_per_tick]:
                _, owner, _ = slot
                if self.paused():
                    break  # A stop or pause arrived; leave the rest unrecorded.
                run = self.store.get_run(run_id)
                if run["status"] not in ("prepared", "open"):
                    self._record(conn, slot, "day_stopped", run_id=run_id, note=f"day is {run['status']}")
                    continue
                remaining = self.daily_budget() - self._reserved_today(conn, today)
                if remaining < MIN_REMAINING_USD:
                    self._record(conn, slot, "over_budget", run_id=run_id,
                                 note=f"{remaining} USD left of today's budget")
                    continue
                try:
                    job = self._wake(conn, today, run_id, slot)
                except RehearsalConflict as error:
                    self._record(conn, slot, "blocked", run_id=run_id, note=str(error))
                    continue
                except RehearsalError as error:
                    self._record(conn, slot, "not_started", run_id=run_id, note=str(error))
                    continue
                started.append({"agent_id": owner, "wake_id": job["wake_id"], "status": job["status"]})
        return {"outcome": "woke" if started else "nothing_started", "run_id": run_id,
                "continued_from": previous, "wakes": started, "missed": missed}

    @staticmethod
    def _slot_note(owner, job, actions):
        if job.get("status") not in (None, "completed"):
            # Name the agent and model so a model that stops answering is easy to find.
            return (f"{owner} on {job.get('requested_model') or 'unknown model'}: "
                    f"{job.get('failure_code') or job.get('status')}")
        return ("choices: " + ", ".join(actions)) if len(actions) > 1 else None

    def _wake(self, conn, today, run_id, slot):
        """One wake: up to ``choices_per_wake`` turns, each a choice and its doing.

        Each turn is its own stored step (same reservation, recovery and witness
        rules), and later turns see earlier ones through today's continuity.
        The slot is recorded as woken as soon as the first turn returns, and
        updated after every later turn, so a restart mid-wake finds the slot
        done and never reruns finished turns or exceeds the wake's choices.
        The wake ends early when the agent rests, a turn does not complete, a
        pause arrives, or the budget runs low. Returns the last turn's job.
        """
        _, owner, _ = slot
        total = self.schedule.choices_per_wake
        job = self.run_wake(run_id, owner, step=(1, total)) if total > 1 else self.run_wake(run_id, owner)
        actions = [job.get("action") or job.get("status") or "unknown"]
        self._record(conn, slot, "woke", run_id=run_id, wake_id=job["wake_id"],
                     note=self._slot_note(owner, job, actions))
        self._progress(conn, slot, job, actions)
        for step in range(2, total + 1):
            if (job.get("status") != "completed" or job.get("action") in (None, "rest") or self.paused()
                    or self.daily_budget() - self._reserved_today(conn, today) < MIN_REMAINING_USD):
                break
            try:
                job = self.run_wake(run_id, owner, step=(step, total))
            except (RehearsalConflict, RehearsalError, ProviderError):
                # Refused before this turn started (for example the key was cleared
                # mid-wake): the wake ends here and the earlier turns stand.
                break
            actions.append(job.get("action") or job.get("status") or "unknown")
            self._progress(conn, slot, job, actions)
        return job

    def _progress(self, conn, slot, job, actions):
        conn.execute("UPDATE wake_slots SET wake_id=?,wake_status=?,note=?,finished_at=? WHERE slot_key=?",
                     (job["wake_id"], job["status"], self._slot_note(slot[1], job, actions),
                      self.now().isoformat(), self._key(slot)))
        conn.commit()

    # ---- settling calls (code only: no model request, no cost) ------------
    def _day_run_file(self, name):
        """A carried file of the newest day run (the home's current copy), or None."""
        for run in self._runs():
            if self.store.get_run(run["run_id"]).get("kind") != "day":
                continue
            path = self.store.safe_run_file(run["run_id"], name)
            return path if path.exists() else None
        return None

    def _calls_store(self):
        """The calls of the newest day run: the home's current copy. None when none."""
        path = self._day_run_file(CALLS_FILE)
        return CallStore(path) if path is not None else None

    def _settle_calls(self):
        """Settle every open call whose horizon has passed. Never raises.

        Reads closing prices at most every SETTLE_EVERY_MINUTES, and only while
        some call is open, so a quiet home makes no market-data request. A
        problem becomes a short note on the heartbeat page, never a failed tick."""
        if self.fetch_closes is None:
            return None
        try:
            calls = self._calls_store()
            if calls is None or not calls.has_open():
                return None
            now = self.now()
            with self._ledger() as conn:
                last = conn.execute("SELECT checked_at FROM settle_checks ORDER BY checked_at DESC LIMIT 1").fetchone()
            if last is not None and now - datetime.fromisoformat(last[0]) < timedelta(minutes=SETTLE_EVERY_MINUTES):
                return None
            eastern = now.astimezone(ZoneInfo("America/New_York"))
            today = eastern.date().isoformat()
            closed_today = (eastern.hour, eastern.minute) >= MARKET_CLOSED_AFTER

            def completed(session):
                return session < today or (session == today and closed_today)

            summary = settle_open_calls(calls, self.fetch_closes, now=now, today=today, completed=completed)
        except Exception as error:  # A type name only, never a path or a response body.
            summary = {"settled": 0, "open": None, "pending": [], "error": type(error).__name__}
        parts = []
        if summary.get("unavailable"):
            parts.append("market data unavailable: " + summary["unavailable"])
        if summary.get("error"):
            parts.append("settling calls failed (" + summary["error"] + ")")
        parts.extend(summary.get("pending") or [])
        try:
            with self._ledger() as conn:
                conn.execute("INSERT INTO settle_checks(checked_at,settled,still_open,note) VALUES (?,?,?,?)",
                             (self.now().isoformat(), summary.get("settled") or 0, summary.get("open") or 0,
                              "; ".join(parts)[:500] or None))
        except Exception:
            pass
        return summary

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
            reserved = self._reserved_today(conn, today)
            day_error = conn.execute("SELECT recorded_at,code FROM day_errors WHERE local_date=? "
                                     "ORDER BY recorded_at DESC LIMIT 1", (today,)).fetchone()
            settle_note = conn.execute("SELECT checked_at,note FROM settle_checks ORDER BY checked_at DESC "
                                       "LIMIT 1").fetchone()
        run = self.store.get_run(day["run_id"]) if day else None
        upcoming = [slot for slot in self.schedule.slots(local.date()) if slot[0] > local]
        next_wakes = {}
        for moment, owner, _ in upcoming:
            next_wakes.setdefault(owner, moment.isoformat())
        if self.paused():
            reason = "paused"
        elif self.schedule.dispatch == "clock-only":
            reason = "clock-only mode: wake times are recorded, nothing is dispatched"
        elif self.schedule.mode == "real" and not self.key_present():
            reason = "the OpenRouter key is not set"
        elif run is not None and run["status"] not in ("prepared", "open"):
            reason = f"today's day is {run['status']}"
        elif self.daily_budget() - reserved < MIN_REMAINING_USD:
            reason = "today's budget is spent"
        elif day_error is not None:
            reason = "today's day could not open: " + day_error["code"]
        elif not upcoming:
            reason = "quiet: no more wakes today"
        else:
            reason = "running: next wake " + min(next_wakes.values())
        counts = {}
        for row in rows:
            counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
        problems = [{"agent_id": row["agent_id"], "scheduled_at": row["scheduled_at"], "note": row["note"]}
                    for row in rows if row["wake_status"] in ("failed", "uncertain")]
        if day_error is not None:
            problems.insert(0, {"agent_id": None, "scheduled_at": day_error["recorded_at"],
                                "note": "today's day could not open: " + day_error["code"]})
        if settle_note is not None and settle_note["note"]:
            problems.append({"agent_id": None, "scheduled_at": settle_note["checked_at"],
                             "note": "calls not settled yet: " + settle_note["note"]})
        return {"reason": reason, "paused": self.paused(), "dispatch": self.schedule.dispatch,
                "mode": self.schedule.mode, "local_time": local.isoformat(),
                "today": {"run_id": run["run_id"] if run else None,
                          "status": run["status"] if run else None,
                          "counted_usd": format(reserved, "f"),
                          "daily_budget_usd": format(self.daily_budget(), "f"),
                          "slot_outcomes": counts},
                "next_wake_by_agent": next_wakes, "problems": problems}
