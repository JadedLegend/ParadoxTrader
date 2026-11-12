"""Actual wake integration against temporary lineage with no providers/brokers."""
import json
from pathlib import Path
import sqlite3
from unittest import mock
from uuid import NAMESPACE_URL, uuid5

from tests.test_agent_loop import OfflineCase, loop
from core.runtime.cohort import prepare_cohort
from core.runtime.inquiry import get_inquiry_receipt
from core.trading.lineage import LineageStore, LineageAccessError
from core.usage.context import current_usage_context

MENU = [{'action': 'inquire', 'label': 'Private inquiry', 'hrv_cost': 3.0},
        {'action': 'rest', 'label': 'Quiet rest', 'hrv_cost': -1.5}]
CLOSED = {'introduction_stage': 'settling', 'available_concepts': ['environment'],
          'forum_open': False, 'peer_messages_open': False, 'share_peer_positions': False}


class OnboardingRuntimeTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.community.return_value = dict(CLOSED)
        self.database = Path(self.tmp) / 'trade_queue.sqlite3'
        self.store = LineageStore(self.database)
        self.positions = self.patch(loop, 'get_cross_agent_positions', return_value={})
        self.patch(loop, 'get_available_actions', return_value=MENU)

    def test_explicit_malformed_wake_ids_fail_before_any_wake_effect(self):
        for bad in ('', False, 0, [], {}, 'bad id', '../escape', 'x' * 129):
            with self.subTest(value=repr(bad)), self.assertRaises(ValueError):
                loop.agent_wake('tempest', wake_id=bad)
        self.llm.assert_not_called()
        self.positions.assert_not_called()
        self.assertEqual(self.memories, {})
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='inquiry_operations'").fetchone()[0], 0)

    def test_direct_inquiry_rejects_explicit_malformed_context_ids_without_receipt_or_model(self):
        for bad in ('', False, 0, [], {}, 'bad id', '../escape', 'x' * 129):
            with self.subTest(value=repr(bad)), self.assertRaises(ValueError):
                self.execute('inquire', agent_id='tempest', context={'wake_id': bad})
        self.llm.assert_not_called()
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='inquiry_operations'").fetchone()[0], 0)

    def test_actual_seven_wakes_share_cohort_but_have_private_owner_records(self):
        cohort = prepare_cohort('offline-arrival', db_path=self.database)
        self.assertEqual(len(cohort['wakes']), 7)
        self.assertEqual(len({w['wake_id'] for w in cohort['wakes']}), 7)
        for wake in cohort['wakes']:
            aid = wake['agent_id']
            self.llm.side_effect = ['1', json.dumps({'operation': 'start', 'title': aid + ' question',
                                                   'observation': 'A supplied observation',
                                                   'interpretation': 'An initial account to revisit'})]
            result = loop.agent_wake(aid, phase=0, wake_id=wake['wake_id'])
            self.assertEqual(result['wake_id'], wake['wake_id'])
            self.assertEqual(result['action'], 'inquire')
            self.assertEqual(result['result']['status'], 'applied')
            self.assertEqual(self.llm.call_count, 2)
            own = self.store.list_inquiries(aid, viewer_agent_id=aid)
            self.assertEqual(own['total'], 1)
            inquiry_id = own['inquiries'][0]['inquiry_id']
            detail = self.store.get_inquiry(inquiry_id, viewer_agent_id=aid)
            self.assertEqual(detail['inquiry']['visibility'], 'owner')
            self.assertEqual(detail['inquiry']['phase'], 0)
            self.assertEqual(len(detail['entries']), 2)
            self.assertEqual(detail['proposals'], [])
            self.assertEqual(detail['orders'], [])
            for peer in loop.AGENTS:
                if peer != aid:
                    with self.assertRaises(LineageAccessError):
                        self.store.get_inquiry(inquiry_id, viewer_agent_id=peer, phase=3)
            self.assertEqual(self.memory(aid).get_recent_episodes(), [])
            self.positions.assert_called_with([aid])
            self.llm.reset_mock()
        replay = prepare_cohort('offline-arrival', db_path=self.database)
        self.assertEqual(cohort['wakes'], replay['wakes'])
        self.assertTrue(replay['replayed'])

    def test_same_logical_wake_recovers_without_picker_broker_new_interpretation_or_message_ack(self):
        wake_id = str(uuid5(NAMESPACE_URL, 'tempest-recovery'))
        self.llm.side_effect = ['1', json.dumps({'operation': 'start', 'title': 'A preserved inquiry',
                                              'interpretation': 'Keep the original account'})]
        first = loop.agent_wake('tempest', wake_id=wake_id)
        listing = self.store.list_inquiries('tempest', viewer_agent_id='tempest')
        iid = listing['inquiries'][0]['inquiry_id']
        before = self.store.get_inquiry(iid, viewer_agent_id='tempest')
        energy = self.hrv.load('tempest').hrv
        self.messages.send('user', 'tempest', 'Arrived after the first operation')
        self.llm.reset_mock()
        self.llm.side_effect = AssertionError('Recovery must not invoke a new model')
        self.positions.reset_mock()
        result = loop.agent_wake('tempest', wake_id=wake_id)
        self.assertEqual(result['choice_status'], 'resumed_inquiry')
        self.assertTrue(result['result']['replayed'])
        self.assertEqual(result['result']['status'], 'applied')
        self.llm.assert_not_called()
        self.positions.assert_not_called()
        self.assertEqual(self.store.get_inquiry(iid, viewer_agent_id='tempest'), before)
        self.assertEqual(self.hrv.load('tempest').hrv, energy)
        self.assertEqual(self.messages.unread_count('tempest'), 1)
        self.assertEqual(result['result']['operation_id'], first['result']['operation_id'])

    def test_same_id_correlates_picker_and_inquiry_model_calls(self):
        logical_id = str(uuid5(NAMESPACE_URL, 'cost-correlated-inquiry'))
        seen = []
        def choose_or_record(*args, **kwargs):
            seen.append(current_usage_context())
            return '1' if len(seen) == 1 else '{"operation":"none"}'
        self.llm.side_effect = choose_or_record
        result = loop.agent_wake('siren', wake_id=logical_id)
        self.assertEqual(result['result']['status'], 'no_change')
        self.assertEqual({item['wake_id'] for item in seen}, {logical_id})
        self.assertEqual([item['activity'] for item in seen], ['choose_action', 'inquire'])
        self.assertEqual(self.store.list_inquiries('siren', viewer_agent_id='siren')['total'], 0)
        self.assertIsNotNone(get_inquiry_receipt('siren', logical_id, db_path=self.database))

    def test_no_change_invalid_and_rest_do_not_create_inquiries_or_force_journals(self):
        for response, status in [('{"operation":"none"}', 'no_change'),
                                 ('{"operation":"order","qty":1}', 'invalid')]:
            self.llm.side_effect = ['1', response]
            result = loop.agent_wake('shadow')
            self.assertEqual(result['result']['status'], status)
            self.assertEqual(self.store.list_inquiries('shadow', viewer_agent_id='shadow')['total'], 0)
            self.assertEqual(self.memory('shadow').get_recent_episodes(), [])
            self.llm.reset_mock()
        self.llm.side_effect = None
        self.llm.return_value = '2'
        result = loop.agent_wake('shadow')
        self.assertEqual(result['action'], 'rest')
        self.assertFalse(result['result']['journal_written'])

    def test_failed_inquiry_does_not_ack_user_message(self):
        self.messages.send('user', 'oracle', 'An invitation, not a task')
        self.llm.side_effect = ['1', 'not JSON']
        result = loop.agent_wake('oracle')
        self.assertEqual(result['result']['status'], 'invalid')
        self.assertEqual(self.messages.unread_count('oracle'), 1)

    def test_forum_open_never_shares_holdings_or_consumes_closed_peer_messages(self):
        self.community.return_value = {**CLOSED, 'forum_open': True}
        self.messages.send('shadow', 'siren', 'Private peer message waiting for opening')
        self.messages.send('user', 'siren', 'Available during adjustment')
        self.llm.side_effect = ['2']
        loop.agent_wake('siren', phase=1)
        self.positions.assert_called_once_with(['siren'])
        context = self.llm.call_args.args[1][0]['content']
        self.assertIn('Available during adjustment', context)
        self.assertNotIn('Private peer message waiting', context)
        self.assertIn('community-invitations/v1', context)
        self.assertEqual(self.messages.unread_count('siren'), 2)

    def test_inquiry_model_sees_owned_evidence_not_journals_peer_holdings_or_messages(self):
        self.memory('weaver').write_journal('PRIVATE_JOURNAL_SENTINEL')
        self.llm.return_value = '{"operation":"none"}'
        result = self.execute('inquire', agent_id='weaver', phase=0, context={
            'messages': [{'content': 'PRIVATE_MESSAGE_SENTINEL'}],
            'positions': {'oracle': {'status': 'ok', 'positions': [{'symbol': 'PEER_SENTINEL'}]},
                          'weaver': {'status': 'ok', 'positions': []}},
            'market_data': {'status': 'not_supplied'},
        })
        self.assertEqual(result['status'], 'no_change')
        content = json.dumps(self.llm.call_args.args[1])
        for forbidden in ['PRIVATE_JOURNAL_SENTINEL', 'PRIVATE_MESSAGE_SENTINEL', 'PEER_SENTINEL']:
            self.assertNotIn(forbidden, content)
        self.assertIn('own_positions', content)

    def test_direct_calls_cannot_bypass_closed_communication_or_collective_analysis(self):
        for aid in loop.AGENTS:
            for action in ('forum_post', 'direct_message', 'analyze_consensus'):
                with self.subTest(agent=aid, action=action):
                    result = self.execute(action, phase=3, agent_id=aid)
                    self.assertEqual(result['status'], 'permission_denied')
        self.llm.assert_not_called()
        self.assertEqual(self.forum.get_recent(), [])
        self.assertTrue(all(self.messages.unread_count(aid) == 0 for aid in loop.AGENTS))


class CommunityMenuTests(OfflineCase):
    def test_closed_policy_retains_rest_roam_inquiry_and_removes_peer_actions(self):
        self.community.return_value = dict(CLOSED)
        for aid in loop.AGENTS:
            seen = set()
            for _ in range(100):
                choices = loop.get_available_actions(aid, 3, self.state(aid))
                actions = {entry['action'] for entry in choices}
                self.assertIn('rest', actions)
                self.assertFalse(actions & {'forum_post', 'direct_message', 'analyze_consensus'})
                seen.update(actions)
            self.assertTrue({'rest', 'roam', 'inquire'} <= seen)
