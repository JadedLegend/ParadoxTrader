"""UI examples come from public personas and current menu logic, not provider state."""
import json
from pathlib import Path
import unittest

from scripts.build_ui_fixtures import build_fixture, OUTPUT


class UIFixtureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(OUTPUT.read_text(encoding='utf-8'))

    def test_checked_in_fixture_matches_offline_generation(self):
        self.assertEqual(self.fixture, build_fixture())

    def test_all_seven_agents_have_unique_complete_scenarios(self):
        agents = self.fixture['agents']
        self.assertEqual(len(agents), 7)
        self.assertEqual(len({a['agent_id'] for a in agents}), 7)
        for a in agents:
            self.assertIsNone(a['last_tick_at'])
            self.assertEqual(a['hrv_status'], 'ok')
            self.assertGreater(a['max_hrv'], a['hrv'])
            self.assertEqual(set(self.fixture['windows'][a['agent_id']]),
                             {'phase0', 'phase1', 'phase3', 'interval'})

    def test_menus_are_affordable_unique_and_phase_compatible(self):
        root = Path(__file__).resolve().parents[1]
        from core.hrv.engine import AgentHRVState
        for aid, scenarios in self.fixture['windows'].items():
            soul = json.loads((root / 'agents' / aid / 'soul.json').read_text())
            for scenario, window in scenarios.items():
                with self.subTest(agent=aid, scenario=scenario):
                    state = AgentHRVState(aid, hrv=window['hrv'], specialty_actions=soul['hrv_specialties'])
                    actions = window['choices']
                    names = [a['action'] for a in actions]
                    self.assertLessEqual(len(names), 5)
                    self.assertEqual(len(names), len(set(names)))
                    self.assertIn('rest', names)
                    for action in actions:
                        self.assertTrue(state.can_perform(action['action']))
                        expected = -min(state.recovery_rate, state.max_hrv-state.hrv) if action['action']=='rest' else state.get_action_cost(action['action'])
                        self.assertEqual(action['hrv_cost'], expected)
                    if window['phase'] == 0:
                        self.assertFalse(set(names) & {'forum_post', 'direct_message', 'analyze_consensus'})
                    if window['in_interval']:
                        self.assertEqual(names, ['rest'])

    def test_examples_distinguish_confirmed_empty_and_unknown_positions(self):
        positions = self.fixture['positions']
        self.assertEqual(positions['siren']['status'], 'ok')
        self.assertEqual(positions['siren']['positions'], [])
        self.assertEqual(positions['alchemist']['status'], 'not_configured')
        self.assertEqual(positions['weaver']['status'], 'error')
        self.assertEqual(positions['tempest']['positions'][0]['symbol'], 'DEMO')
        self.assertEqual(self.fixture['kind'], 'fixture')

    def test_fixture_contains_no_config_credentials_or_personal_runtime_records(self):
        rendered = json.dumps(self.fixture).lower()
        for marker in ['api_key', 'api_secret', 'secret_key', 'authorization', 'bearer ', 'paper-api.alpaca']:
            self.assertNotIn(marker, rendered)
        self.assertNotIn('episodes', self.fixture)
        self.assertNotIn('journal', self.fixture)
        for value in self.fixture['definitions'].values():
            self.assertEqual(value['self_definition_history'], [])


if __name__ == '__main__':
    unittest.main()
