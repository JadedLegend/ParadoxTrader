"""Actual-store local fixture tests; no real session or provider is read."""
import json
from pathlib import Path
import unittest
from scripts.build_rehearsal_fixture import build_fixture, OUTPUT, RUN_ID


class RehearsalFixtureTests(unittest.TestCase):
    def test_checked_in_fixture_matches_isolated_actual_controller(self):
        self.assertEqual(json.loads(OUTPUT.read_text()), build_fixture())

    def test_all_seven_two_rounds_have_only_allowed_optional_actions(self):
        fixture = build_fixture()
        run = fixture['runs'][0]
        self.assertEqual(run['mode'], 'offline')
        self.assertEqual(run['status'], 'completed')
        self.assertEqual(len(run['agents']), 7)
        jobs = fixture['jobs'][RUN_ID]
        self.assertEqual(len(jobs), 14)
        actions = {job['action'] for job in jobs}
        self.assertEqual(actions, {'rest', 'journal', 'inquire', 'library', 'roam'})
        for job in jobs:
            self.assertEqual(job['status'], 'completed')
            if job['action'] == 'rest':
                self.assertEqual(job['record_refs'], [])
            self.assertNotIn('content', job)
            self.assertNotIn('output', job)
        self.assertLessEqual(run['request_count'], 28)
        self.assertLessEqual(len(fixture['requests'][RUN_ID]), 28)

    def test_private_records_are_owner_keyed_without_trading_or_innermost_material(self):
        fixture = build_fixture()
        for key, payload in fixture['records'][RUN_ID].items():
            owner, kind, record_id = key.split('|', 2)
            self.assertEqual(payload['agent_id'], owner)
            self.assertEqual(payload['kind'], kind)
            self.assertEqual(str(payload['id']), record_id)
            self.assertNotEqual(kind, 'innermost')
            if kind == 'inquiry':
                record = payload['record']
                self.assertEqual(record['inquiry']['agent_id'], owner)
                self.assertEqual(record['inquiry']['visibility'], 'owner')
                self.assertEqual(record['orders'], [])
                self.assertEqual(record['proposals'], [])
                self.assertEqual(record['positions'], [])
        for request in fixture['requests'][RUN_ID]:
            for forbidden in ('messages', 'headers', 'api_key', 'content', 'query', 'reasoning'):
                self.assertNotIn(forbidden, request)
