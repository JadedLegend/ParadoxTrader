"""Build public UI examples without services, credentials, models, or broker reads.

Run: python3 scripts/build_ui_fixtures.py [--check]
Network/tracing are blocked before importing runtime menu logic. DATA_DIR is temporary.
Only selected public persona fields and constructed example state are exported.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import random
import socket
import sys
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'frontend/src/preview/fixtures.json'
STAMP = '2026-11-12T00:00:00+00:00'


def build_fixture():
    with TemporaryDirectory(prefix='paradox-ui-fixtures-') as tmp, ExitStack() as stack:
        stack.enter_context(mock.patch.dict(os.environ, {
            'DATA_DIR': tmp, 'LANGCHAIN_TRACING_V2': 'false',
            'LANGSMITH_TRACING': 'false', 'LANGSMITH_TRACING_V2': 'false',
        }))
        for name in ('LANGCHAIN_API_KEY', 'LANGSMITH_API_KEY'):
            os.environ.pop(name, None)
        for target, name in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                             (socket, 'create_connection')):
            stack.enter_context(mock.patch.object(target, name, side_effect=AssertionError('No fixture network')))
        try:
            import requests
        except ImportError:
            pass
        else:
            stack.enter_context(mock.patch.object(requests.sessions.Session, 'request',
                side_effect=AssertionError('No fixture provider calls')))
        sys.path.insert(0, str(ROOT))
        from core.runtime import config
        stack.enter_context(mock.patch.object(config, 'load_config', side_effect=AssertionError('No fixture credentials')))
        from core.runtime import agent_loop as loop
        from core.hrv.engine import AgentHRVState
        stack.enter_context(mock.patch.object(loop, 'call_llm', side_effect=AssertionError('No fixture models')))
        rng = random.getstate()
        stack.callback(random.setstate, rng)
        values = [72.0, 63.0, 84.0, 56.0, 73.0, 61.0, 92.0]
        agents, windows, definitions = [], {}, {}
        for index, aid in enumerate(loop.AGENTS):
            soul = loop.load_soul(aid)
            energy = values[index]
            agents.append({
                'agent_id': aid, 'name': soul['name'],
                'epistemic_role': soul.get('epistemic_role', ''),
                'core_drive': soul.get('core_drive', ''),
                'model': soul.get('model_preference', ''),
                'current_focus': '', 'curiosity_questions': [],
                'hrv': energy, 'max_hrv': 100.0, 'in_interval': False,
                'last_tick_at': None, 'hrv_status': 'ok',
            })
            definitions[aid] = {'self_definition': soul.get('self_definition', ''),
                                'self_definition_history': []}
            windows[aid] = {}
            for phase in (0, 1, 3):
                state = AgentHRVState(aid, hrv=energy, specialty_actions=soul.get('hrv_specialties', []))
                random.seed(1300 + index * 100 + phase)
                choices = loop.get_available_actions(aid, phase, state)
                windows[aid][f'phase{phase}'] = {
                    'phase': phase, 'hrv': energy, 'max_hrv': 100.0,
                    'in_interval': False, 'choices': choices,
                }
            # Interval branch bypasses the picker and all active options.
            windows[aid]['interval'] = {
                'phase': 0, 'hrv': 20.0, 'max_hrv': 100.0,
                'in_interval': True,
                'choices': [{'action': 'rest', 'label': 'Quiet rest — no reflection required', 'hrv_cost': -1.5}],
            }
        positions = {}
        states = ['ok', 'ok', 'not_configured', 'error', 'ok', 'not_configured', 'ok']
        for index, aid in enumerate(loop.AGENTS):
            holdings = ([{'symbol': 'DEMO', 'qty': '2', 'avg_entry_price': '10.00', 'unrealized_pl': '0.00'}]
                        if index == 0 else [])
            positions[aid] = {'status': states[index], 'positions': holdings, 'observed_at': STAMP}
        return {'schema_version': 1, 'kind': 'fixture', 'observed_at': STAMP,
                'agents': agents, 'positions': positions, 'windows': windows, 'definitions': definitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the checked-in fixture is stale.')
    args = parser.parse_args()
    text = json.dumps(build_fixture(), indent=2, ensure_ascii=False) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != text:
            raise SystemExit('UI fixture differs; regenerate with scripts/build_ui_fixtures.py')
        print('UI fixture matches public personas and current offline menu logic.')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(text, encoding='utf-8')
        print(f'Wrote UI examples: {OUTPUT}')


if __name__ == '__main__':
    main()
