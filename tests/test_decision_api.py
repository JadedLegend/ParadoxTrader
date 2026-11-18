"""Actual temporary-store ASGI reads, with all external network blocked."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from api import rehearsal
from core.runtime.rehearsal.store import RehearsalStore, CAPABILITIES, _message_input
from tests.test_rehearsal_api import _asgi_request, TOKEN
from tests.test_rehearsal_store import synthetic_manifest

class DecisionAPI(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp) / 'runs'
        self.store = RehearsalStore(self.root)
        self.run_id = self.store.prepare(synthetic_manifest())['run_id']
        self.token = self.store.begin(self.run_id)
        self.wake = 'tempest-r1'
        self.store.claim_job(self.run_id, self.wake, self.token)
        manifest = self.store.get_manifest(self.run_id)
        self.metadata = {'schema_version': 1, 'offered_actions': list(CAPABILITIES),
            'action_costs': [{'action': action, 'max_requests': 1 if action == 'rest' else 2,
                             'reservation_ceiling_usd': '0', 'basis': 'catalog_upper_bound'} for action in CAPABILITIES],
            'constraints': manifest['limits'], 'admission_snapshot': {'reserved_usd': '0', 'remaining_budget_usd': '1', 'request_count': 0, 'remaining_requests': 28, 'is_reservation': False},
            'model': {'requested_model': 'synthetic/tempest', 'context_length': 65536, 'max_completion_tokens': 1024, 'catalog_source': 'synthetic'},
            'continuity': {'status': 'empty', 'refs': [], 'truncated': False, 'chars': 0}}
        self.store.commit_decision_context(self.run_id, self.wake, self.token, metadata=self.metadata,
            private_context={'continuity': {'status': 'empty', 'refs': [], 'excerpts': [], 'body': '<script>literal PRIVATE</script>'}, 'include_metadata': True, 'include_continuity': True})
        messages = [{'role': 'system', 'content': 'Exact identity'}, {'role': 'user', 'content': 'FULL literal private input'}]
        _, self.digest, size = _message_input(messages)
        self.request_id = self.store.reserve_request(self.run_id, self.wake, self.token, agent_id='tempest', activity='choice', model='synthetic/tempest', input_bytes=size, max_output_tokens=1024, reserved_usd='0')
        self.store.commit_request_context(self.run_id, self.request_id, self.token, messages)
        self.app = rehearsal.create_app(self.root, operator_token=TOKEN)
        self.path = f'/api/rehearsals/{self.run_id}/decisions?agent_id=tempest&wake_id={self.wake}'
        for target in ('socket.create_connection', 'socket.socket.connect', 'urllib.request.urlopen'):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError('network forbidden')))
            self.addCleanup(guard.assert_not_called)
    def request(self, path=None, **options):
        return asyncio.run(_asgi_request(self.app, path or self.path, **options))
    def test_actual_details_are_exact_owner_inputs_and_read_only(self):
        db = self.root / self.run_id / 'control.sqlite3'
        before = db.read_bytes()
        with mock.patch.object(RehearsalStore, '_context_schema', side_effect=AssertionError('read DDL forbidden')):
            status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(headers[b'cache-control'], b'private, no-store')
        self.assertEqual(body['decision']['metadata'], self.metadata)
        event = body['decision']['requests'][0]
        self.assertEqual((event['agent_id'], event['wake_id'], event['input_sha256'], event['input_coverage']), ('tempest', self.wake, self.digest, 'complete'))
        self.assertEqual(event['messages'][1]['content'], 'FULL literal private input')
        self.assertIn('<script>literal PRIVATE</script>', json.dumps(body))
        self.assertEqual(db.read_bytes(), before)
        for path in ('', '/jobs', '/requests'):
            public = self.request(f'/api/rehearsals/{self.run_id}{path}')[1]
            self.assertNotIn('literal PRIVATE', json.dumps(public))
            self.assertNotIn('FULL literal', json.dumps(public))
    def test_auth_and_owner_validation_precede_all_store_io(self):
        with mock.patch.object(rehearsal, '_store', side_effect=AssertionError('no IO')) as factory:
            self.assertEqual(self.request(authorization=None)[0], 403)
            for query in ('agent_id=siren&wake_id=tempest-r1', 'agent_id=tempest&wake_id=tempest-r49', 'agent_id=tempest&wake_id=tempest-r1&wake_id=tempest-r2', 'agent_id=outsider&wake_id=tempest-r1', 'agent_id=tempest', 'agent_id=tempest&wake_id=tempest-r1&operator=true'):
                self.assertIn(self.request(f'/api/rehearsals/{self.run_id}/decisions?{query}')[0], (400, 404))
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                self.assertEqual(self.request(method=method)[0], 405)
            factory.assert_not_called()
        self.assertTrue(all(route.methods == {'GET'} for route in self.app.routes))
    def test_legacy_missing_context_is_unavailable_without_schema_backfill(self):
        before = (self.root / self.run_id / 'control.sqlite3').read_bytes()
        self.assertEqual(self.request(f'/api/rehearsals/{self.run_id}/decisions?agent_id=siren&wake_id=siren-r1')[0], 404)
        self.assertEqual((self.root / self.run_id / 'control.sqlite3').read_bytes(), before)
    def test_nested_public_and_private_dynamic_fields_are_not_forwarded(self):
        details = self.store.get_decision_details(self.run_id, self.wake)
        details['metadata']['continuity']['raw_output'] = 'UNEXPECTED SECRET'
        details['private_context']['api_key'] = 'UNEXPECTED SECRET'
        details['requests'][0]['authorization'] = 'UNEXPECTED SECRET'
        details['requests'][0]['messages'][0]['api_key'] = 'UNEXPECTED SECRET'
        fake = mock.Mock(); fake.list_jobs.return_value = self.store.list_jobs(self.run_id); fake.get_decision_details.return_value = details
        with mock.patch.object(rehearsal, '_store', return_value=fake):
            status, body, _ = self.request()
            self.assertEqual(status, 200)
            self.assertNotIn('UNEXPECTED SECRET', json.dumps(body))
            for attack in ('request', 'private', 'wrapper'):
                changed = deepcopy(details)
                if attack == 'request': changed['requests'][0]['agent_id'] = 'siren'
                if attack == 'private': changed['private_context']['continuity']['agent_id'] = 'siren'
                if attack == 'wrapper': fake.list_jobs.return_value = [{'wake_id': self.wake, 'agent_id': 'siren'}]
                fake.get_decision_details.return_value = changed
                self.assertEqual(self.request()[0], 404)

if __name__ == '__main__':
    unittest.main()
