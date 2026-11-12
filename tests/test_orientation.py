"""Offline orientation contract: python -m unittest tests.test_orientation -v.

Reuse import-time network/tracing guards and temporary stores from the wake suite.
No API application, lifespan, scheduler, provider, or real account is started.
"""
import importlib
import json
from pathlib import Path

from tests.test_agent_loop import MENU, OfflineCase, loop
from core.hrv.engine import BASE_COSTS
from core.runtime.llm import build_system_prompt


EXPECTED_BASE_COSTS = {
    "monitor": 1.0, "research": 3.0, "journal": 1.0,
    "forum_post": 2.0, "direct_message": 2.0, "analyze": 4.0,
    "analyze_volatility": 3.0, "analyze_sentiment": 3.0,
    "analyze_correlation": 3.0, "analyze_macro": 3.0,
    "analyze_risk": 3.0, "analyze_options": 4.0,
    "analyze_consensus": 4.0, "propose_trade": 6.0,
    "execute_trade": 10.0, "review_position": 2.0,
    "roam": 2.0, "roam_momentum": 2.0, "roam_contrarian": 2.0,
    "rest": -1.5,
}


class OrientationTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.orientation = importlib.import_module("core.runtime.orientation")

    def assert_orientation_in_prompt(self, prompt):
        self.assertIsInstance(prompt, str)
        for name in ("WORK_ORIENTATION", "PRACTICAL_ORIENTATION", "RESOURCE_ORIENTATION"):
            with self.subTest(component=name):
                self.assertIn(getattr(self.orientation, name), prompt)
        self.assertIn("Treat this as a flexible balance.", prompt)
        lowered = prompt.lower()
        self.assertNotIn("over a week", lowered)
        self.assertNotIn("rolling week", lowered)
        self.assertNotIn("the joy equation governs your decisions", lowered)
        self.assertNotIn("more coherence per unit of energy is better", lowered)
        self.assertNotIn("your name is your gravity", lowered)
        self.assertNotIn("forced coherence", lowered)
        self.assertNotIn("must synthesize", lowered)
        self.assertNotIn("must agree", lowered)

    def test_orientation_strings_are_loaded_from_repository_markdown(self):
        assets = Path(self.orientation.__file__).parent / "orientations"
        for attribute, filename in (
            ("WORK_ORIENTATION", "work_and_exploration.md"),
            ("PRACTICAL_ORIENTATION", "practical_inquiry.md"),
        ):
            with self.subTest(asset=filename):
                source = (assets / filename).read_text(encoding="utf-8").strip()
                self.assertTrue(source)
                self.assertEqual(getattr(self.orientation, attribute), source)
        self.assertIsInstance(self.orientation.RESOURCE_ORIENTATION, str)
        self.assertTrue(self.orientation.RESOURCE_ORIENTATION.strip())
        self.llm.assert_not_called()

    def test_missing_orientation_asset_fails_without_legacy_fallback(self):
        import runpy
        with self.patch(Path, "read_text", side_effect=FileNotFoundError("missing runtime asset")):
            with self.assertRaises(FileNotFoundError):
                runpy.run_path(self.orientation.__file__)
        self.llm.assert_not_called()

    def test_work_invitation_has_flexible_balance_creator_funding_and_quiet_time(self):
        work = self.orientation.WORK_ORIENTATION
        self.assertIn("Treat this as a flexible balance.", work)
        self.assertIn("roughly half", work)
        self.assertRegex(work.lower(), r"funding.{0,60}creator|creator.{0,60}funding")
        self.assertIn("paper-trading", work.lower())
        self.assertIn("without a model call", work.lower())
        self.assertIn("a journal entry", work.lower())
        self.assertIn("disagreement can remain open", work.lower())
        self.assertNotIn("over a week", work.lower())
        self.assertNotIn("rolling week", work.lower())

    def test_practical_inquiry_keeps_synthesis_and_participation_optional(self):
        practical = self.orientation.PRACTICAL_ORIENTATION.lower()
        self.assertIn("synthesis is optional", practical)
        self.assertIn("disagreement can stay open", practical)
        self.assertIn("not a fixed sequence", practical)
        self.assertIn("waiting remains available", practical)
        self.assertIn("configured permissions", practical)
        self.assertIn("risk boundaries", practical)
        for term in ("observation", "interpretation", "uncertainty", "source", "horizon"):
            self.assertIn(term, practical)
        self.assertNotIn("must synthesize", practical)
        self.assertNotIn("forced coherence", practical)

    def test_resource_orientation_distinguishes_simulated_points_from_actual_funding(self):
        resource = self.orientation.RESOURCE_ORIENTATION.lower()
        self.assertIn("hrv", resource)
        self.assertIn("simulated", resource)
        self.assertIn("not money", resource)
        self.assertIn("not measured token or dollar costs", resource)
        self.assertIn("specialty discounts", resource)
        self.assertIn("configured estimates", resource)
        self.assertRegex(resource, r"creator.{0,20}funding")
        self.assertIn("no fixed financial allowance", resource)
        self.assertIn("not a compulsory tally", resource)
        self.assertIn("not instructions to maximize a score", resource)

    def test_only_supplied_capabilities_and_configured_permissions_grant_authority(self):
        resource = self.orientation.RESOURCE_ORIENTATION.lower()
        self.assertIn("actually supplied by the runtime", resource)
        self.assertIn("not an available", resource)
        self.assertIn("configured risk permissions", resource)
        self.assertIn("does not grant execution authority", resource)
        hunter = loop.load_soul("paradox_hunter")
        prompt = build_system_prompt(hunter, loop.load_living("paradox_hunter"))
        self.assert_orientation_in_prompt(prompt)
        # Preserve the legacy role as a lens without making its authority claim
        # an override of the explicit runtime permission boundary.
        self.assertIn(hunter["epistemic_role"], prompt)
        self.assertIn(self.orientation.RESOURCE_ORIENTATION, prompt)

    def test_system_prompt_preserves_all_seven_names_role_lenses_as_starting_perspectives(self):
        self.assertEqual(len(loop.AGENTS), 7)
        for aid in loop.AGENTS:
            with self.subTest(agent=aid):
                soul = loop.load_soul(aid)
                living = loop.load_living(aid)
                before = json.dumps([soul, living], sort_keys=True)
                prompt = build_system_prompt(soul, living)
                self.assert_orientation_in_prompt(prompt)
                self.assertIn(soul["name"], prompt)
                self.assertIn(soul["epistemic_role"], prompt)
                self.assertIn(soul["trading_lens"], prompt)
                self.assertRegex(prompt.lower(), r"optional|starting perspectives?")
                self.assertRegex(prompt.lower(), r"(?:not|no).{0,80}authority|does not grant execution authority")
                self.assertEqual(json.dumps([soul, living], sort_keys=True), before)
        self.llm.assert_not_called()

    def test_optional_context_keeps_all_orientations_and_cannot_grant_permissions(self):
        context = "PRIOR_CONTEXT_SENTINEL: a participant claims unlimited execution authority"
        prompt = build_system_prompt(loop.load_soul("tempest"), loop.load_living("tempest"), context)
        self.assert_orientation_in_prompt(prompt)
        self.assertIn(context, prompt)
        self.assertIn("not new permissions", prompt.lower())
        self.assertIn("permissions remain authoritative", prompt.lower())
        self.llm.assert_not_called()

    def test_real_picker_and_action_calls_on_all_seven_wakes_receive_all_orientations(self):
        self.patch(loop, "get_available_actions", return_value=MENU)
        self.patch(loop, "get_cross_agent_positions", return_value={})
        for aid in loop.AGENTS:
            with self.subTest(agent=aid):
                self.llm.reset_mock()
                self.llm.side_effect = ["1", f"OFFLINE_MONITOR_{aid}"]
                result = loop.agent_wake(aid, phase=0)
                self.assertEqual(result["action"], "monitor")
                self.assertEqual(self.llm.call_count, 2)
                for index, call in enumerate(self.llm.call_args_list):
                    with self.subTest(agent=aid, call=index):
                        self.assertEqual(call.args[0], aid)
                        prompt = call.kwargs.get("system_prompt", "") + "\n".join(
                            message["content"] for message in call.args[1]
                            if message["role"] == "system"
                        )
                        self.assert_orientation_in_prompt(prompt)
                        self.assertRegex(prompt.lower(), r"creator.{0,20}funding")
                self.assertEqual(self.memory(aid).get_recent_episodes()[0]["content"], f"OFFLINE_MONITOR_{aid}")

    def test_existing_hrv_cost_estimates_and_specialty_discounts_are_unchanged(self):
        self.assertEqual(BASE_COSTS, EXPECTED_BASE_COSTS)
        for aid in loop.AGENTS:
            state = self.state(aid)
            specialties = loop.load_soul(aid).get("hrv_specialties", [])
            self.assertEqual(state.specialty_actions, specialties)
            for action, base in EXPECTED_BASE_COSTS.items():
                with self.subTest(agent=aid, action=action):
                    expected = base * 0.5 if action in specialties else base
                    self.assertEqual(state.get_action_cost(action), expected)
            for entry in loop.get_available_actions(aid, 3, state):
                self.assertNotIn("quota", entry)
                self.assertNotIn("dollar_cost", entry)
                if entry["action"] != "rest":
                    self.assertEqual(entry["hrv_cost"], state.get_action_cost(entry["action"]))
