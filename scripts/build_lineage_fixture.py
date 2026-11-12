#!/usr/bin/env python3
"""Build a local mock history from the real lifecycle; never open live stores."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from unittest import mock
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
OUTPUT = REPO_ROOT / 'frontend' / 'src' / 'lineage' / 'fixture.json'
AGENT = 'alchemist'
STRUCTURE = {
    'symbol': 'DEMO270115C00100000', 'underlying': 'DEMO',
    'expiry': '2027-01-15', 'option_type': 'call', 'strike': '100',
    'side': 'buy', 'intent': 'open', 'qty': 2, 'order_type': 'limit',
    'limit_price': '2.50', 'multiplier': 100,
}


def build_fixture():
    from core.trading.lineage import LineageStore
    from core.trading.queue import TradeQueue
    from core.trading.mock_broker import MockBroker
    from core.trading.lifecycle import PaperLifecycle

    rng = random.Random(1987)
    def fixed_uuid():
        return UUID(int=rng.getrandbits(128), version=4)

    class Clock(datetime):
        counter = 0
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=cls.counter)
            cls.counter += 1
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    with TemporaryDirectory(prefix='paradox-lineage-fixture-') as folder, ExitStack() as patches:
        # Patch only these offline modules' clock/UUID aliases, not global agent
        # state or the process's real credentials/configuration.
        modules = [module for name, module in list(sys.modules.items()) if
            name in {'core.trading.queue', 'core.trading.mock_broker', 'core.trading.lifecycle'}
            or name.startswith('core.trading.lineage')]
        for module in modules:
            if getattr(module, 'datetime', None) is datetime:
                patches.enter_context(mock.patch.object(module, 'datetime', Clock))
            if hasattr(module, 'uuid4'):
                patches.enter_context(mock.patch.object(module, 'uuid4', side_effect=fixed_uuid))
            if callable(getattr(module, '_id', None)):
                patches.enter_context(mock.patch.object(module, '_id', side_effect=lambda: str(fixed_uuid())))
        db = Path(folder) / 'trade_queue.sqlite3'
        broker_db = Path(folder) / 'mock_broker.sqlite3'
        store = LineageStore(db)
        broker = MockBroker(broker_db)
        lifecycle = PaperLifecycle(store, broker)

        inquiry = store.create_inquiry(AGENT, 'A timing question, followed through', operation_key='demo-inquiry')
        store.add_entry(inquiry, AGENT, 'observation',
            'Fictional scenario: two accounts disagree about the useful horizon for an options premium.',
            source='operator', operation_key='demo-observation')
        store.add_entry(inquiry, AGENT, 'interpretation',
            'Compare a timing explanation with a volatility explanation; leave both available for further inquiry.',
            operation_key='demo-interpretation')
        proposal = store.create_proposal(inquiry, AGENT, STRUCTURE,
            thesis='Optional mock structure to test execution continuity for this inquiry.',
            horizon='Fictional short-term scenario', uncertainty='No live quote or contract lookup is supplied.',
            operation_key='demo-opening-proposal')
        queue = TradeQueue(str(db))
        assert queue.approve(store.get_proposal(proposal, AGENT)['queue_id'], 'Explicit operator mock approval')
        broker.fail_after_accept_once = True
        opening = lifecycle.submit(proposal)
        assert opening['status'] == 'submission_unknown'
        client_id = opening['client_order_id']
        # Restart after the ambiguous broker acknowledgement: same stable ID.
        store = LineageStore(db)
        broker = MockBroker(broker_db)
        lifecycle = PaperLifecycle(store, broker)
        opening = lifecycle.reconcile(opening['order_id'])
        assert opening['client_order_id'] == client_id and opening['status'] == 'accepted'
        broker.fill_order(client_id, 1, '2.40')
        opening = lifecycle.reconcile(opening['order_id'])
        assert opening['status'] == 'partially_filled' and opening['filled_qty'] == 1
        # Restart once more while partially filled.
        store = LineageStore(db)
        broker = MockBroker(broker_db)
        lifecycle = PaperLifecycle(store, broker)
        broker.fill_order(client_id, 1, '2.50')
        opening = lifecycle.reconcile(opening['order_id'])
        assert opening['status'] == 'filled' and opening['filled_qty'] == 2

        close_structure = {**STRUCTURE, 'side': 'sell', 'intent': 'close', 'limit_price': '2.70'}
        closing_proposal = store.create_proposal(inquiry, AGENT, close_structure,
            thesis='An explicit mock exit structure, separate from the original interpretation.',
            horizon='Mock lifecycle completion', uncertainty='Fees and market marks remain unavailable.',
            operation_key='demo-closing-proposal')
        assert queue.approve(store.get_proposal(closing_proposal, AGENT)['queue_id'], 'Explicit operator mock close approval')
        closing = lifecycle.submit(closing_proposal)
        broker.fill_order(closing['client_order_id'], 1, '2.70')
        closing = lifecycle.reconcile(closing['order_id'])
        broker.fill_order(closing['client_order_id'], 1, '2.70')
        closing = lifecycle.reconcile(closing['order_id'])
        assert closing['status'] == 'filled'
        detail = store.get_inquiry(inquiry, operator=True)
        position = detail['positions'][0]
        assert position['qty'] == 0 and position['status'] == 'closed'
        store.add_review(inquiry, AGENT,
            'The mock execution sequence is complete. Continue investigating the horizon question using new evidence when it becomes available.',
            proposal_id=closing_proposal, order_id=closing['order_id'], position_id=position['position_id'],
            operation_key='demo-optional-review')

        waiting = store.create_inquiry(AGENT, 'Wait for a clearer horizon', operation_key='waiting-inquiry')
        store.add_entry(waiting, AGENT, 'interpretation', 'Keep this question open while choosing whether further investigation would help.',
            operation_key='waiting-note')
        paused = store.create_inquiry(AGENT, 'Liquidity question — paused', operation_key='paused-inquiry')
        store.set_inquiry_state(paused, AGENT, 'paused', reason='Return when relevant evidence is available.', operation_key='pause')
        revisited = store.create_inquiry(AGENT, 'An alternative explanation, revisited', operation_key='revisited-inquiry')
        store.add_entry(revisited, AGENT, 'interpretation', 'A prior account remains available alongside a later alternative.', operation_key='old-account')
        store.set_inquiry_state(revisited, AGENT, 'abandoned', reason='Set aside for now.', operation_key='abandon')
        store.set_inquiry_state(revisited, AGENT, 'open', reason='A new question made this worth revisiting.', operation_key='revisit')
        store.add_entry(revisited, AGENT, 'interpretation', 'Revisit the assumptions without requiring a synthesis or trade.', operation_key='new-account')

        listing = store.list_inquiries(AGENT, operator=True)
        details = {item['inquiry_id']: store.get_inquiry(item['inquiry_id'], operator=True) for item in listing['inquiries']}
        assert len(details) == 4
        assert all(not value['orders'] and not value['proposals'] for key, value in details.items() if key != inquiry)
        return {'mode': 'mock_demo', 'agent_id': AGENT, 'list': listing, 'details': details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify reproducibility without writing output')
    args = parser.parse_args()
    data = json.dumps(build_fixture(), ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != data:
            raise SystemExit('Lineage fixture differs from the current offline lifecycle.')
        print('Lineage fixture matches the actual temporary one-agent mock lifecycle.')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(data)
        print('Generated one-agent mock lifecycle fixture: ' + str(OUTPUT))


if __name__ == '__main__':
    main()
