"""Actual private temporary stores; no model, services, secrets or external HTTP."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from api import rehearsal
from core.memory.compost import CompostStore
from core.memory.engine import ThresholdMemory
from core.runtime.rehearsal.store import RehearsalStore
from core.runtime.rehearsal.witness import WitnessStore
from core.trading.lineage import LineageStore
from tests.test_rehearsal_api import _asgi_request, AUTH, TOKEN, ID
from tests.test_rehearsal_store import synthetic_manifest


class CompostReadAPI(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp) / 'runs'
        self.store = RehearsalStore(self.root)
        self.store.prepare(synthetic_manifest(), run_id=ID)
        self.app = rehearsal.create_app(self.root, operator_token=TOKEN)
        for target in ('socket.create_connection', 'socket.socket.connect', 'urllib.request.urlopen'):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError('network forbidden')))
            self.addCleanup(guard.assert_not_called)

    def request(self, suffix, **kwargs):
        return asyncio.run(_asgi_request(self.app, f'/api/rehearsals/{ID}/{suffix}', **kwargs))

    def compost(self, owner='tempest'):
        return CompostStore(self.store.safe_run_file(ID, f'memory/{owner}.sqlite3'), owner)

    def collect(self, owner='tempest'):
        store = self.compost(owner)
        original = '<script>literal source</script>\nUnresolved material stays literal.'
        first = store.append_note('note-1', original, channels=['idea', 'orientation'], note_kind='compost', source_mode='offline', source_wake_id=f'{owner}-r1')['id']
        second = store.append_note('note-2', owner + ' second source', channels=['trading'], note_kind='compost', source_mode='offline')['id']
        store.prepare_distillation('digest', [first, second])
        digest = store.apply_distillation('digest', owner + ' chosen distillation', channels=['idea', 'orientation'], release=True, source_mode='offline', source_wake_id=f'{owner}-r2')['id']
        return first, second, digest, original

    def witness(self, scope):
        return WitnessStore(self.store.safe_run_file(ID, 'witness.sqlite3')).record(
            self.store.get_witness_snapshot(ID, None if scope == 'steward' else scope),
            scope=scope, operation_key='account-' + scope)

    def test_authentication_precedes_parse_and_all_store_io(self):
        with mock.patch.object(rehearsal, '_store', side_effect=AssertionError('must authenticate first')) as factory:
            for path in ('journals?agent_id=../../siren&note_id=bad', 'witness?limit=99', 'journals?agent_id=tempest&agent_id=siren'):
                status, body, _ = self.request(path, authorization=None)
                self.assertEqual((status, body), (403, {'detail': 'rehearsal_operator_required'}))
            factory.assert_not_called()
        self.assertFalse((self.root / ID / 'witness.sqlite3').exists())
        self.assertFalse((self.root / ID / 'memory' / 'tempest.sqlite3').exists())

    def test_unknown_duplicate_malformed_and_peer_queries_fail_before_io(self):
        with mock.patch.object(rehearsal, '_store', side_effect=AssertionError('invalid query reached IO')) as factory:
            for path in ('journals', 'journals?agent_id=outsider', 'journals?agent_id=tempest&agent_id=siren',
                         'journals?agent_id=tempest&channel=innermost', 'journals?agent_id=tempest&source_mode=offline',
                         'journals?agent_id=tempest&limit=21', 'journals?agent_id=tempest&limit=0',
                         'journals?agent_id=tempest&offset=10001', 'journals?agent_id=tempest&note_id=0',
                         'journals?agent_id=tempest&note_id=1&note_id=2', 'journals?agent_id=tempest&state=published',
                         'witness?agent_id=steward', 'witness?operator=true', 'witness?limit=3&limit=4',
                         'witness?offset=-1', 'witness?offset=10001', 'witness?account_id=1'):
                self.assertIn(self.request(path)[0], (400, 404), path)
            factory.assert_not_called()

    def test_private_sources_distillation_and_released_original_are_preserved(self):
        first, second, digest, original = self.collect()
        status, value, headers = self.request('journals?agent_id=tempest&channel=idea&state=active')
        self.assertEqual(status, 200)
        self.assertEqual([note['id'] for note in value['notes']], [digest])
        self.assertEqual(value['notes'][0]['source_ids'], [first, second])
        self.assertEqual(headers[b'cache-control'], b'private, no-store')
        archived = self.request('journals?agent_id=tempest&channel=idea&state=released')[1]
        self.assertEqual([note['id'] for note in archived['notes']], [first])
        detail = self.request(f'journals?agent_id=tempest&channel=trading&state=active&note_id={first}')[1]
        self.assertEqual(detail['note']['content'], original)
        self.assertEqual(detail['note']['state'], 'released')
        self.assertEqual(detail['note']['author'], 'tempest')
        self.assertEqual(detail['note']['source_wake_id'], 'tempest-r1')
        self.assertEqual(detail['notes'], [])
        self.assertNotIn('innermost', json.dumps(detail))

    def test_owner_integer_collisions_never_relabel_or_read_another_memory(self):
        self.collect('tempest')
        first = self.compost('siren').append_note('own', 'SIREN private literal', channels=['idea'], source_mode='offline')['id']
        self.assertEqual(first, 1)
        value = self.request('journals?agent_id=siren&channel=idea&note_id=1')[1]
        self.assertEqual(value['note']['content'], 'SIREN private literal')
        self.assertNotIn('tempest', json.dumps(value))
        self.assertEqual(self.request('journals?agent_id=siren&note_id=3')[0], 404)

    def test_missing_and_legacy_reads_create_and_migrate_nothing(self):
        path = self.store.safe_run_file(ID, 'memory/tempest.sqlite3')
        self.assertEqual(self.request('journals?agent_id=tempest')[1]['status'], 'missing')
        self.assertEqual(self.request('witness')[1]['status'], 'missing')
        self.assertFalse(path.exists())
        memory = ThresholdMemory(str(path))
        memory.write_journal('Older freeform literal')
        memory.write_innermost('NOT A JOURNAL SOURCE')
        before = path.read_bytes()
        value = self.request('journals?agent_id=tempest')[1]
        self.assertEqual(value['status'], 'ok')
        self.assertEqual(value['notes'][0]['channels'], ['unclassified'])
        self.assertIsNone(value['notes'][0]['source_mode'])
        self.assertNotIn('NOT A JOURNAL SOURCE', json.dumps(value))
        self.assertEqual(self.request('journals?agent_id=tempest&channel=idea')[1]['notes'], [])
        self.assertEqual(path.read_bytes(), before)
        with sqlite3.connect(path) as conn:
            self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'compost_%' LIMIT 1").fetchone())

    def test_witness_owner_and_steward_are_separate_authenticated_scopes(self):
        owner = self.witness('tempest')
        self.witness('siren')
        steward = self.witness('steward')
        value = self.request('witness?agent_id=tempest')[1]
        self.assertEqual(value['scope'], 'tempest')
        self.assertEqual(value['accounts'][0]['id'], owner['id'])
        self.assertNotIn('siren', json.dumps(value))
        self.assertNotIn(steward['id'], json.dumps(value))
        broad = self.request('witness?limit=1')[1]
        self.assertEqual(broad['scope'], 'steward')
        self.assertEqual(broad['accounts'][0]['id'], steward['id'])
        self.assertEqual(self.request('witness', authorization='Bearer wrong')[0], 403)
        self.assertEqual(self.request('witness?agent_id=oracle')[1]['accounts'], [])

    def test_witness_read_job_projects_only_mode_channels_and_linked_private_reference(self):
        account = self.witness('tempest')
        steward = self.witness('steward')
        token = self.store.begin(ID)
        self.store.claim_job(ID, 'tempest-r1', token)
        self.store.commit_choice(ID, 'tempest-r1', token, {'action': 'journal', 'journal_mode': 'witness'})
        self.store.finish_job(ID, 'tempest-r1', token, action='journal', record_refs=[{'kind': 'witness', 'id': account['id']}])
        public = self.request('jobs?agent_id=tempest')[1]['jobs'][0]
        self.assertEqual(public['journal_mode'], 'witness')
        self.assertNotIn('channels', public)
        self.assertEqual(public['record_refs'], [{'kind': 'witness', 'id': account['id']}])
        self.assertNotIn(account['content'], json.dumps(public))
        for field in ('choice', 'source_ids', 'output', 'private_context'):
            self.assertNotIn(field, public)
        private = self.request(f"records?agent_id=tempest&kind=witness&id={account['id']}")
        self.assertEqual(private[0], 200)
        safe_fields = ('id', 'scope', 'content', 'source_refs', 'source_digest', 'author', 'method', 'created_at')
        self.assertEqual(private[1]['record'], {key: account[key] for key in safe_fields})
        self.assertNotIn('source_facts', private[1]['record'])
        self.assertEqual(self.request(f"records?agent_id=siren&kind=witness&id={account['id']}")[0], 404)
        self.assertEqual(self.request(f"records?agent_id=tempest&kind=witness&id={steward['id']}")[0], 404)
        self.store.claim_job(ID, 'tempest-r2', token)
        self.store.commit_choice(ID, 'tempest-r2', token, {'action': 'journal', 'journal_mode': 'compost', 'channels': ['idea']})
        self.store.finish_job(ID, 'tempest-r2', token, action='journal')
        second = self.request('jobs?agent_id=tempest')[1]['jobs'][1]
        self.assertEqual(second['journal_mode'], 'compost')
        self.assertEqual(second['channels'], ['idea'])
        bad = {**public, 'channels': ['idea', 'innermost'], 'journal_mode': 'arbitrary',
               'choice': {'source_ids': [1]}, 'source_ids': [1],
               'record_refs': [{'kind': 'witness', 'id': account['id'], 'agent_id': 'siren', 'content': 'PEER PRIVATE'}]}
        projected = rehearsal._job(bad)
        self.assertNotIn('journal_mode', projected)
        self.assertNotIn('channels', projected)
        self.assertEqual(projected['record_refs'], [])
        self.assertNotIn('PEER PRIVATE', json.dumps(projected))

    def test_bounded_pagination_and_safe_exact_projections(self):
        for index in range(23):
            self.compost().append_note(str(index), 'note ' + str(index), channels=['orientation'], source_mode='offline')
        page = self.request('journals?agent_id=tempest&channel=orientation&limit=2&offset=20')[1]
        self.assertEqual(page['total'], 23)
        self.assertEqual(len(page['notes']), 2)
        self.assertEqual(self.request('journals?agent_id=tempest&channel=orientation&offset=10000')[1]['notes'], [])
        actual = self.compost().list_notes(channel='orientation', limit=1)
        actual['notes'][0].update(api_key='FORBIDDEN', innermost='FORBIDDEN', source_links=[{'content': 'FORBIDDEN'}])
        with mock.patch.object(CompostStore, 'list_notes', return_value=actual):
            value = self.request('journals?agent_id=tempest&channel=orientation&limit=1')[1]
            self.assertNotIn('FORBIDDEN', json.dumps(value))
        for field, malicious in [('author', 'siren'), ('agent_id', 'siren'), ('source_mode', 'pretend'), ('source_wake_id', 'siren-r1')]:
            poisoned = json.loads(json.dumps(actual))
            poisoned['notes'][0][field] = malicious
            with mock.patch.object(CompostStore, 'list_notes', return_value=poisoned):
                self.assertEqual(self.request('journals?agent_id=tempest&channel=orientation&limit=1')[0], 503)

    def test_lineage_headers_are_owned_linked_bounded_and_not_execution_copies(self):
        lineage = LineageStore(self.store.safe_run_file(ID, 'trade_queue.sqlite3'))
        linked = lineage.create_inquiry('tempest', '<b>Literal inquiry title</b>', operation_key='linked')
        lineage.create_inquiry('tempest', 'Unlinked owner inquiry', operation_key='unlinked')
        peer = lineage.create_inquiry('siren', 'PEER header', operation_key='peer')
        proposal = lineage.create_proposal(linked, 'tempest', {
            'symbol': 'SPY261218C00600000', 'underlying': 'SPY', 'expiry': '2026-12-18',
            'option_type': 'call', 'strike': '600', 'multiplier': 100, 'qty': 1,
            'side': 'buy', 'intent': 'open', 'order_type': 'limit', 'limit_price': '1',
        }, operation_key='proposal')
        token = self.store.begin(ID)
        self.store.claim_job(ID, 'tempest-r1', token)
        self.store.finish_job(ID, 'tempest-r1', token, action='inquire', record_refs=[{'kind': 'inquiry', 'id': linked}, {'kind': 'inquiry', 'id': peer}])
        result = self.request('journals?agent_id=tempest&channel=idea&limit=1')[1]
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['sources'][0]['id'], linked)
        self.assertEqual(result['sources'][0]['title'], '<b>Literal inquiry title</b>')
        self.assertNotIn('PEER', json.dumps(result))
        self.assertNotIn('Unlinked owner inquiry', json.dumps(result))
        trading = self.request('journals?agent_id=tempest&channel=trading')[1]
        self.assertEqual(trading['sources'][0]['proposal_ids'], [proposal])
        self.assertEqual(trading['sources'][0]['provenance'], 'lineage_proposals')
        for field in ('proposals', 'orders', 'fills', 'structure', 'thesis'):
            self.assertNotIn('"' + field + '"', json.dumps(trading))
        self.assertEqual(self.request('journals?agent_id=tempest&channel=idea&state=released')[1]['sources'], [])

    def test_all_routes_are_get_only_and_actual_reads_never_execute_ddl_or_dml(self):
        self.collect()
        self.witness('tempest')
        self.witness('steward')
        original_connect = sqlite3.connect
        denied = {getattr(sqlite3, name) for name in ('SQLITE_INSERT', 'SQLITE_UPDATE', 'SQLITE_DELETE', 'SQLITE_CREATE_TABLE', 'SQLITE_CREATE_INDEX', 'SQLITE_CREATE_TRIGGER', 'SQLITE_ALTER_TABLE', 'SQLITE_DROP_TABLE')}
        calls = []
        def readonly_connect(path, *args, **kwargs):
            calls.append(str(path))
            self.assertIn('mode=ro', str(path))
            conn = original_connect(path, *args, **kwargs)
            conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK)
            return conn
        with mock.patch.object(sqlite3, 'connect', side_effect=readonly_connect):
            for path in ('journals?agent_id=tempest&channel=idea', 'journals?agent_id=tempest&note_id=1', 'witness?agent_id=tempest', 'witness'):
                self.assertEqual(self.request(path)[0], 200, path)
        self.assertGreater(len(calls), 0)
        self.assertTrue(all(route.methods == {'GET'} for route in self.app.routes))
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self.assertEqual(self.request('journals?agent_id=tempest', method=method)[0], 405)
            self.assertEqual(self.request('witness', method=method)[0], 405)

    def test_symlink_memory_witness_and_sidecars_are_rejected_without_following(self):
        for relative in ('memory/tempest.sqlite3', 'witness.sqlite3'):
            path = self.store.safe_run_file(ID, relative)
            outside = Path(self.temp) / ('outside-' + path.name)
            outside.write_bytes(b'NEVER FOLLOW')
            path.symlink_to(outside)
            suffix = 'journals?agent_id=tempest' if 'memory' in relative else 'witness'
            self.assertNotEqual(self.request(suffix)[0], 200)
            self.assertEqual(outside.read_bytes(), b'NEVER FOLLOW')
            path.unlink()
        self.collect()
        sidecar = Path(str(self.store.safe_run_file(ID, 'memory/tempest.sqlite3')) + '-wal')
        sidecar.symlink_to(Path(self.temp) / 'absent')
        self.assertNotEqual(self.request('journals?agent_id=tempest')[0], 200)


if __name__ == '__main__':
    unittest.main()
