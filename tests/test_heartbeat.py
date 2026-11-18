"""The heartbeat: scheduled gatherings, hard limits, no catch-up, pause and stop.

Actual temporary private stores, scripted offline HTTP, structurally blocked network.
"""
from datetime import datetime, timezone
from decimal import Decimal
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
from tests.test_rehearsal_provider import manifest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"timezone": "UTC", "slots": ["09:30", "13:00"], "grace_minutes": 20,
          "daily_budget_usd": "3.00", "gathering_budget_usd": "1.00", "mode": "offline"}


def at(hour, minute, day=18):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


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
        self.budgets = []

    def prepare_run(self, budget_usd):
        self.budgets.append(budget_usd)
        raw = manifest()
        raw["limits"]["budget_usd"] = budget_usd
        return self.store.prepare(raw)["run_id"]

    def run_gathering(self, run_id):
        return RehearsalController(self.store, run_id, transport=OpenRouterTransport(
            "scripted-offline", http_post=ScriptedHTTP())).run()

    def heartbeat(self, **overrides):
        schedule = Schedule.from_config({**CONFIG, **overrides})
        return Heartbeat(self.store, schedule, prepare_run=self.prepare_run,
                         run_gathering=self.run_gathering, now=lambda: self.clock)

    def ledger(self):
        with sqlite3.connect(self.store.root / "heartbeat.sqlite3") as conn:
            return [tuple(row) for row in conn.execute("SELECT slot,outcome,run_status FROM slots ORDER BY slot_key")]

    def test_quiet_before_the_first_slot(self):
        self.assertEqual(self.heartbeat().tick(), {"outcome": "quiet"})
        self.assertEqual(self.store.list_runs()["total"], 0)

    def test_each_slot_starts_one_gathering_that_continues_the_home(self):
        beat = self.heartbeat()
        self.clock = at(9, 31)
        first = beat.tick()
        self.assertEqual(first["outcome"], "started")
        self.assertIsNone(first["continued_from"])
        self.assertEqual(first["run_status"], "completed")
        self.assertEqual(beat.tick(), {"outcome": "quiet"})  # Same slot never runs twice.

        self.clock = at(13, 5)
        second = beat.tick()
        self.assertEqual(second["continued_from"], first["run_id"])
        self.assertEqual(read_home(self.store, second["run_id"])["previous_run_id"], first["run_id"])
        self.assertEqual(self.ledger(), [("09:30", "started", "completed"), ("13:00", "started", "completed")])

    def test_missed_slots_are_recorded_and_never_caught_up(self):
        beat = self.heartbeat()
        self.clock = at(15, 0)  # The machine was down through both slots.
        self.assertEqual(beat.tick(), {"outcome": "quiet"})
        self.assertEqual(self.ledger(), [("09:30", "missed", None), ("13:00", "missed", None)])
        self.assertEqual(self.store.list_runs()["total"], 0)
        self.clock = at(9, 35, day=19)  # Next day starts fresh, at its own slot only.
        self.assertEqual(beat.tick()["outcome"], "started")
        self.assertEqual(self.store.list_runs()["total"], 1)

    def test_pause_resume_and_stop(self):
        beat = self.heartbeat()
        self.clock = at(9, 31)
        beat.pause()
        self.assertEqual(beat.tick(), {"outcome": "paused"})
        self.assertEqual(self.store.list_runs()["total"], 0)
        beat.resume()
        self.assertEqual(beat.tick()["outcome"], "started")

        running = self.prepare_run("1.00")
        self.store.begin(running)
        result = beat.stop()
        self.assertTrue(result["paused"])
        self.assertEqual(result["stop_requested"], [running])
        self.assertEqual(self.store.get_run(running)["status"], "stopped")
        self.assertTrue(beat.status()["paused"])

    def test_an_unfinished_run_blocks_until_the_operator_recovers_it(self):
        beat = self.heartbeat()
        leftover = self.prepare_run("1.00")
        self.clock = at(9, 31)
        result = beat.tick()
        self.assertEqual(result["outcome"], "blocked")
        self.assertEqual(result["runs"], [leftover])
        self.assertEqual(self.store.list_runs()["total"], 1)
        self.assertEqual(self.ledger(), [("09:30", "blocked", None)])

    def test_daily_budget_is_enforced_in_code(self):
        beat = self.heartbeat(daily_budget_usd="1.50", gathering_budget_usd="1.00")
        self.clock = at(9, 31)
        with patch.object(Heartbeat, "_spent_today", return_value=Decimal("0.75")):
            self.assertEqual(beat.tick()["budget_usd"], "0.75")  # Never more than the day has left.
        self.clock = at(13, 1)
        with patch.object(Heartbeat, "_spent_today", return_value=Decimal("1.495")):
            self.assertEqual(beat.tick()["outcome"], "over_budget")
        self.assertEqual(self.budgets, ["0.75"])
        self.assertEqual(self.ledger()[-1], ("13:00", "over_budget", None))

    def test_a_refused_continuation_fails_closed(self):
        beat = self.heartbeat()
        self.clock = at(9, 31)
        beat.tick()
        self.clock = at(13, 1)
        with patch("core.runtime.rehearsal.heartbeat.continue_home", side_effect=RehearsalError("home_mode_mismatch")):
            self.assertEqual(beat.tick()["outcome"], "failed")
        self.clock = at(13, 2, day=19)
        self.assertEqual(beat.tick()["outcome"], "blocked")  # Waits for the operator.

    def test_configuration_is_validated(self):
        for bad in ({"slots": ["9:30"]}, {"slots": []}, {"slots": ["25:00"]},
                    {"gathering_budget_usd": "5", "daily_budget_usd": "3"},
                    {"mode": "real"}, {"timezone": "Not/AZone"}, {"surprise": 1},
                    {"grace_minutes": 0}):
            with self.subTest(bad=bad), self.assertRaises(RehearsalError):
                Schedule.from_config({**CONFIG, **bad})
        real = Schedule.from_config({**CONFIG, "mode": "real", "models_file": "/etc/paradoxtrader/models.json"})
        self.assertEqual(real.mode, "real")

    def test_cli_status_and_real_mode_needs_the_key_first(self):
        spec = importlib.util.spec_from_file_location("heartbeat_cli", ROOT / "scripts" / "heartbeat.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        config = Path(self.temp.name) / "heartbeat.json"
        config.write_text(json.dumps(CONFIG))
        self.assertEqual(cli.main(["--root", str(self.store.root), "--config", str(config), "status"]), 0)
        config.write_text(json.dumps({**CONFIG, "mode": "real", "models_file": "/nope.json"}))
        with patch.dict("os.environ", {"REHEARSAL_OPENROUTER_API_KEY": ""}), self.assertRaises(ValueError):
            cli.main(["--root", str(self.store.root), "--config", str(config), "tick"])
        self.assertFalse((self.store.root / "heartbeat.sqlite3").exists() and self.ledger())

    def test_timer_never_catches_up_and_service_is_not_enabled_by_the_installer(self):
        timer = (ROOT / "deploy/systemd/paradoxtrader-heartbeat.timer").read_text()
        self.assertIn("Persistent=false", timer)
        installer = (ROOT / "deploy/install_host.sh").read_text()
        self.assertNotIn("paradoxtrader-heartbeat", installer)
        service = (ROOT / "deploy/systemd/paradoxtrader-heartbeat.service").read_text()
        self.assertIn("User=paradoxtrader", service)


if __name__ == "__main__":
    unittest.main()
