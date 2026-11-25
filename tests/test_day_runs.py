"""Day runs: each agent's wakes arrive one at a time on its own clock.

Actual temporary private stores, scripted offline HTTP, structurally blocked network.
"""
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from api.rehearsal import _owner_wake, _witness_account
from core.runtime.rehearsal.continuity import owner_continuity
from core.runtime.rehearsal.controller import RehearsalController
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.home import continue_home, previous_run_ids
from core.runtime.rehearsal.provider import OpenRouterTransport, validate_manifest
from core.runtime.rehearsal.store import MAX_WAKES_PER_AGENT, RehearsalConflict, RehearsalError, RehearsalStore
from core.runtime.rehearsal.witness import WitnessStore
from tests.test_rehearsal_provider import manifest

OWNERS = ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter")


def day_manifest(wakes=6, budget="5.00"):
    raw = manifest()
    raw["kind"] = "day"
    raw["limits"]["wakes_per_agent"] = wakes
    raw["limits"]["max_requests"] = 2 * wakes * 7
    raw["limits"]["budget_usd"] = budget
    return raw


class DayRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = RehearsalStore(Path(self.temp.name) / "sessions")
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.http = ScriptedHTTP()

    def controller(self, run_id):
        return RehearsalController(self.store, run_id, transport=OpenRouterTransport(
            "scripted-offline", http_post=self.http))

    def test_a_day_starts_empty_and_each_wake_arrives_on_its_own(self):
        day = self.store.prepare(day_manifest())["run_id"]
        self.assertEqual(self.store.list_jobs(day), [])
        self.assertEqual(self.store.get_run(day)["kind"], "day")

        siren = self.controller(day).run_wake("siren")  # Only Siren is awake.
        self.assertEqual((siren["wake_id"], siren["status"], siren["action"]), ("siren-r1", "completed", "journal"))
        self.assertEqual([job["agent_id"] for job in self.store.list_jobs(day)], ["siren"])
        self.assertEqual(self.store.get_run(day)["status"], "open")

        self.controller(day).run_wake("tempest")
        second = self.store.add_wake(day, "siren")  # Her next wake is round 2 of today.
        self.assertEqual(second["wake_id"], "siren-r2")
        context = owner_continuity(self.store, day, second)
        self.assertEqual(context["status"], "available")
        self.assertIn({"kind": "journal", "id": siren["record_refs"][0]["id"], "wake_id": "siren-r1"}, context["refs"])

    def test_an_owner_cannot_start_a_new_wake_while_one_is_unfinished(self):
        day = self.store.prepare(day_manifest())["run_id"]
        self.store.add_wake(day, "oracle")
        with self.assertRaises(RehearsalConflict):
            self.store.add_wake(day, "oracle")
        self.store.add_wake(day, "weaver")  # Others are independent.

    def test_a_wake_left_pending_is_finished_by_that_agents_next_wake(self):
        day = self.store.prepare(day_manifest())["run_id"]
        self.store.add_wake(day, "oracle")  # Reset to pending, e.g. after an earlier failure.
        finished = self.controller(day).run_wake("oracle")
        self.assertEqual((finished["wake_id"], finished["status"]), ("oracle-r1", "completed"))
        self.assertEqual([j["wake_id"] for j in self.store.list_jobs(day)], ["oracle-r1"])
        self.assertEqual(self.controller(day).run_wake("oracle")["wake_id"], "oracle-r2")

    def test_a_journal_naming_notes_it_cannot_condense_fails_cleanly(self):
        from core.runtime.rehearsal.examples import ScriptedResponse

        def bad_distill(url, *, json=None, **kwargs):
            text = chr(10).join(str(m.get("content", "")) for m in (json or {}).get("messages", []))
            if "REHEARSAL CHOICE" in text and "Stable owner ID: alchemist" in text:
                content = '{"action":"journal","journal_mode":"distill","source_ids":[99]}'
                return ScriptedResponse({"id": "x", "model": json.get("model"), "provider": "scripted-offline",
                                         "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                                                   "cost": "0"}})
            return self.http(url, json=json, **kwargs)

        day = self.store.prepare(day_manifest())["run_id"]
        controller = RehearsalController(self.store, day, transport=OpenRouterTransport(
            "scripted-offline", http_post=bad_distill))
        job = controller.run_wake("alchemist")
        self.assertEqual((job["status"], job["failure_code"]), ("failed", "invalid_journal_sources"))
        self.assertEqual(self.controller(day).run_wake("alchemist")["wake_id"], "alchemist-r2")  # Not stuck.

    def test_day_runs_give_replies_more_room_and_rehearsals_do_not(self):
        roomy = day_manifest()
        roomy["limits"]["max_output_tokens"] = 3000
        for row in roomy["catalog_snapshot"]["models"]:
            row["max_completion_tokens"] = 8192
        day = self.store.prepare(roomy)["run_id"]
        self.assertEqual(self.store.get_run(day)["limits"]["max_output_tokens"], 3000)
        self.assertEqual(validate_manifest(roomy)["limits"]["max_output_tokens"], 3000)
        too_roomy = manifest()
        too_roomy["limits"]["max_output_tokens"] = 3000
        with self.assertRaises(RehearsalError):
            self.store.prepare(too_roomy)
        roomy["limits"]["max_output_tokens"] = 3001
        with self.assertRaises(RehearsalError):
            self.store.prepare(roomy)

    def test_daily_wake_limit(self):
        day = self.store.prepare(day_manifest(wakes=2))["run_id"]
        for _ in range(2):
            self.controller(day).run_wake("shadow")
        with self.assertRaises(RehearsalError):
            self.store.add_wake(day, "shadow")

    def test_the_daily_budget_holds_across_wakes(self):
        priced = day_manifest(wakes=20, budget="0.06")
        for row in priced["catalog_snapshot"]["models"]:  # Offline examples are otherwise free.
            row["pricing"] = {"prompt": "0.000001", "completion": "0.000002", "request": "0.001"}
        day = self.store.prepare(priced)["run_id"]
        outcomes = [self.controller(day).run_wake("oracle")["status"] for _ in range(6)]
        self.assertEqual(outcomes[0], "completed")
        self.assertIn("failed", outcomes)  # Admission refuses once the day's budget is reserved.
        failed = [job for job in self.store.list_jobs(day) if job["status"] == "failed"]
        self.assertTrue(all(job["failure_code"] == "admission_budget_exceeded" for job in failed))

    def test_stop_closes_the_door_on_new_wakes(self):
        day = self.store.prepare(day_manifest())["run_id"]
        self.controller(day).run_wake("alchemist")
        self.store.request_stop(day)
        with self.assertRaises(RehearsalConflict):
            self.store.add_wake(day, "alchemist")

    def test_two_days_with_all_seven_on_their_own_clocks(self):
        first = self.store.prepare(day_manifest())["run_id"]
        order = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter",
                 "siren", "weaver", "paradox_hunter"]  # Staggered; some wake twice.
        for owner in order:
            self.assertEqual(self.controller(first).run_wake(owner)["status"], "completed")
        closed = self.store.close_day(first)
        self.assertEqual(closed["status"], "completed")
        accounts = WitnessStore(self.store.safe_run_file(first, "witness.sqlite3"))
        self.assertGreaterEqual(accounts.list_accounts("siren", limit=20)["total"], 2)

        second = self.store.prepare(day_manifest())["run_id"]
        continue_home(self.store, second, first)
        self.assertEqual(previous_run_ids(self.store, second), [first])
        job = self.store.add_wake(second, "siren")
        carried = owner_continuity(self.store, second, job)
        self.assertEqual(carried["status"], "available")
        self.assertTrue(all(item.get("earlier_run_id") == first for item in carried["excerpts"]))

    def test_the_witness_keeps_writing_through_a_full_day_of_moves(self):
        # A day stores each move as its own round, up to MAX_WAKES_PER_AGENT.
        # The witness was written for two rounds and went silent from round 3.
        day = self.store.prepare(day_manifest(wakes=MAX_WAKES_PER_AGENT, budget="100.00"))["run_id"]
        for number in range(1, MAX_WAKES_PER_AGENT + 1):
            controller = self.controller(day)
            self.assertEqual(controller.run_wake("oracle")["status"], "completed")
            self.assertEqual(controller.witness_errors, [], f"oracle-r{number}")
        witness = WitnessStore(self.store.safe_run_file(day, "witness.sqlite3"))
        accounts = witness.list_accounts("oracle", limit=20)
        self.assertEqual(accounts["total"], MAX_WAKES_PER_AGENT)
        latest = accounts["accounts"][0]
        self.assertIn(f"oracle-r{MAX_WAKES_PER_AGENT}: selected", latest["content"])
        # The dashboard's witness page serves the account for the day's last move.
        served = _witness_account(latest, "oracle")
        self.assertEqual(served["content"], latest["content"])
        self.assertEqual(len(served["source_refs"]), len(latest["source_refs"]))

    def test_the_whole_day_snapshot_holds_every_wake_and_request(self):
        day = self.store.prepare(day_manifest())["run_id"]
        for _ in range(3):  # 21 wakes and their requests: more than one two-round rehearsal.
            for owner in OWNERS:
                self.controller(day).run_wake(owner)
        self.assertEqual(self.store.close_day(day)["status"], "completed")
        snapshot = self.store.get_witness_snapshot(day)
        self.assertEqual(len(snapshot["jobs"]), 21)
        self.assertEqual(len(snapshot["requests"]), self.store.list_requests(day)["total"])
        self.assertGreater(len(snapshot["requests"]), 28)
        served = _witness_account(WitnessStore(self.store.safe_run_file(day, "witness.sqlite3")).record(
            snapshot, scope="steward", operation_key="whole-day"), "steward")
        self.assertIn("Wake outcomes: completed=21.", served["content"])

    def test_rehearsals_are_unchanged_and_the_kinds_do_not_mix(self):
        rehearsal = self.store.prepare(manifest())["run_id"]
        self.assertNotIn("kind", self.store.get_manifest(rehearsal))
        self.assertEqual(len(self.store.list_jobs(rehearsal)), 14)
        with self.assertRaises(RehearsalError):
            self.controller(rehearsal).run_wake("tempest")
        with self.assertRaises(RehearsalError):
            self.store.add_wake(rehearsal, "tempest")
        day = self.store.prepare(day_manifest())["run_id"]
        with self.assertRaises(RehearsalError):
            self.controller(day).run()
        too_many = manifest()
        too_many["limits"]["wakes_per_agent"] = 3
        with self.assertRaises(RehearsalError):
            self.store.prepare(too_many)  # Rehearsals keep exactly two rounds.
        self.assertEqual(validate_manifest(day_manifest())["kind"], "day")

    def test_store_and_provider_accept_the_same_day_turn_limit(self):
        # 20 wakes x 6 moves = 120 turns must prepare AND run; one over the cap fails both.
        from core.runtime.rehearsal.provider import ManifestError
        from core.runtime.rehearsal.store import MAX_WAKES_PER_AGENT
        from core.runtime.rehearsal.store import _validate_manifest as store_validate
        for turns in (80, 96, MAX_WAKES_PER_AGENT):
            with self.subTest(turns=turns):
                self.assertEqual(validate_manifest(day_manifest(wakes=turns))["kind"], "day")
                self.assertEqual(store_validate(day_manifest(wakes=turns))["kind"], "day")
        with self.assertRaises(ManifestError):
            validate_manifest(day_manifest(wakes=MAX_WAKES_PER_AGENT + 1))
        with self.assertRaises(RehearsalError):
            store_validate(day_manifest(wakes=MAX_WAKES_PER_AGENT + 1))

    def test_api_accepts_any_wake_number_of_the_same_owner_only(self):
        self.assertTrue(_owner_wake("siren", "siren-r1"))
        self.assertTrue(_owner_wake("siren", "siren-r120"))
        for owner, wake in (("siren", "siren-r121"), ("siren", "siren-r1000"), ("siren", "siren-r0"), ("siren", "siren-r01"),
                            ("siren", "tempest-r1"), ("siren", "siren-r1x"), ("shadow", "shadow-r")):
            with self.subTest(wake=wake):
                self.assertFalse(_owner_wake(owner, wake))


if __name__ == "__main__":
    unittest.main()
