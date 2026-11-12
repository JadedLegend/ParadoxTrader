#!/usr/bin/env python3
"""Finite seven-owner arrival rehearsal, with scripted choices and temporary stores.

This does not launch actual agents, load accounts, call a model, start timers,
create journals, or prepare/submit orders. No persistent default data is touched.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def rehearse():
    with TemporaryDirectory(prefix='paradox-arrival-rehearsal-') as folder, ExitStack() as guards:
        blocked = []
        for target, name in ((socket, 'create_connection'), (socket.socket, 'connect'), (socket.socket, 'connect_ex')):
            blocked.append(guards.enter_context(mock.patch.object(target, name, side_effect=AssertionError('Offline rehearsal forbids networking'))))
        from core.runtime.cohort import prepare_cohort
        from core.runtime.inquiry import run_inquiry
        from core.trading.lineage import LineageStore
        db = Path(folder) / 'trade_queue.sqlite3'
        cohort = prepare_cohort('offline-arrival-example', db_path=db)
        store = LineageStore(db)

        def one(wake):
            aid = wake['agent_id']
            # One member leaves no inquiry; participation is not compulsory.
            choice = ({'operation': 'none'} if aid == 'oracle' else {
                'operation': 'start', 'title': 'A question I might return to',
                'interpretation': 'This is a scripted local example, not an agent-authored plan.',
            })
            def scripted_model(_messages):
                return json.dumps(choice)
            first = run_inquiry(aid, wake['operation_id'], db_path=db, phase=0, model_call=scripted_model)
            def no_repeat(_messages):
                raise AssertionError('A committed receipt must not request a second interpretation')
            second = run_inquiry(aid, wake['operation_id'], db_path=db, phase=0, model_call=no_repeat)
            assert first['status'] == second['status'] and second['replayed']
            own = store.list_inquiries(aid, viewer_agent_id=aid)
            return {'agent_id': aid, 'wake_id': wake['wake_id'], 'cohort_id': wake['cohort_id'],
                    'status': first['status'], 'private_inquiries': own['total'], 'recovery_replayed': second['replayed']}

        # All seven belong to one arrival marker; concurrency bounds do not give
        # any member a separate onboarding head start or a live execution right.
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(one, cohort['wakes']))
        assert len(results) == 7 and len({r['wake_id'] for r in results}) == 7
        assert len({r['cohort_id'] for r in results}) == 1
        assert all(result['recovery_replayed'] for result in results)
        for guard in blocked:
            guard.assert_not_called()
        return {'mode': 'offline_scripted_rehearsal', 'cohort_status': cohort['status'],
                'providers_called': False, 'live_agents_started': False, 'timers_started': False,
                'orders_created': False, 'results': results}


if __name__ == '__main__':
    print(json.dumps(rehearse(), indent=2))
