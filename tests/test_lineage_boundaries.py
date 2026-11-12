"""Regression coverage for independent review findings; no app import."""
import ast
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from core.trading.lineage import LineageStore
from core.trading.lineage.errors import LineageAccessError
from core.trading.lifecycle import PaperLifecycle
from core.trading.mock_broker import MockBroker
from core.trading.queue import TradeQueue
from scripts.build_lineage_fixture import STRUCTURE

SOURCE = Path(__file__).resolve().parents[1] / 'api' / 'app.py'


class LineageBoundaries(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection', 'socket.socket.connect', 'urllib.request.urlopen'):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError('network forbidden')))
            self.addCleanup(guard.assert_not_called)

    def test_api_lineage_factory_uses_existing_configured_queue_path_and_stays_lazy(self):
        names = {'get_trade_queue', 'get_lineage_store'}
        nodes = [copy.deepcopy(node) for node in ast.parse(SOURCE.read_text()).body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
        with TemporaryDirectory() as folder:
            resolved = Path(folder) / 'configured-data' / 'trade_queue.sqlite3'
            resolver = mock.Mock(side_effect=lambda name: str(resolved.parent / name))
            queue_factory = mock.Mock(side_effect=lambda path: SimpleNamespace(db_path=path))
            namespace = {'db_path': resolver, 'TradeQueue': queue_factory}
            exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(SOURCE), 'exec'), namespace)
            queue = namespace['get_trade_queue']()
            store = namespace['get_lineage_store']()
            self.assertEqual(store.db_path, queue.db_path)
            self.assertEqual(store.db_path, str(resolved))
            self.assertEqual(resolver.call_args_list, [mock.call('trade_queue.sqlite3'), mock.call('trade_queue.sqlite3')])
            self.assertFalse(resolved.exists(), 'A factory must not initialize the default queue database.')
            inquiry = store.create_inquiry('alchemist', 'Configured-path inquiry', operation_key='configured')
            actual_queue = TradeQueue(queue.db_path)
            proposal = store.create_proposal(inquiry, 'alchemist', STRUCTURE, operation_key='configured-proposal')
            qid = store.get_proposal(proposal, 'alchemist')['queue_id']
            self.assertTrue(actual_queue.approve(qid, 'Explicit operator approval'))
            self.assertEqual(store.get_proposal(proposal, 'alchemist')['review_status'], 'approved')
            self.assertTrue(resolved.exists())

    def test_other_valid_options_contracts_are_not_pilot_execution_authority(self):
        candidates = [
            {**STRUCTURE, 'symbol': 'AAPL270115C00100000', 'underlying': 'AAPL'},
            {**STRUCTURE, 'symbol': 'DEMO270115P00100000', 'option_type': 'put'},
        ]
        for index, structure in enumerate(candidates):
            with self.subTest(symbol=structure['symbol']), TemporaryDirectory() as folder:
                store = LineageStore(Path(folder) / 'trade_queue.sqlite3')
                inquiry = store.create_inquiry('alchemist', 'Optional alternative structure', operation_key='inquiry')
                proposal = store.create_proposal(inquiry, 'alchemist', structure, operation_key='proposal')
                queue = TradeQueue(store.db_path)
                self.assertTrue(queue.approve(store.get_proposal(proposal, 'alchemist')['queue_id']))
                broker = MockBroker(Path(folder) / 'mock_broker.sqlite3')
                service = PaperLifecycle(store, broker)
                with mock.patch.object(broker, 'lookup_order', wraps=broker.lookup_order) as lookup, \
                     mock.patch.object(broker, 'submit_order', wraps=broker.submit_order) as dispatch:
                    with self.assertRaises(LineageAccessError):
                        service.submit(proposal)
                    lookup.assert_not_called()
                    dispatch.assert_not_called()
                self.assertEqual(store.get_inquiry(inquiry, operator=True)['orders'], [])
                self.assertEqual(store.get_inquiry(inquiry, operator=True)['positions'], [])
