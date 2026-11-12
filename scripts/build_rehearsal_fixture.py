#!/usr/bin/env python3
"""Build deterministic actual-controller OFFLINE examples; no real run is read."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from unittest import mock
from uuid import UUID, NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / 'frontend' / 'src' / 'rehearsal' / 'fixture.json'
RUN_ID = '88888888-8888-4888-8888-888888888888'
STAMP = '2026-11-12T00:00:00+00:00'
_spec = importlib.util.spec_from_file_location('fixture_rehearsal_cli', ROOT / 'scripts' / 'rehearsal.py')
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def build_fixture():
    with TemporaryDirectory(prefix='paradox-rehearsal-fixture-') as tmp, ExitStack() as blocked:
        for target, name in [(socket, 'create_connection'), (socket.socket, 'connect'), (socket.socket, 'connect_ex')]:
            blocked.enter_context(mock.patch.object(target, name, side_effect=AssertionError('Fixture networking forbidden')))
        from core.runtime.rehearsal.store import RehearsalStore
        from core.runtime.rehearsal.controller import RehearsalController
        from core.runtime.rehearsal.provider import OpenRouterTransport
        from core.runtime.rehearsal.examples import ScriptedHTTP, OWNERS
        from core.memory.engine import ThresholdMemory
        from core.trading.lineage import LineageStore
        from core.library.store import LibraryStore

        store = RehearsalStore(tmp)
        store.prepare(cli.manifest_for(), run_id=RUN_ID)
        transport = OpenRouterTransport('offline-scripted-not-a-credential', http_post=ScriptedHTTP())
        result = RehearsalController(store, RUN_ID, transport=transport, repo_root=ROOT).run()
        if result['status'] != 'completed':
            problems = [(job['agent_id'], job['round'], job['status'], job['failure_code'])
                        for job in store.list_jobs(RUN_ID) if job['status'] != 'completed']
            raise AssertionError('Offline fixture must complete actual two-round controller: ' + repr(problems))
        path = store.run_path(RUN_ID)
        jobs = sorted(store.list_jobs(RUN_ID), key=lambda job: (OWNERS.index(job['agent_id']), job['round']))
        requests = store.list_requests(RUN_ID, limit=100)['events']
        job_map = {job['wake_id']: job for job in jobs}
        requests.sort(key=lambda request: (OWNERS.index(request['agent_id']), job_map[request['wake_id']]['round'], request['activity'] != 'choice', request['activity']))
        replacements = {}
        for request in requests:
            if request.get('request_id'):
                replacements[request['request_id']] = str(uuid5(NAMESPACE_URL, f"fixture-request:{request['wake_id']}:{request['activity']}"))
        records = {}
        for job in jobs:
            owner = job['agent_id']
            for reference in job['record_refs']:
                kind, record_id = reference['kind'], reference['id']
                if kind == 'inquiry':
                    replacements[record_id] = str(uuid5(NAMESPACE_URL, f"fixture-inquiry:{job['wake_id']}"))
                    record = LineageStore(path / 'trade_queue.sqlite3').get_inquiry(record_id, viewer_agent_id=owner)
                elif kind in ('journal', 'episode'):
                    memory = ThresholdMemory(str(path / 'memory' / (owner + '.sqlite3')))
                    rows = memory.read_journal(limit=100) if kind == 'journal' else memory.get_recent_episodes(limit=100)
                    record = next(row for row in rows if row['id'] == record_id)
                elif kind == 'library':
                    record = LibraryStore(corpus_path=path / 'library_corpus.json', db_path=path / 'library.sqlite3').read_section(record_id, max_chars=1200)
                else:
                    raise AssertionError('Unsupported private fixture record')
                records[f'{owner}|{kind}|{record_id}'] = {'run_id': RUN_ID, 'agent_id': owner, 'kind': kind, 'id': record_id, 'record': record}
        fixture = {'kind': 'fixture', 'observed_at': STAMP,
                   'runs': [result], 'jobs': {RUN_ID: jobs}, 'requests': {RUN_ID: requests}, 'records': {RUN_ID: records}}

        def normalize(value, address='root', key=None):
            if isinstance(value, dict):
                pairs = []
                for name, content in value.items():
                    renamed = str(name)
                    for before, after in replacements.items():
                        renamed = renamed.replace(before, after)
                    pairs.append((renamed, content))
                return {name: normalize(content, address + '/' + name, name) for name, content in sorted(pairs)}
            if isinstance(value, list):
                return [normalize(content, address + '/' + str(index), key) for index, content in enumerate(value)]
            if key in ('duration_ms',):
                return 0
            if isinstance(value, str):
                if key and (key.endswith('_at') or key in ('arrival_at',)):
                    return STAMP
                if value in replacements:
                    return replacements[value]
                if value != RUN_ID:
                    try:
                        UUID(value)
                    except ValueError:
                        pass
                    else:
                        replacements[value] = str(uuid5(NAMESPACE_URL, 'fixture-id:' + address))
                        return replacements[value]
            return value
        return normalize(fixture)


def main():
    fixture = build_fixture()
    if '--check' in sys.argv:
        if json.loads(OUTPUT.read_text(encoding='utf-8')) != fixture:
            raise SystemExit('Rehearsal fixture is stale; rebuild from scripted temporary controller.')
        print('Rehearsal fixture matches the actual two-round offline controller.')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
        print('Generated isolated, explicitly scripted seven-owner rehearsal examples.')


if __name__ == '__main__':
    main()
