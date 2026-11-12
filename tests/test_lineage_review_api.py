"""Protect linked review without importing or starting the API application."""
import ast
import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest import mock

from core.trading.lineage import LineageStore
from core.trading.queue import TradeQueue
from scripts.build_lineage_fixture import STRUCTURE
from tests.test_lineage_api import HTTPException

SOURCE = Path(__file__).resolve().parents[1] / 'api' / 'app.py'
TOKEN = 'test-operator-credential'


def handlers(queue):
    names = {'_require_lineage_operator', 'approve_trade', 'reject_trade'}
    nodes = [copy.deepcopy(node) for node in ast.parse(SOURCE.read_text()).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    namespace = {'os': os, 'Optional': Optional, 'HTTPException': HTTPException,
                 'Header': lambda *args, **kwargs: None, 'TradeReviewRequest': SimpleNamespace,
                 'get_trade_queue': lambda: queue}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), 'exec'), namespace)
    return namespace


class LinkedReviewAPI(unittest.TestCase):
    def setUp(self):
        self.queue = mock.Mock(spec=('get_entry', 'approve', 'reject'))
        self.queue.get_entry.return_value = {'lineage_proposal_id': 'private-proposal'}
        self.queue.approve.return_value = True
        self.queue.reject.return_value = True
        self.callables = handlers(self.queue)
        self.enterContext(mock.patch.dict(os.environ, {'LINEAGE_OPERATOR_TOKEN': TOKEN}))
        for target in ('socket.create_connection', 'socket.socket.connect', 'urllib.request.urlopen'):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError('network forbidden')))
            self.addCleanup(guard.assert_not_called)

    def call(self, action='approve', authorization=None, notes=''):
        return self.callables[action + '_trade'](1, SimpleNamespace(notes=notes), authorization=authorization)

    def assert_http(self, status, detail, action='approve', **kwargs):
        with self.assertRaises(HTTPException) as raised:
            self.call(action, **kwargs)
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (status, detail))

    def test_linked_review_cannot_use_missing_wrong_or_client_claimed_authority(self):
        for action in ('approve', 'reject'):
            for authorization in (None, 'Bearer wrong', 'operator', 'Bearer alchemist'):
                self.assert_http(403, 'lineage_operator_required', action, authorization=authorization)
        self.queue.approve.assert_not_called()
        self.queue.reject.assert_not_called()

    def test_linked_review_is_unavailable_without_operator_configuration(self):
        with mock.patch.dict(os.environ, {'LINEAGE_OPERATOR_TOKEN': ''}):
            for action in ('approve', 'reject'):
                self.assert_http(503, 'lineage_operator_unavailable', action, authorization='Bearer ' + TOKEN)
        self.queue.approve.assert_not_called()
        self.queue.reject.assert_not_called()

    def test_linked_review_delegates_only_after_authorization(self):
        for action in ('approve', 'reject'):
            self.assertEqual(self.call(action, authorization='Bearer ' + TOKEN, notes='Explicit review'),
                             {'status': 'approved' if action == 'approve' else 'rejected', 'id': 1})
            getattr(self.queue, action).assert_called_once_with(1, 'Explicit review')

    def test_false_review_is_a_conflict_not_a_success(self):
        for action in ('approve', 'reject'):
            getattr(self.queue, action).return_value = False
            self.assert_http(409, 'trade_review_conflict', action, authorization='Bearer ' + TOKEN)

    def test_linked_notes_are_bounded_before_mutation(self):
        for action in ('approve', 'reject'):
            self.assert_http(400, 'invalid_lineage_review', action, authorization='Bearer ' + TOKEN, notes='x' * 2001)
        self.queue.approve.assert_not_called()
        self.queue.reject.assert_not_called()

    def test_legacy_unlinked_review_permissions_and_missing_id_behavior_are_unchanged(self):
        with mock.patch.dict(os.environ, clear=True):
            for entry in ({'lineage_proposal_id': None}, None):
                self.queue.get_entry.return_value = entry
                for action in ('approve', 'reject'):
                    self.assertEqual(self.call(action, notes='x' * 2001)['id'], 1)

    def test_actual_linked_queue_review_is_private_idempotent_and_never_dispatches(self):
        with TemporaryDirectory() as folder:
            db = Path(folder) / 'trade_queue.sqlite3'
            store = LineageStore(db)
            inquiry = store.create_inquiry('alchemist', 'Private inquiry', operation_key='inquiry')
            proposal = store.create_proposal(inquiry, 'alchemist', STRUCTURE, thesis='Owner-only thesis', operation_key='proposal')
            qid = store.get_proposal(proposal, 'alchemist')['queue_id']
            queue = TradeQueue(str(db))
            self.assertEqual(queue.get_pending(), [])
            routes = handlers(queue)
            request = SimpleNamespace(notes='Explicit operator approval')
            with self.assertRaises(HTTPException):
                routes['approve_trade'](qid, request, authorization=None)
            self.assertEqual(queue.get_entry(qid)['status'], 'pending')
            for _ in range(2):
                self.assertEqual(routes['approve_trade'](qid, request, authorization='Bearer ' + TOKEN)['status'], 'approved')
            detail = store.get_inquiry(inquiry, operator=True)
            self.assertEqual(len([e for e in detail['events'] if e['kind'] == 'proposal_reviewed']), 1)
            self.assertEqual(detail['orders'], [])
            self.assertEqual(detail['fills'], [])
            self.assertEqual(detail['positions'], [])
            self.assertFalse((Path(folder) / 'mock_broker.sqlite3').exists())
            with self.assertRaises(HTTPException) as raised:
                routes['reject_trade'](qid, request, authorization='Bearer ' + TOKEN)
            self.assertEqual(raised.exception.status_code, 409)
            self.assertEqual(queue.get_entry(qid)['status'], 'approved')
