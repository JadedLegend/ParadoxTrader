"""The heartbeat: each agent on its own staggered clock, with hard limits.

Actual temporary private stores, scripted offline HTTP, a scripted clock and a
structurally blocked network.
"""
from datetime import date, datetime, timezone
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.home import read_home
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalError, RehearsalStore
from tests.test_day_runs import day_manifest

ROOT = Path(__file__).resolve().parents[1]
# 14-minute interval: agent i is offset by 2*i minutes (tempest 9:00, siren 9:02, ...).
CONFIG = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
          "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}


def at(hour, minute, day=18, month=11):
    return datetime(2026, month, day, hour, minute, tzinfo=timezone.utc)


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RehearsalStore(Path(self.temp.name) / "sessions")
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.clock = at(8, 0)
        self.woken = []

    def prepare_day(self, budget_usd, wakes_per_agent, models=None):
        raw = day_manifest(wakes=wakes_per_agent, budget=budget_usd)
        if models:
            from core.runtime.rehearsal.examples import synthetic_catalog
            from core.runtime.rehearsal.provider import catalog_snapshot
            raw["agent_models"] = dict(models)
            raw["catalog_snapshot"] = catalog_snapshot(models, synthetic_catalog(models))
        return self.store.prepare(raw)["run_id"]

    def run_wake(self, run_id, owner):
        self.woken.append(owner)
        return RehearsalController(self.store, run_id, transport=OpenRouterTransport(
            "scripted-offline", http_post=ScriptedHTTP())).run_wake(owner)

    def heartbeat(self, **overrides):
        return Heartbeat(self.store, Schedule.from_config({**CONFIG, **overrides}),
                         prepare_day=self.prepare_day, run_wake=self.run_wake, now=lambda: self.clock)

    def slots(self):
        with sqlite3.connect(self.store.root / "heartbeat.sqlite3") as conn:
            return [tuple(row) for row in conn.execute(
                "SELECT agent_id,substr(scheduled_at,12,5),outcome FROM wake_slots ORDER BY scheduled_at, agent_id")]

    def test_each_agent_has_its_own_staggered_times(self):
        schedule = Schedule.from_config(CONFIG)
        first = {}
        for moment, owner, _ in schedule.slots(date(2026, 11, 18)):
            first.setdefault(owner, moment.strftime("%H:%M"))
        self.assertEqual(first, {"tempest": "09:00", "siren": "09:02", "alchemist": "09:04", "weaver": "09:06",
                                 "oracle": "09:08", "shadow": "09:10", "paradox_hunter": "09:12"})
        self.assertEqual(len(set(first.values())), 7)  # Never all seven at once.
        self.assertTrue(all(m.hour == 9 for m, _, _ in schedule.slots(date(2026, 11, 18))))  # Quiet night.

    def test_quiet_outside_the_windows(self):
        self.assertEqual(self.heartbeat().tick(), {"outcome": "quiet", "missed": 0})
        self.assertEqual(self.store.list_runs()["total"], 0)

    def test_wakes_arrive_one_agent_at_a_time_in_one_continuing_day(self):
        beat = self.heartbeat()
        self.clock = at(9, 1)
        first = beat.tick()
        self.assertEqual([w["agent_id"] for w in first["wakes"]], ["tempest"])
        self.assertIsNone(first["continued_from"])
        self.clock = at(9, 3)
        second = beat.tick()
        self.assertEqual([w["agent_id"] for w in second["wakes"]], ["siren"])
        self.assertEqual(second["run_id"], first["run_id"])  # Same day, same run.
        self.assertEqual(self.store.get_run(first["run_id"])["status"], "open")
        self.assertEqual(self.store.get_run(first["run_id"])["kind"], "day")

    def test_at_most_three_per_tick_and_late_slots_are_missed_not_caught_up(self):
        beat = self.heartbeat()
        self.clock = at(9, 1)
        beat.tick()  # tempest 09:00
        self.clock = at(9, 15)  # The machine paused for a while.
        result = beat.tick()
        # siren 09:02 and alchemist 09:04 are more than 10 minutes late: missed.
        self.assertEqual(result["missed"], 2)
        self.assertEqual([w["agent_id"] for w in result["wakes"]], ["weaver", "oracle", "shadow"])
        self.clock = at(9, 16)
        # paradox_hunter 09:12, then tempest 09:14 and siren 09:16 (her second wake).
        self.assertEqual([w["agent_id"] for w in beat.tick()["wakes"]], ["paradox_hunter", "tempest", "siren"])
        outcomes = {(agent, time): outcome for agent, time, outcome in self.slots()}
        self.assertEqual(outcomes[("siren", "09:02")], "missed")
        self.assertEqual(outcomes[("tempest", "09:14")], "woke")
        tempest = [job for job in self.store.list_jobs(result["run_id"]) if job["agent_id"] == "tempest"]
        self.assertEqual([job["wake_id"] for job in tempest], ["tempest-r1", "tempest-r2"])

    def test_clock_only_records_times_and_dispatches_nothing(self):
        beat = self.heartbeat(dispatch="clock-only")
        self.clock = at(9, 5)
        self.assertEqual(beat.tick(), {"outcome": "clock_only", "slots": 3, "missed": 0})
        self.assertEqual(self.store.list_runs()["total"], 0)
        self.assertEqual(self.woken, [])
        self.assertEqual([outcome for _, _, outcome in self.slots()], ["clock_only"] * 3)
        self.assertTrue(beat.status()["reason"].startswith("clock-only"))

    def test_a_new_day_continues_the_home_and_closes_yesterday(self):
        beat = self.heartbeat()
        self.clock = at(9, 1)
        yesterday = beat.tick()["run_id"]
        self.clock = at(9, 1, day=19)
        today = beat.tick()
        self.assertNotEqual(today["run_id"], yesterday)
        self.assertEqual(today["continued_from"], yesterday)
        self.assertEqual(read_home(self.store, today["run_id"])["previous_run_id"], yesterday)
        self.assertEqual(self.store.get_run(yesterday)["status"], "completed")

    def test_pause_resume_and_stop(self):
        beat = self.heartbeat()
        self.clock = at(9, 1)
        beat.pause()
        self.assertEqual(beat.tick(), {"outcome": "paused"})
        self.assertEqual(beat.status()["reason"], "paused")
        beat.resume()
        day = beat.tick()["run_id"]
        result = beat.stop()
        self.assertEqual(result["stop_requested"], [day])
        self.assertEqual(self.store.get_run(day)["status"], "stopped")
        beat.resume()
        self.clock = at(9, 3)
        after = beat.tick()  # A stopped day accepts no wakes; a new day continues the home.
        self.assertNotEqual(after["run_id"], day)
        self.assertEqual(after["continued_from"], day)

    def test_a_stop_between_wakes_in_one_tick_is_never_lost(self):
        beat = None
        original = self.run_wake

        def wake_then_stop(run_id, owner):
            job = original(run_id, owner)
            beat.stop()
            return job
        self.run_wake = wake_then_stop
        beat = self.heartbeat()
        self.clock = at(9, 9)  # tempest, siren, alchemist, weaver, oracle all due.
        result = beat.tick()
        self.assertEqual([w["agent_id"] for w in result["wakes"]], ["tempest"])
        self.assertEqual(self.woken, ["tempest"])
        self.assertTrue(beat.paused())

    def test_over_budget_creates_no_wakes(self):
        beat = self.heartbeat(daily_budget_usd="0")
        self.clock = at(9, 1)
        result = beat.tick()
        self.assertEqual(result, {"outcome": "over_budget", "slots": 1, "missed": 0})
        self.assertEqual(self.slots(), [("tempest", "09:00", "over_budget")])
        self.assertEqual(self.store.list_runs()["total"], 0)  # Nothing opened once the day is spent.
        self.assertEqual(beat.status()["reason"], "today's budget is spent")

    def test_an_unfinished_wake_blocks_only_that_agent(self):
        beat = self.heartbeat()
        self.clock = at(9, 1)
        day = beat.tick()["run_id"]
        self.store.add_wake(day, "siren")  # Left unfinished, as after a crash.
        self.clock = at(9, 5)
        result = beat.tick()
        self.assertEqual([w["agent_id"] for w in result["wakes"]], ["alchemist"])
        self.assertIn(("siren", "09:02", "blocked"), self.slots())

    def test_a_failed_wake_names_the_agent_and_model(self):
        def failing(run_id, owner):
            job = self.store.add_wake(run_id, owner)
            return {**job, "status": "failed", "failure_code": "http_rejected", "requested_model": "flaky/model"}
        beat = Heartbeat(self.store, Schedule.from_config(CONFIG), prepare_day=self.prepare_day,
                         run_wake=failing, now=lambda: self.clock)
        self.clock = at(9, 1)
        beat.tick()
        problems = beat.status()["problems"]
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["agent_id"], "tempest")
        self.assertEqual(problems[0]["note"], "tempest on flaky/model: http_rejected")

    def test_two_choices_per_wake_run_back_to_back_and_stop_at_rest(self):
        http, prompts, steps = ScriptedHTTP(), [], []

        def recording(url, **kwargs):
            prompts.append(chr(10).join(str(m.get("content", "")) for m in kwargs["json"]["messages"]))
            return http(url, **kwargs)

        def run_wake(run_id, owner, step=None):
            steps.append((owner, step))
            return RehearsalController(self.store, run_id, transport=OpenRouterTransport(
                "scripted-offline", http_post=recording)).run_wake(owner, step=step)

        beat = Heartbeat(self.store, Schedule.from_config({**CONFIG, "choices_per_wake": 2}),
                         prepare_day=self.prepare_day, run_wake=run_wake, now=lambda: self.clock)
        self.clock = at(9, 3)  # Tempest (rests) at 9:00, Siren (journals, then rests) at 9:02.
        result = beat.tick()
        self.assertEqual(steps, [("tempest", (1, 2)), ("siren", (1, 2)), ("siren", (2, 2))])
        jobs = {(j["agent_id"], j["round"]): j for j in self.store.list_jobs(result["run_id"])}
        self.assertEqual((jobs[("siren", 1)]["action"], jobs[("siren", 2)]["action"]), ("journal", "rest"))
        self.assertNotIn(("tempest", 2), jobs)  # Rest ends the wake.
        self.assertEqual(self.store.get_run(result["run_id"])["limits"]["wakes_per_agent"],
                         2 * Schedule.from_config(CONFIG).wakes_per_agent())
        choices = [p for p in prompts if "choice 2 of 2" in p]
        self.assertEqual(len(choices), 1)
        self.assertIn("Stable owner ID: siren", choices[0])
        notes = dict(((owner, when), note) for owner, when, note in sqlite3.connect(
            self.store.root / "heartbeat.sqlite3").execute(
            "SELECT agent_id,substr(scheduled_at,12,5),note FROM wake_slots WHERE outcome='woke'"))
        self.assertEqual(notes[("siren", "09:02")], "choices: journal, rest")
        self.assertIsNone(notes[("tempest", "09:00")])

    def test_a_failed_first_choice_ends_the_wake(self):
        calls = []

        def failing(run_id, owner, step=None):
            calls.append(step)
            job = self.store.add_wake(run_id, owner)
            return {**job, "status": "failed", "action": "journal", "failure_code": "http_rejected"}

        beat = Heartbeat(self.store, Schedule.from_config({**CONFIG, "choices_per_wake": 2}),
                         prepare_day=self.prepare_day, run_wake=failing, now=lambda: self.clock)
        self.clock = at(9, 1)
        beat.tick()
        self.assertEqual(calls, [(1, 2)])

    def test_a_restart_mid_wake_never_reruns_or_adds_turns(self):
        calls = []

        def crashing(run_id, owner, step=None):
            calls.append((owner, step))
            if step == (2, 2):
                raise KeyboardInterrupt  # The service dies before the second turn returns.
            job = self.store.add_wake(run_id, owner)
            return {**job, "status": "completed", "action": "journal"}

        def beat():
            return Heartbeat(self.store, Schedule.from_config({**CONFIG, "choices_per_wake": 2}),
                             prepare_day=self.prepare_day, run_wake=crashing, now=lambda: self.clock)

        self.clock = at(9, 0)
        with self.assertRaises(KeyboardInterrupt):
            beat().tick()
        self.assertEqual(calls, [("tempest", (1, 2)), ("tempest", (2, 2))])
        self.assertIn(("tempest", "09:00", "woke"), self.slots())  # Saved after the first turn.
        self.clock = at(9, 1)
        beat().tick()  # Restart: the slot is done, so no turn runs again.
        self.assertEqual([c for c in calls if c[0] == "tempest"], [("tempest", (1, 2)), ("tempest", (2, 2))])

    def test_a_key_cleared_mid_wake_ends_the_wake_and_keeps_the_first_turn(self):
        from core.runtime.rehearsal.provider import ProviderError

        def keyless_second(run_id, owner, step=None):
            if step == (2, 2):
                raise ProviderError("explicit_api_key_required")
            job = self.store.add_wake(run_id, owner)
            return {**job, "status": "completed", "action": "journal"}

        beat = Heartbeat(self.store, Schedule.from_config({**CONFIG, "choices_per_wake": 2}),
                         prepare_day=self.prepare_day, run_wake=keyless_second, now=lambda: self.clock)
        self.clock = at(9, 3)
        result = beat.tick()
        self.assertEqual([w["agent_id"] for w in result["wakes"]], ["tempest", "siren"])  # The tick went on.
        self.assertIn(("tempest", "09:00", "woke"), self.slots())

    def test_choices_per_wake_is_bounded(self):
        for value in (0, 4, "2", True):
            with self.subTest(value=value), self.assertRaises(RehearsalError):
                Schedule.from_config({**CONFIG, "choices_per_wake": value})
        too_many = {**CONFIG, "active_window": ["00:00", "20:00"], "active_interval_minutes": 60}
        Schedule.from_config({**too_many, "choices_per_wake": 2})  # 20 wakes x 2 = 40 turns: allowed.
        with self.assertRaises(RehearsalError):
            Schedule.from_config({**too_many, "choices_per_wake": 3})  # 60 turns: over the daily cap.

    def test_daylight_saving_days_keep_every_wake_distinct_and_in_order(self):
        schedule = Schedule.from_config({**CONFIG, "timezone": "America/New_York",
                                         "active_window": ["00:30", "04:00"], "active_interval_minutes": 30})
        for day in (date(2026, 3, 8), date(2026, 11, 1)):  # Spring forward, fall back.
            with self.subTest(day=day):
                slots = schedule.slots(day)
                instants = [moment.astimezone(timezone.utc) for moment, _, _ in slots]
                self.assertEqual(instants, sorted(instants))
                keys = {(moment.isoformat(), owner) for moment, owner, _ in slots}
                self.assertEqual(len(keys), len(slots))
                self.assertEqual(len(set(instants)), len(instants))
        spring = [m.strftime("%H:%M") for m, owner, _ in schedule.slots(date(2026, 3, 8)) if owner == "tempest"]
        self.assertEqual(spring, ["00:30", "01:00", "01:30", "03:00", "03:30"])  # 02:00 and 02:30 never exist.

    def test_overlapping_ticks_report_busy(self):
        import fcntl
        beat = self.heartbeat()
        self.clock = at(9, 1)
        beat.status()  # Creates the root.
        lock = self.store.root / "heartbeat.lock"
        lock.touch()
        with open(lock, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(beat.tick(), {"outcome": "busy"})

    def test_configuration_is_validated(self):
        for bad in ({"active_window": ["9:00", "10:00"]}, {"active_window": ["10:00", "09:00"]},
                    {"active_interval_minutes": 1}, {"mode": "real"}, {"timezone": "Not/AZone"},
                    {"surprise": 1}, {"dispatch": "fast"}, {"daily_budget_usd": "-1"},
                    {"active_window": ["00:00", "23:59"], "active_interval_minutes": 5},
                    {"quiet_window": ["09:30", "11:00"], "quiet_interval_minutes": 60}):
            with self.subTest(bad=bad), self.assertRaises(RehearsalError):
                Schedule.from_config({**CONFIG, **bad})
        schedule = Schedule.from_config({**CONFIG, "quiet_window": ["10:00", "12:00"], "quiet_interval_minutes": 60})
        self.assertEqual(schedule.wakes_per_agent(), 5 + 2)

    def test_cli_controls_never_need_the_key(self):
        spec = importlib.util.spec_from_file_location("heartbeat_cli", ROOT / "scripts" / "heartbeat.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        config = Path(self.temp.name) / "heartbeat.json"
        root = ["--root", str(self.store.root), "--config", str(config)]
        config.write_text(json.dumps({**CONFIG, "mode": "real", "models_file": "/nope.json"}))
        with patch.dict("os.environ", {"REHEARSAL_OPENROUTER_API_KEY": ""}):
            for command in ("status", "pause", "resume", "stop", "resume"):
                self.assertEqual(cli.main(root + [command]), 0)
            with self.assertRaises(ValueError):
                cli.main(root + ["tick"])  # Live real wakes need the key.
            config.write_text(json.dumps({**CONFIG, "mode": "real", "models_file": "/nope.json",
                                          "dispatch": "clock-only"}))
            self.assertEqual(cli.main(root + ["tick"]), 0)  # Keeping time needs no key.

    def settings_beat(self):
        from core.runtime.owner_settings import OwnerSettings
        settings = OwnerSettings(Path(self.temp.name) / "settings")
        beat = Heartbeat(self.store, Schedule.from_config(CONFIG), prepare_day=self.prepare_day,
                         run_wake=self.run_wake, now=lambda: self.clock, settings=settings)
        return beat, settings

    def test_settings_choose_the_models_and_a_change_applies_from_the_next_wake(self):
        beat, settings = self.settings_beat()
        chosen = {owner: f"example/{owner}-first" for owner in
                  ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter")}
        settings.update({"models": chosen})
        self.clock = at(9, 1)
        first = beat.tick()
        self.assertEqual(self.store.get_run(first["run_id"])["agent_models"], chosen)
        settings.update({"models": {"siren": "example/siren-second"}})
        self.clock = at(9, 3)
        second = beat.tick()  # Siren's next wake uses her new model.
        self.assertNotEqual(second["run_id"], first["run_id"])
        self.assertEqual(second["continued_from"], first["run_id"])  # Same day, new segment, same home.
        self.assertEqual(self.store.get_run(second["run_id"])["agent_models"]["siren"], "example/siren-second")
        siren = self.store.list_jobs(second["run_id"])[0]
        self.assertEqual((siren["agent_id"], siren["requested_model"]), ("siren", "example/siren-second"))
        self.assertNotIn(self.store.get_run(first["run_id"])["status"], ("open", "prepared"))

    def test_budget_changes_apply_from_the_next_wake(self):
        beat, settings = self.settings_beat()
        settings.update({"daily_budget_usd": "2.00"})
        self.clock = at(9, 1)
        first = beat.tick()
        self.assertEqual(self.store.get_run(first["run_id"])["limits"]["budget_usd"], "2")
        settings.update({"daily_budget_usd": "3.00"})  # Raised: a new segment gets the extra room.
        self.clock = at(9, 3)
        raised = beat.tick()
        self.assertNotEqual(raised["run_id"], first["run_id"])
        self.assertEqual(beat.status()["today"]["daily_budget_usd"], "3.00")
        settings.update({"daily_budget_usd": "0.00"})  # Lowered: no more wakes today.
        self.clock = at(9, 5)
        self.assertEqual(beat.tick()["outcome"], "over_budget")
        self.assertEqual(beat.status()["reason"], "today's budget is spent")

    def test_status_says_when_the_key_is_missing(self):
        beat = Heartbeat(self.store, Schedule.from_config({**CONFIG, "mode": "real", "models_file": "/x.json"}),
                         prepare_day=self.prepare_day, run_wake=self.run_wake, now=lambda: self.clock,
                         key_present=lambda: False)
        self.assertEqual(beat.status()["reason"], "the OpenRouter key is not set")

    def test_timer_ticks_every_minute_and_never_catches_up(self):
        timer = (ROOT / "deploy/systemd/paradoxtrader-heartbeat.timer").read_text()
        self.assertIn("OnCalendar=*:*:00", timer)
        self.assertIn("Persistent=false", timer)
        self.assertNotIn("paradoxtrader-heartbeat", (ROOT / "deploy/install_host.sh").read_text())
        self.assertIn("User=paradoxtrader", (ROOT / "deploy/systemd/paradoxtrader-heartbeat.service").read_text())


if __name__ == "__main__":
    unittest.main()
