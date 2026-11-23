"""The skill shelf, phase 1 of docs/specs/SKILL_SHELF.md: the page carries a table
of contents and the always lines; a skill choice opens one full text. Scripted
HTTP; the network is blocked."""
from datetime import datetime, timezone
import json
import unittest

from core.runtime.llm import build_system_prompt
from core.runtime.orientation import SHELF_ORIENTATION, SKILLS, skill_text
from core.runtime.rehearsal.controller import CHOICE_INSTRUCTIONS, RehearsalController, validate_choice
from core.runtime.rehearsal.examples import ScriptedHTTP, ScriptedResponse
from core.runtime.rehearsal.heartbeat import Heartbeat, Schedule
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest
from tests.test_market_window import BlockedNetwork


class ShelfTests(unittest.TestCase):
    def test_the_page_lists_every_skill_and_its_always_line_but_not_the_full_text(self):
        self.assertEqual(set(SKILLS), {"learning-from-inquiry", "making-calls", "outside-voices"})
        prompt = build_system_prompt({"agent_id": "tempest"}, {}, shelf=True)
        self.assertIn(SHELF_ORIENTATION, prompt)
        for skill in SKILLS.values():
            with self.subTest(skill=skill["name"]):
                self.assertIn(f"- {skill['name']}: {skill['description']}", prompt)
                self.assertTrue(skill["always"])
                self.assertIn(skill["always"], prompt)
                self.assertNotIn(skill["body"], prompt)
        self.assertNotIn("TODO", prompt)
        self.assertIn('{"action":"skill","name":"<a name from the shelf>"}', CHOICE_INSTRUCTIONS)

    def test_paths_without_the_skill_choice_keep_every_full_text(self):
        prompt = build_system_prompt({"agent_id": "tempest"}, {})  # agent_loop and council.
        self.assertNotIn("SKILLS ON THE SHELF", prompt)
        for skill in SKILLS.values():
            self.assertIn(skill["body"], prompt)

    def test_a_skill_opens_by_its_exact_name_only(self):
        self.assertEqual(skill_text("outside-voices"), SKILLS["outside-voices"]["body"])
        for name in ("Outside-Voices", "outside voices", "../outside-voices", "", None, 7):
            self.assertIsNone(skill_text(name))

    def test_a_skill_choice_is_strict(self):
        self.assertEqual(validate_choice(json.dumps({"action": "skill", "name": "outside-voices"}))["name"],
                         "outside-voices")
        for broken in ({"action": "skill"}, {"action": "library", "name": "outside-voices"},
                       {"action": "skill", "name": "Outside"}, {"action": "skill", "name": "a/b"},
                       {"action": "skill", "name": "x" * 65}, {"action": "skill", "name": 3},
                       {"action": "skill", "name": "outside-voices", "query": "posts"}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                validate_choice(json.dumps(broken))


class SkillWakeTests(BlockedNetwork):
    def wake(self, name):
        store = RehearsalStore(self.root / "sessions")
        scripted, activity = ScriptedHTTP(), []

        def http(url, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in kwargs["json"]["messages"])
            if "Stable owner ID: tempest" in text and "REHEARSAL CHOICE" in text:
                scripted.calls += 1
                return ScriptedResponse({"id": "skill-1", "model": kwargs["json"].get("model"),
                                         "provider": "scripted-offline",
                                         "choices": [{"message": {"content": json.dumps({"action": "skill", "name": name})},
                                                      "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 60, "completion_tokens": 20,
                                                   "total_tokens": 80, "cost": "0"}})
            if "Stable owner ID: tempest" in text:
                activity.append(text)
            return scripted(url, **kwargs)

        def prepare_day(budget_usd, wakes_per_agent, models=None):
            return store.prepare(day_manifest(wakes=wakes_per_agent, budget=budget_usd))["run_id"]

        def run_wake(run_id, owner, step=None):
            return RehearsalController(store, run_id, transport=OpenRouterTransport(
                "scripted-offline", http_post=http)).run_wake(owner, step=step)

        config = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
                  "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live"}
        beat = Heartbeat(store, Schedule.from_config(config), prepare_day=prepare_day, run_wake=run_wake,
                         now=lambda: datetime(2026, 11, 18, 9, 1, tzinfo=timezone.utc))  # Tempest only.
        run_id = beat.tick()["run_id"]
        [job] = [j for j in store.list_jobs(run_id) if j["wake_id"] == "tempest-r1"]
        return store, run_id, job, activity

    def test_opening_a_skill_delivers_its_full_text_and_keeps_an_optional_note(self):
        store, run_id, job, activity = self.wake("outside-voices")
        self.assertEqual((job["status"], job["action"]), ("completed", "skill"))
        [request] = activity
        self.assertIn("REHEARSAL ACTIVITY: skill", request)
        self.assertIn(SKILLS["outside-voices"]["body"], request)
        self.assertNotIn(SKILLS["learning-from-inquiry"]["body"], request)
        self.assertEqual(len(store.get_decision_details(run_id, "tempest-r1")["requests"]), 2)

    def test_a_name_not_on_the_shelf_is_refused_without_a_second_request(self):
        store, run_id, job, activity = self.wake("no-such-skill")
        self.assertEqual((job["status"], job["failure_code"]), ("failed", "skill_not_found"))
        self.assertEqual(activity, [])


class OpenSkillSittingTests(BlockedNetwork):
    """Shelf phase 2: a skill opened on one move stays at hand for the rest of the wake."""

    def sitting(self, moves, choices):
        store = RehearsalStore(self.root / "sessions")
        scripted, seen = ScriptedHTTP(), []  # seen: (kind, text) for each of Tempest's requests.

        def http(url, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in kwargs["json"]["messages"])
            if "Stable owner ID: tempest" not in text:
                return scripted(url, **kwargs)
            if "REHEARSAL CHOICE" in text:
                move = sum(kind == "choice" for kind, _ in seen)
                seen.append(("choice", text))
                scripted.calls += 1
                return ScriptedResponse({"id": f"sit-{move}", "model": kwargs["json"].get("model"),
                                         "provider": "scripted-offline",
                                         "choices": [{"message": {"content": json.dumps(moves[move])},
                                                      "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 60, "completion_tokens": 20,
                                                   "total_tokens": 80, "cost": "0"}})
            seen.append(("activity", text))
            return scripted(url, **kwargs)

        def prepare_day(budget_usd, wakes_per_agent, models=None):
            return store.prepare(day_manifest(wakes=wakes_per_agent, budget=budget_usd))["run_id"]

        def run_wake(run_id, owner, step=None):
            return RehearsalController(store, run_id, transport=OpenRouterTransport(
                "scripted-offline", http_post=http)).run_wake(owner, step=step)

        config = {"timezone": "UTC", "active_window": ["09:00", "10:00"], "active_interval_minutes": 14,
                  "grace_minutes": 10, "daily_budget_usd": "5.00", "mode": "offline", "dispatch": "live",
                  "choices_per_wake": choices}
        clock = [datetime(2026, 11, 18, 9, 1, tzinfo=timezone.utc)]
        beat = Heartbeat(store, Schedule.from_config(config), prepare_day=prepare_day, run_wake=run_wake,
                         now=lambda: clock[0])
        run_id = beat.tick()["run_id"]  # Tempest only.
        return store, run_id, seen, beat, clock

    def test_later_moves_of_the_wake_still_hold_the_opened_skill(self):
        body = SKILLS["outside-voices"]["body"]
        _, _, seen, _, _ = self.sitting([{"action": "skill", "name": "outside-voices"},
                                         {"action": "journal"}, {"action": "rest"}], choices=4)
        kinds = [kind for kind, _ in seen]
        self.assertEqual(kinds, ["choice", "activity", "choice", "activity", "choice"])  # Rest ended it.
        self.assertNotIn("still at hand", seen[0][1])
        self.assertIn(body, seen[1][1])  # Opening it delivers the text.
        for kind, text in seen[2:]:
            with self.subTest(kind=kind):  # The journal choice, the journal itself, and the rest choice.
                self.assertIn("Skill you opened earlier in this wake (still at hand): outside-voices", text)
                self.assertIn(body, text)
        self.assertIn("choice 3 of 4", seen[-1][1])

    def test_reopening_a_skill_makes_it_the_newest_open_one(self):
        _, _, seen, _, _ = self.sitting([{"action": "skill", "name": "outside-voices"},
                                         {"action": "skill", "name": "learning-from-inquiry"},
                                         {"action": "skill", "name": "outside-voices"},
                                         {"action": "rest"}], choices=4)
        last = seen[-1][1]  # The fourth move's choice: both open, oldest first.
        marker = "Skill you opened earlier in this wake (still at hand): "
        reopened = seen[-2][1]
        self.assertEqual(reopened.count(SKILLS["outside-voices"]["body"]), 1)
        self.assertIn(marker + "learning-from-inquiry", reopened)
        self.assertEqual(last.count(marker), 2)
        self.assertLess(last.index(marker + "learning-from-inquiry"), last.index(marker + "outside-voices"))

    def test_opening_a_third_skill_sets_down_the_oldest_during_the_activity(self):
        _, _, seen, _, _ = self.sitting([{"action": "skill", "name": "outside-voices"},
                                         {"action": "skill", "name": "learning-from-inquiry"},
                                         {"action": "skill", "name": "making-calls"}], choices=3)
        kind, text = seen[-1]
        self.assertEqual(kind, "activity")
        self.assertIn(SKILLS["making-calls"]["body"], text)
        self.assertIn(SKILLS["learning-from-inquiry"]["body"], text)
        self.assertNotIn(SKILLS["outside-voices"]["body"], text)

    def test_the_skill_goes_back_on_the_shelf_when_the_wake_ends(self):
        _, _, seen, beat, clock = self.sitting([{"action": "skill", "name": "outside-voices"},
                                                {"action": "rest"}, {"action": "rest"}], choices=2)
        self.assertEqual(len(seen), 3)  # Skill, its reading, then rest.
        clock[0] = datetime(2026, 11, 18, 9, 15, tzinfo=timezone.utc)  # Tempest's next wake.
        for _ in range(3):  # Other agents due within the grace window go first, three per tick.
            beat.tick()
        self.assertEqual([kind for kind, _ in seen[3:]], ["choice"])
        self.assertNotIn("still at hand", seen[3][1])


if __name__ == "__main__":
    unittest.main()
