"""No services, broad app, actual providers, credentials or external HTTP."""
import asyncio
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from api import rehearsal

ID = '11111111-1111-4111-8111-111111111111'
TOKEN = 'offline-test-operator'
AUTH = 'Bearer ' + TOKEN
OWNERS = sorted(rehearsal.AGENTS)


async def _asgi_request(app, path, authorization=AUTH, method='GET'):
    url, _, query = path.partition('?')
    headers = [] if authorization is None else [(b'authorization', authorization.encode('utf-8'))]
    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'method': method,
             'scheme': 'http', 'path': url, 'raw_path': url.encode(), 'query_string': query.encode(),
             'root_path': '', 'headers': headers, 'client': ('offline-test', 1), 'server': ('offline-test', 80)}
    sent, first = [], True
    async def receive():
        nonlocal first
        if first:
            first = False
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.sleep(3600)
    async def send(message):
        sent.append(message)
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    start = next(message for message in sent if message['type'] == 'http.response.start')
    body = b''.join(message.get('body', b'') for message in sent if message['type'] == 'http.response.body')
    return start['status'], json.loads(body or b'null'), dict(start['headers'])


class RehearsalReadAPI(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp) / 'unopened'
        self.app = rehearsal.create_app(self.root, operator_token=TOKEN)
        self.store = mock.Mock()
        self.factory = self.enterContext(mock.patch.object(rehearsal, '_store', return_value=self.store))
        self.summary = {
            'run_id': ID, 'mode': 'offline', 'status': 'prepared', 'created_at': 'mock-time', 'started_at': None,
            'ended_at': None, 'stop_requested': False, 'limits': {field: '1' if field == 'budget_usd' else 2 for field in rehearsal.LIMIT_FIELDS},
            'agent_models': {owner: 'mock/synthetic-' + owner for owner in OWNERS}, 'request_count': 0,
            'reserved_usd': '0', 'known_cost_usd': '0', 'unknown_cost_requests': 0,
            'agents': [{'agent_id': owner, 'pending': 2, 'completed': 0, 'failed': 0, 'stopped': 0, 'uncertain': 0} for owner in OWNERS],
            'capabilities': ['rest', 'journal', 'inquire', 'library', 'roam'],
        }
        self.store.get_run.return_value = self.summary
        self.store.list_runs.return_value = {'runs': [self.summary], 'total': 1}
        self.job = {'wake_id': 'tempest-round-1', 'agent_id': 'tempest', 'round': 1, 'status': 'completed', 'action': 'rest',
                    'failure_code': None, 'requested_model': 'mock/exact', 'response_model': None, 'provider': None,
                    'request_count': 1, 'duration_ms': 0, 'record_refs': [], 'updated_at': 'mock-time'}
        self.store.list_jobs.return_value = [self.job]
        self.event = {'request_id': 'mock-request', 'wake_id': self.job['wake_id'], 'agent_id': 'tempest', 'activity': 'choice',
                      'model': 'mock/exact', 'outcome': 'unknown', 'duration_ms': None, 'reserved_usd': '0.01',
                      'response_model': None, 'provider': None, 'usage': None}
        self.store.list_requests.return_value = {'events': [self.event], 'total': 1}
        for target in ('socket.create_connection', 'socket.socket.connect', 'urllib.request.urlopen'):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError('external network forbidden')))
            self.addCleanup(guard.assert_not_called)

    def request(self, path='/api/rehearsals', **kwargs):
        return asyncio.run(_asgi_request(self.app, path, **kwargs))

    def test_factory_is_idle_no_startup_or_broad_import(self):
        self.assertFalse(self.root.exists())
        self.factory.assert_not_called()
        self.assertFalse(self.app.router.on_startup)
        self.assertFalse(self.app.router.on_shutdown)
        self.assertEqual([route.methods for route in self.app.routes], [{'GET'}] * 8)
        source = Path(rehearsal.__file__).read_text()
        for forbidden in ('from api.app', 'import api.app', 'from core.runtime.scheduler', 'from core.runtime.agent_loop', 'from core.runtime.rehearsal.provider'):
            self.assertNotIn(forbidden, source)

    def test_auth_precedes_malformed_paths_queries_and_store_construction(self):
        for path in ('/api/rehearsals', '/api/rehearsals/not-uuid/records?agent_id=../../secret', '/api/rehearsals?limit=bogus', '/unknown'):
            for authorization in (None, '', 'operator=true', 'Bearer wrong', AUTH + ' ', AUTH.lower()):
                status, body, _ = self.request(path, authorization=authorization)
                self.assertEqual((status, body), (403, {'detail': 'rehearsal_operator_required'}))
        self.factory.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_unconfigured_token_and_env_fallback(self):
        self.app = rehearsal.create_app(self.root, operator_token='')
        self.assertEqual(self.request()[0], 503)
        self.factory.assert_not_called()
        with mock.patch.dict('os.environ', {'LINEAGE_OPERATOR_TOKEN': TOKEN}):
            self.app = rehearsal.create_app(self.root)
            self.assertEqual(self.request()[0], 200)

    def test_constant_time_auth(self):
        with mock.patch.object(rehearsal.hmac, 'compare_digest', wraps=rehearsal.hmac.compare_digest) as compare:
            self.assertEqual(self.request()[0], 200)
            compare.assert_called_once_with(AUTH.encode(), AUTH.encode())

    def test_no_mutation_or_unprotected_docs_endpoints(self):
        for method in ('POST', 'PATCH', 'DELETE', 'PUT'):
            self.assertEqual(self.request(method=method)[0], 405)
        for path in ('/docs', '/openapi.json', f'/api/rehearsals/{ID}/start', f'/api/rehearsals/{ID}/innermost'):
            self.assertEqual(self.request(path)[0], 404)
        self.factory.assert_not_called()

    def test_reads_are_bounded_enveloped_and_owner_filtered(self):
        status, body, headers = self.request('/api/rehearsals?limit=1&offset=2')
        self.assertEqual(status, 200)
        self.assertEqual(body, {'runs': [self.summary], 'total': 1, 'limit': 1, 'offset': 2})
        self.assertEqual(headers[b'cache-control'], b'private, no-store')
        self.store.list_runs.assert_called_once_with(limit=1, offset=2)
        self.assertEqual(self.request(f'/api/rehearsals/{ID}')[1], self.summary)
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/jobs?agent_id=siren')[1], {'run_id': ID, 'jobs': []})
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/requests?agent_id=tempest&limit=1&offset=4')[0], 200)
        self.store.list_requests.assert_called_once_with(ID, agent_id='tempest', limit=1, offset=4)

    def test_invalid_and_duplicate_queries_never_access_store(self):
        for path in ('/api/rehearsals?limit=0', '/api/rehearsals?limit=21', '/api/rehearsals?offset=-1', '/api/rehearsals?offset=2147483648',
                     '/api/rehearsals?limit=1.5', '/api/rehearsals?limit=%2B1', '/api/rehearsals?limit=1&limit=2', '/api/rehearsals?operator=true',
                     f'/api/rehearsals/{ID}?agent_id=tempest', f'/api/rehearsals/{ID}/requests?limit=51', f'/api/rehearsals/{ID}/records?agent_id=outsider&kind=journal&id=1',
                     f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=innermost&id=1', f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=inquiry&id=not-uuid',
                     '/api/rehearsals?offset=1000001', f'/api/rehearsals/{ID}/requests?offset=1000001'):
            self.assertIn(self.request(path)[0], (400, 404))
        self.factory.assert_not_called()

    def test_operational_metadata_projects_no_content_or_secrets(self):
        for value in (self.summary, self.job, self.event):
            value.update({'raw_output': 'RAW_PRIVATE', 'content': 'PRIVATE_BODY', 'api_key': 'SECRET_KEY', 'innermost': 'INNERMOST'})
        self.job['record_refs'] = [{'kind': 'innermost', 'id': 1}, {'kind': 'journal', 'id': 1, 'content': 'PRIVATE_BODY'}]
        self.event['usage'] = {'cost_usd': '0', 'cost_status': 'reported', 'authorization': 'SECRET_KEY', 'raw_response': 'RAW_PRIVATE'}
        for path in ('/api/rehearsals', f'/api/rehearsals/{ID}', f'/api/rehearsals/{ID}/jobs', f'/api/rehearsals/{ID}/requests'):
            status, body, _ = self.request(path)
            self.assertEqual(status, 200)
            output = json.dumps(body)
            for secret in ('PRIVATE_BODY', 'RAW_PRIVATE', 'SECRET_KEY', 'INNERMOST'):
                self.assertNotIn(secret, output)
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/jobs')[1]['jobs'][0]['record_refs'], [{'kind': 'journal', 'id': 1}])

    def test_wrong_owner_request_adapter_is_not_relabelled(self):
        self.event['agent_id'] = 'siren'
        status, body, _ = self.request(f'/api/rehearsals/{ID}/requests?agent_id=tempest')
        self.assertEqual((status, body), (503, {'detail': 'rehearsal_unavailable'}))

    def test_flat_actual_store_usage_keeps_zero_and_unknown_distinct(self):
        self.event.pop('usage')
        self.event.update(input_tokens=0, output_tokens=0, cost_usd='0', cost_status='reported')
        value = self.request(f'/api/rehearsals/{ID}/requests')[1]['events'][0]
        self.assertEqual(value['usage'], {'input_tokens': 0, 'output_tokens': 0, 'cost_usd': '0', 'cost_status': 'reported'})
        self.event.update(input_tokens=None, output_tokens=None, cost_usd=None, cost_status='unknown')
        value = self.request(f'/api/rehearsals/{ID}/requests')[1]['events'][0]
        self.assertEqual(value['usage']['cost_usd'], None)
        self.assertEqual(value['usage']['cost_status'], 'unknown')

    def memory(self, owner):
        run = Path(self.temp) / ID
        path = run / 'memory' / (owner + '.sqlite3')
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as conn:
            conn.executescript('CREATE TABLE journal(id INTEGER PRIMARY KEY,content TEXT,phase TEXT,created_at TEXT); CREATE TABLE episodes(id INTEGER PRIMARY KEY,title TEXT,content TEXT,phase TEXT,created_at TEXT);')
            conn.execute('INSERT INTO journal VALUES(1,?,?,?)', (owner + ' PRIVATE journal', 'symmetry', 'mock-time'))
            conn.execute('INSERT INTO episodes VALUES(1,?,?,?,?)', ('Owner episode', owner + ' PRIVATE episode', 'symmetry', 'mock-time'))
        self.store.run_path.return_value = run
        return path

    def test_memory_ref_is_run_local_owner_protected_and_read_only(self):
        path = self.memory('tempest')
        self.memory('siren')
        before = path.read_bytes()
        self.job['record_refs'] = [{'kind': 'journal', 'id': 1}, {'kind': 'episode', 'id': 1}]
        for kind in ('journal', 'episode'):
            status, value, _ = self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind={kind}&id=1')
            self.assertEqual(status, 200)
            self.assertEqual(value['record']['content'], 'tempest PRIVATE ' + kind)
            self.assertNotIn('joy_score', value['record'])
            self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=siren&kind={kind}&id=1')[0], 404)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=journal&id=2')[0], 404)

    def test_ref_cannot_escape_owner_memory_via_symlink(self):
        path = self.memory('tempest')
        peer = self.memory('siren')
        path.unlink()
        path.symlink_to(peer)
        self.job['record_refs'] = [{'kind': 'journal', 'id': 1}]
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=journal&id=1')[0], 404)

    def test_sqlite_sidecar_symlink_and_unreferenced_library_are_denied(self):
        path = self.memory('tempest')
        Path(str(path) + '-wal').symlink_to(path)
        self.job['record_refs'] = [{'kind': 'journal', 'id': 1}]
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=journal&id=1')[0], 404)

    def test_library_ref_reads_only_linked_run_local_bounded_source_without_writes(self):
        run = Path(self.temp) / ID
        run.mkdir()
        path = run / 'library.sqlite3'
        section_id = 'doc-123456789abc-s00001'
        with sqlite3.connect(path) as conn:
            conn.execute('CREATE TABLE library_sections(section_id TEXT,document_id TEXT,locator TEXT,text TEXT)')
            conn.execute('INSERT INTO library_sections VALUES(?,?,?,?)', (section_id, 'doc-123456789abc', 'Mock source', 'x' * 2000))
        self.store.run_path.return_value = run
        self.job['record_refs'] = [{'kind': 'library', 'id': section_id}]
        before = path.read_bytes()
        route = f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=library&id={section_id}'
        status, value, _ = self.request(route)
        self.assertEqual(status, 200)
        self.assertEqual(len(value['record']['text']), 1200)
        self.assertTrue(value['record']['truncated'])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.request(route.replace('agent_id=tempest', 'agent_id=siren'))[0], 404)
        self.job['record_refs'] = []
        self.assertEqual(self.request(route)[0], 404)

    def test_library_ref_to_a_research_section_reads_the_research_shelf(self):
        run = Path(self.temp) / ID
        run.mkdir()
        writings, research = 'doc-123456789abc-s00001', 'doc-abcdef123456-s00001'
        for name, section_id, text in (('library.sqlite3', writings, 'writing'), ('library_research.sqlite3', research, 'note')):
            with sqlite3.connect(run / name) as conn:
                conn.execute('CREATE TABLE library_sections(section_id TEXT,document_id TEXT,locator TEXT,text TEXT)')
                conn.execute('INSERT INTO library_sections VALUES(?,?,?,?)', (section_id, section_id[:16], 'Mock source', text))
        self.store.run_path.return_value = run
        self.job['record_refs'] = [{'kind': 'library', 'id': writings}, {'kind': 'library', 'id': research}]
        for section_id, text in ((writings, 'writing'), (research, 'note')):
            status, value, _ = self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=library&id={section_id}')
            self.assertEqual((status, value['record']['text']), (200, text))
        (run / 'library_research.sqlite3').unlink()  # A run from before the rooms has no research shelf.
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=library&id={research}')[0], 404)

    def test_inquiry_uuid_uses_existing_lineage_owner_check_without_schema_writes(self):
        from core.trading.lineage import LineageStore
        run = Path(self.temp) / ID
        run.mkdir()
        path = run / 'trade_queue.sqlite3'
        lineage = LineageStore(path)
        inquiry = lineage.create_inquiry('tempest', 'Optional private inquiry', operation_key='offline-create')
        lineage.add_entry(inquiry, 'tempest', 'observation', 'Private observation', operation_key='offline-note')
        before = path.read_bytes()
        self.store.run_path.return_value = run
        self.job['record_refs'] = [{'kind': 'inquiry', 'id': inquiry}]
        status, value, _ = self.request(f'/api/rehearsals/{ID}/records?agent_id=tempest&kind=inquiry&id={inquiry}')
        self.assertEqual(status, 200)
        self.assertEqual(value['record']['inquiry']['agent_id'], 'tempest')
        self.assertEqual(value['record']['entries'][0]['content'], 'Private observation')
        self.assertEqual(path.read_bytes(), before)
        # Even a bad cross-owner reference must not widen the LineageStore gate.
        self.job['agent_id'] = 'siren'
        self.assertEqual(self.request(f'/api/rehearsals/{ID}/records?agent_id=siren&kind=inquiry&id={inquiry}')[0], 404)

    def test_backend_errors_do_not_echo_paths_keys_or_outputs(self):
        self.store.list_runs.side_effect = RuntimeError('/private/path SECRET_KEY RAW_PRIVATE')
        self.assertEqual(self.request()[:2], (503, {'detail': 'rehearsal_unavailable'}))


class RehearsalActualStoreAPI(unittest.TestCase):
    def test_idle_actual_store_reads_never_import_provider_or_scheduler(self):
        try:
            importlib.import_module('core.runtime.rehearsal.store')
        except ModuleNotFoundError:
            self.skipTest('Parallel-owned actual rehearsal store not available yet')
        from core.runtime.rehearsal.store import RehearsalStore
        owners = sorted(rehearsal.AGENTS)
        manifest = {'schema_version': 1, 'mode': 'offline', 'agent_models': {a: 'mock/' + a for a in owners},
                    'limits': {'wakes_per_agent': 2, 'max_requests': 28, 'max_output_tokens': 1024, 'max_input_bytes': 24000,
                               'max_runtime_seconds': 900, 'request_timeout_seconds': 60, 'max_parallelism': 3, 'budget_usd': '1'},
                    'catalog_snapshot': {'source': 'synthetic', 'models': [{'id': 'mock/' + a, 'context_length': 32000, 'max_completion_tokens': 1024,
                       'supported_parameters': ['max_tokens'], 'pricing': {'prompt': '0', 'completion': '0', 'request': '0'}} for a in owners]},
                    'capabilities': ['rest', 'journal', 'inquire', 'library', 'roam']}
        with tempfile.TemporaryDirectory() as root:
            store = RehearsalStore(root)
            summary = store.prepare(manifest, run_id=ID)
            app = rehearsal.create_app(root, operator_token=TOKEN)
            for target in ('socket.create_connection', 'socket.socket.connect'):
                with mock.patch(target, side_effect=AssertionError('network forbidden')):
                    status, body, _ = asyncio.run(_asgi_request(app, f'/api/rehearsals/{ID}'))
                    self.assertEqual(status, 200)
                    self.assertEqual(body['run_id'], summary['run_id'])
                    status, body, _ = asyncio.run(_asgi_request(app, f'/api/rehearsals/{ID}/jobs'))
                    self.assertEqual(status, 200)
                    self.assertEqual(len(body['jobs']), 14)
                    self.assertTrue(all(job['status'] == 'pending' for job in body['jobs']))


if __name__ == '__main__':
    unittest.main()
