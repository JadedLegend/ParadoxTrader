"""One continuing home: memory and witness carry from one run into the next.

Actual temporary private stores, scripted offline HTTP, structurally blocked network.
"""
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.continuity import owner_continuity
from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.home import continue_home, previous_run_ids, read_home
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalConflict, RehearsalError, RehearsalStore
from core.runtime.rehearsal.witness import WitnessStore
from tests.test_rehearsal_provider import manifest


def digest_tree(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file()}


class HomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RehearsalStore(Path(self.temp.name) / "runs")
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def day(self):
        run_id = self.store.prepare(manifest())["run_id"]
        return run_id

    def live(self, run_id):
        controller = RehearsalController(self.store, run_id,
                                         transport=OpenRouterTransport("scripted-offline", http_post=ScriptedHTTP()))
        return controller.run()

    def test_a_new_day_starts_with_yesterdays_notes_and_witness(self):
        first = self.day()
        self.assertEqual(self.live(first)["status"], "completed")
        before = digest_tree(self.store.run_path(first))
        yesterday = {job["agent_id"]: job for job in self.store.list_jobs(first) if job["round"] == 1}
        siren_note = next(ref for ref in yesterday["siren"]["record_refs"] if ref["kind"] == "journal")

        second = self.day()
        result = continue_home(self.store, second, first)
        self.assertEqual(result["previous_run_id"], first)
        self.assertIn("memory/siren.sqlite3", result["present"])
        self.assertIn("witness.sqlite3", result["present"])
        self.assertEqual(read_home(self.store, second)["previous_run_id"], first)
        self.assertEqual(previous_run_ids(self.store, second), [first])

        # Siren's first wake today is offered her own note from yesterday.
        job = next(j for j in self.store.list_jobs(second) if j["agent_id"] == "siren" and j["round"] == 1)
        context = owner_continuity(self.store, second, job)
        self.assertEqual(context["status"], "available")
        self.assertIn({"kind": "journal", "id": siren_note["id"]}, context["refs"])
        self.assertIn("scripted private example note", context["excerpts"][0]["body"])
        self.assertEqual(context["excerpts"][0]["earlier_run_id"], first)
        self.assertNotIn("wake_id", context["excerpts"][0])

        # Tempest only rested and inquired: nothing to carry, nothing invented.
        tempest = next(j for j in self.store.list_jobs(second) if j["agent_id"] == "tempest" and j["round"] == 1)
        self.assertEqual(owner_continuity(self.store, second, tempest)["status"], "empty")

        # The witness's earlier accounts about each owner are readable today.
        carried = WitnessStore(self.store.safe_run_file(second, "witness.sqlite3")).list_accounts("siren", limit=20)
        self.assertGreater(carried["total"], 0)

        # Today runs normally and yesterday is never changed.
        self.assertEqual(self.live(second)["status"], "completed")
        self.assertEqual(digest_tree(self.store.run_path(first)), before)
        self.assertGreater(WitnessStore(self.store.safe_run_file(second, "witness.sqlite3"))
                           .list_accounts("siren", limit=20)["total"], carried["total"])

    def test_notes_carry_across_several_days(self):
        days = [self.day()]
        self.live(days[0])
        for _ in range(2):
            days.append(self.day())
            continue_home(self.store, days[-1], days[-2])
            self.live(days[-1])
        self.assertEqual(previous_run_ids(self.store, days[-1]), [days[1], days[0]])
        with sqlite3.connect(self.store.safe_run_file(days[-1], "memory/siren.sqlite3")) as conn:
            notes = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        with sqlite3.connect(self.store.safe_run_file(days[0], "memory/siren.sqlite3")) as conn:
            first_day = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        self.assertEqual(notes, 3 * first_day)

    def test_retry_is_safe_and_a_different_previous_day_is_refused(self):
        first, other = self.day(), self.day()
        self.live(first)
        self.live(other)
        second = self.day()
        continue_home(self.store, second, first)
        again = continue_home(self.store, second, first)
        self.assertEqual(again["carried_now"], [])
        with self.assertRaises(RehearsalConflict):
            continue_home(self.store, second, other)

    def test_refuses_unfinished_started_self_and_cycles(self):
        unfinished = self.day()
        second = self.day()
        with self.assertRaises(RehearsalError):
            continue_home(self.store, second, unfinished)
        with self.assertRaises(RehearsalError):
            continue_home(self.store, second, second)
        self.assertIsNone(read_home(self.store, second))

        finished = self.day()
        self.live(finished)
        started = self.day()
        self.live(started)
        with self.assertRaises(RehearsalError):
            continue_home(self.store, started, finished)

    def test_refuses_a_different_mode(self):
        first = self.day()
        self.live(first)
        second = self.day()
        real = dict(self.store.get_manifest(second), mode="real")
        with patch.object(self.store, "get_manifest", side_effect=lambda rid: real if rid == second else manifest()):
            with self.assertRaises(RehearsalError):
                continue_home(self.store, second, first)

    def test_a_corrupt_link_is_refused_not_trusted(self):
        second = self.day()
        self.store.safe_run_file(second, "home.json").write_text(json.dumps({"previous_run_id": "../x"}))
        with self.assertRaises(RehearsalError):
            read_home(self.store, second)
        job = next(j for j in self.store.list_jobs(second) if j["agent_id"] == "siren" and j["round"] == 1)
        self.assertEqual(owner_continuity(self.store, second, job)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
