"""Actual temporary mock-engine data, not hand-authored order-state examples."""
import contextlib
from decimal import Decimal
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts import build_lineage_fixture as builder
from tests.test_agent_loop import block_network


class LineageFixtureTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        guards = block_network(self.stack)
        for guard in guards:
            self.addCleanup(guard.assert_not_called)

    def test_checked_in_example_matches_engine_and_is_reproducible(self):
        first = builder.build_fixture()
        self.assertEqual(first, builder.build_fixture())
        self.assertEqual(first, json.loads(builder.OUTPUT.read_text()))
        self.assertEqual(first['mode'], 'mock_demo')
        self.assertEqual(first['agent_id'], 'alchemist')
        self.assertEqual(first['list']['total'], 4)
        self.assertEqual(set(first['agent_lists']), set(builder.AGENTS))
        self.assertEqual(len(first['details']), 16)

    def test_three_inquiries_can_wait_pause_or_revisit_without_trade_proposals(self):
        data = builder.build_fixture()
        untouched = [detail for detail in data['details'].values()
                     if detail['inquiry']['agent_id'] == 'alchemist' and not detail['orders']]
        self.assertEqual(len(untouched), 3)
        self.assertTrue(all(not d['proposals'] and not d['fills'] and not d['positions'] for d in untouched))
        self.assertTrue(any(d['inquiry']['state'] == 'paused' for d in untouched))
        revisited = next(d for d in untouched if 'revisited' in d['inquiry']['title'])
        self.assertEqual(revisited['inquiry']['state'], 'open')
        self.assertGreaterEqual(len(revisited['entries']), 2)
        kinds = [event['kind'] for event in revisited['events']]
        self.assertTrue(any('revisit' in kind for kind in kinds))

    def test_one_position_comes_from_confirmed_fills_and_preserves_missing_marks_and_fees(self):
        data = builder.build_fixture()
        traded = next(detail for detail in data['details'].values() if detail['orders'])
        self.assertEqual(len(traded['orders']), 2)
        self.assertEqual(len(traded['positions']), 1)
        self.assertEqual(len(traded['fills']), 4)
        self.assertEqual(len({order['client_order_id'] for order in traded['orders']}), 2)
        self.assertTrue(all(order['status'] == 'filled' and order['broker'] == 'mock' for order in traded['orders']))
        position = traded['positions'][0]
        self.assertEqual(position['status'], 'closed')
        self.assertEqual(position['qty'], 0)
        self.assertIsNone(position['fees'])
        self.assertIsNone(position['unrealized_pnl'])
        self.assertIsNone(position['market_value'])
        expected = (Decimal('2.70') * 2 - Decimal('2.40') - Decimal('2.50')) * 100
        self.assertEqual(Decimal(position['gross_realized_pnl']), expected)
        self.assertEqual(len(traded['reviews']), 1)
        for field in ('proposal_id', 'order_id', 'position_id'):
            self.assertIsNotNone(traded['reviews'][0][field])

    def test_fixture_has_no_private_memory_or_provider_fields_and_does_not_touch_real_stores(self):
        root = Path(builder.REPO_ROOT)
        existing = {path: path.stat().st_mtime_ns for folder in (root / 'data', root / 'agents') if folder.exists()
                    for path in folder.rglob('*.sqlite3')}
        fixture = builder.build_fixture()
        text = json.dumps(fixture)
        for field in ('api_key', 'api_secret', 'private_journal', 'innermost', 'system_prompt', 'Authorization'):
            self.assertNotIn(field, text)
        after = {path: path.stat().st_mtime_ns for folder in (root / 'data', root / 'agents') if folder.exists()
                 for path in folder.rglob('*.sqlite3')}
        self.assertEqual(existing, after)
        self.assertTrue(all(detail['inquiry']['phase'] == 0 and detail['inquiry']['visibility'] == 'owner'
                            for detail in fixture['details'].values()))

    def test_each_owner_list_contains_only_private_owned_records_and_only_pilot_has_orders(self):
        fixture = builder.build_fixture()
        for aid, listing in fixture['agent_lists'].items():
            self.assertEqual(listing['total'], 4 if aid == 'alchemist' else 2)
            for item in listing['inquiries']:
                detail = fixture['details'][item['inquiry_id']]
                self.assertEqual(detail['inquiry']['agent_id'], aid)
                self.assertEqual(detail['inquiry']['visibility'], 'owner')
                self.assertEqual(detail['inquiry']['phase'], 0)
                if aid != 'alchemist':
                    self.assertEqual(detail['proposals'], [])
                    self.assertEqual(detail['orders'], [])
                    self.assertEqual(detail['fills'], [])
                    self.assertEqual(detail['positions'], [])
