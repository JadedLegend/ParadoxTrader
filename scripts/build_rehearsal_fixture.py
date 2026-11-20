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
        from core.memory.compost import CompostStore
        from core.runtime.rehearsal.witness import WitnessStore
        from api.rehearsal import _journal_sources, _witness_account

        store = RehearsalStore(tmp)
        manifest = cli.manifest_for()
        # Serialize only the example's transport so resource snapshots and
        # generated evidence have deterministic order. All seven share a cohort.
        manifest['limits']['max_parallelism'] = 1
        store.prepare(manifest, run_id=RUN_ID)
        path = store.run_path(RUN_ID)
        compost = CompostStore(path / 'memory' / 'tempest.sqlite3', 'tempest')
        seeded = []
        # Explicit scripted pre-existing collection; not claimed as a model turn.
        for index in range(6):
            destination = ('idea', 'orientation', 'trading')[index % 3]
            note = compost.append_note(f'fixture-compost-{index}',
                f'Scripted compost {index + 1}: a question can remain open; this is not a live agent account.',
                channels=[destination], note_kind='compost', source_mode='offline')
            seeded.append(note['id'])
        compost.prepare_distillation('fixture-distillation', seeded)
        compost.apply_distillation('fixture-distillation',
            'Scripted distillation: the questions share a timing concern, while their differences remain open. The originals remain linked.',
            channels=['idea', 'orientation'], release=True, source_mode='offline')
        compost.append_note('fixture-active-return',
            'Scripted active compost: leave room to return to a question without an obligation to resolve it.',
            channels=['orientation'], note_kind='compost', source_mode='offline')
        class CompostExampleHTTP(ScriptedHTTP):
            def __call__(self, *args, **kwargs):
                response = super().__call__(*args, **kwargs)
                messages = kwargs.get('json', {}).get('messages', [])
                text = '\n'.join(str(message.get('content', '')) for message in messages)
                if 'REHEARSAL CHOICE' in text and 'Stable owner ID: siren' in text and self.counts['siren'] == 2:
                    response.payload['choices'][0]['message']['content'] = json.dumps({'action': 'journal', 'journal_mode': 'witness'})
                return response
        transport = OpenRouterTransport('offline-scripted-not-a-credential', http_post=CompostExampleHTTP())
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
                    replacements.setdefault(record_id, str(uuid5(NAMESPACE_URL, f"fixture-inquiry:{job['wake_id']}")))
                    record = LineageStore(path / 'trade_queue.sqlite3').get_inquiry(record_id, viewer_agent_id=owner)
                elif kind in ('journal', 'episode'):
                    memory = ThresholdMemory(str(path / 'memory' / (owner + '.sqlite3')))
                    rows = memory.read_journal(limit=100) if kind == 'journal' else memory.get_recent_episodes(limit=100)
                    record = next(row for row in rows if row['id'] == record_id)
                elif kind == 'library':
                    # The reference names a section, not a room: try writings, then research.
                    try:
                        record = LibraryStore(corpus_path=path / 'library_corpus.json', db_path=path / 'library.sqlite3').read_section(record_id, max_chars=1200)
                    except KeyError:
                        if not (path / 'library_research_corpus.json').exists():
                            raise
                        record = LibraryStore(corpus_path=path / 'library_research_corpus.json',
                                              db_path=path / 'library_research.sqlite3').read_section(record_id, max_chars=1200)
                elif kind == 'witness':
                    record = _witness_account(WitnessStore(path / 'witness.sqlite3').get_account(record_id, owner), owner)
                else:
                    raise AssertionError('Unsupported private fixture record')
                records[f'{owner}|{kind}|{record_id}'] = {'run_id': RUN_ID, 'agent_id': owner, 'kind': kind, 'id': record_id, 'record': record}
        decisions = {job['wake_id']: {'run_id': RUN_ID, 'agent_id': job['agent_id'],
                    'wake_id': job['wake_id'], 'decision': store.get_decision_details(RUN_ID, job['wake_id'])}
                    for job in jobs}
        journal_rows = {}
        for owner in OWNERS:
            memory = CompostStore(path / 'memory' / (owner + '.sqlite3'), owner)
            rows = {}
            for channel in ('trading', 'idea', 'orientation', 'unclassified'):
                for row in memory.list_notes(channel=channel, state='all', limit=20)['notes']:
                    rows[row['id']] = row
            journal_rows[owner] = sorted(rows.values(), key=lambda row: row['id'])
        witness = WitnessStore(path / 'witness.sqlite3')
        witness_rows = {scope: witness.list_accounts(scope, limit=20)['accounts']
                        for scope in (*OWNERS, 'steward')}
        source_headers = {}
        for owner in OWNERS:
            idea, _ = _journal_sources(store, RUN_ID, owner, 'idea', 'all', 20, 0)
            trading, _ = _journal_sources(store, RUN_ID, owner, 'trading', 'all', 20, 0)
            by_id = {row['id']: row for row in (*idea, *trading)}
            source_headers[owner] = list(by_id.values())
        fixture = {'kind': 'fixture', 'observed_at': STAMP,
                   'provenance': 'Scripted temporary stores; serial dispatch, explicit pre-existing scripted compost, normalized IDs/timestamps/hashes. Not real model output.',
                   'runs': [result], 'jobs': {RUN_ID: jobs}, 'requests': {RUN_ID: requests},
                   'records': {RUN_ID: records}, 'decisions': {RUN_ID: decisions},
                   'journals': {RUN_ID: journal_rows}, 'witnesses': {RUN_ID: witness_rows},
                   'sources': {RUN_ID: source_headers}}

        import re
        uuid_pattern = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')

        def register_identifiers(value, address='root'):
            # Register before rewriting so a source ref has the same example ID
            # in the original entry, a quoted input and both private/public refs.
            if isinstance(value, dict):
                for key, item in value.items():
                    stable_key = str(key)
                    for before, after in replacements.items():
                        stable_key = stable_key.replace(before, after)
                    register_identifiers(item, address + '/' + stable_key)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    register_identifiers(item, address + '/' + str(index))
            elif isinstance(value, str):
                for index, identifier in enumerate(uuid_pattern.findall(value)):
                    if identifier != RUN_ID and identifier not in replacements:
                        replacements[identifier] = str(uuid5(NAMESPACE_URL, f'fixture-embedded-id:{address}:{index}'))

        register_identifiers(fixture)

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
                # Quoted request bodies can embed IDs/times inside JSON text.
                for before, after in replacements.items():
                    value = value.replace(before, after)
                import re
                value = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+00:00|Z)', STAMP, value)
            return value
        normalized = normalize(fixture)
        import hashlib
        from core.runtime.rehearsal.provider import bounded_input
        request_metadata = {item['request_id']: item for item in normalized['requests'][RUN_ID]}
        for decision in normalized['decisions'][RUN_ID].values():
            if decision['decision']:
                for request in decision['decision'].get('requests', []):
                    if 'messages' in request:
                        raw = json.dumps(request['messages'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
                        request['input_sha256'] = hashlib.sha256(raw).hexdigest()
                        request['input_bytes'] = bounded_input(request['messages'])
                        request_metadata[request['request_id']]['input_bytes'] = request['input_bytes']
        for accounts in normalized['witnesses'][RUN_ID].values():
            for account in accounts:
                # Explicit synthetic digest after normalizing the source refs.
                snapshot = {key: value for key, value in account.items() if key not in ('source_digest', 'source_facts')}
                account['source_digest'] = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        witness_digests = {account['id']: account['source_digest'] for accounts in normalized['witnesses'][RUN_ID].values() for account in accounts}
        for record in normalized['records'][RUN_ID].values():
            if record['kind'] == 'witness':
                record['record']['source_digest'] = witness_digests[record['id']]
        return normalized


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
