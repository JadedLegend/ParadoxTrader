"""Exact private input evidence; every HTTP transport is injected and socket-blocked."""
import hashlib
import json
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.controller import decision_metadata, validate_choice
from core.runtime.rehearsal.provider import OpenRouterTransport, ProviderError, bounded_input
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_rehearsal_provider import manifest, Response


class DecisionProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)
        self.store = RehearsalStore(self.temp.name)
        self.manifest = manifest('real')
        self.run_id = self.store.prepare(self.manifest)['run_id']
        self.manifest = self.store.get_manifest(self.run_id)
        self.token = self.store.begin(self.run_id)
        self.job = self.store.claim_job(self.run_id, 'tempest-r1', self.token)
        empty = {'status': 'empty', 'refs': [], 'truncated': False, 'chars': 0,
                 'excerpts': [], 'unavailable': False}
        metadata = decision_metadata(self.manifest, self.job, self.store.get_run(self.run_id), empty)
        self.store.commit_decision_context(self.run_id, self.job['wake_id'], self.token,
                                           metadata=metadata, private_context=empty)
        self.sent = []

    def generate(self, response=None, messages=None, system_prompt=None, post=None):
        def http(_url, **kwargs):
            self.sent.append(kwargs['json']['messages'])
            # Both the private input and dispatch transition exist before HTTP.
            details = self.store.get_decision_details(self.run_id, self.job['wake_id'])
            self.assertEqual(details['requests'][-1]['messages'], kwargs['json']['messages'])
            return response or Response()
        transport = OpenRouterTransport('explicit-fake-key', http_post=post or http, is_live=True)
        return transport.generate(store=self.store, run_id=self.run_id, token=self.token,
                                  wake_id=self.job['wake_id'], agent_id='tempest', activity='choice',
                                  messages=messages or [{'role': 'user', 'content': 'A literal private question.'}],
                                  system_prompt=system_prompt, validator=validate_choice)

    def test_exact_unicode_final_messages_are_private_and_hashed(self):
        self.generate(messages=[{'role': 'user', 'content': 'Quoted nuance: café; “leave it open”.'}],
                      system_prompt='A frozen system orientation.')
        details = self.store.get_decision_details(self.run_id, 'tempest-r1')
        request = details['requests'][0]
        self.assertEqual(request['messages'], self.sent[0])
        canonical = json.dumps(request['messages'], ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode('utf-8')
        self.assertEqual(request['input_sha256'], hashlib.sha256(canonical).hexdigest())
        event = self.store.list_requests(self.run_id)['events'][0]
        self.assertEqual(event['input_bytes'], bounded_input(self.sent[0]))
        self.assertEqual(event['finish_reason'], 'stop')
        operational = json.dumps(self.store.list_jobs(self.run_id)) + json.dumps(event)
        self.assertNotIn('café', operational)
        self.assertNotIn('frozen system orientation', operational)
        self.assertNotIn('explicit-fake-key', json.dumps(details))
        self.assertNotIn('messages', event)

    def test_truncation_retains_input_and_finish_without_repaired_rest(self):
        with self.assertRaisesRegex(ProviderError, 'output_truncated'):
            self.generate(Response(finish='length'))
        event = self.store.list_requests(self.run_id)['events'][0]
        self.assertEqual(event['finish_reason'], 'length')
        self.assertEqual(event['failure_code'], 'output_truncated')
        self.assertEqual(len(self.sent), 1)
        self.assertIsNone(self.store.list_jobs(self.run_id)[0]['action'])
        self.assertEqual(len(self.store.get_decision_details(self.run_id, 'tempest-r1')['requests']), 1)

    def test_malformed_choice_does_not_become_model_rest(self):
        with self.assertRaisesRegex(ProviderError, 'invalid_activity_output'):
            self.generate(Response(content='This is not a JSON choice.'))
        job = self.store.list_jobs(self.run_id)[0]
        self.assertIsNone(job['action'])
        self.assertEqual(job['selection_origin'], 'none')
        self.assertEqual(self.store.list_requests(self.run_id)['events'][0]['finish_reason'], 'stop')

    def test_input_write_failure_blocks_http_and_records_not_sent(self):
        with patch.object(self.store, 'commit_request_context', side_effect=OSError('private failure detail')):
            with self.assertRaisesRegex(ProviderError, '^request_context_unavailable$'):
                self.generate()
        self.assertEqual(self.sent, [])
        event = self.store.list_requests(self.run_id)['events'][0]
        self.assertEqual(event['outcome'], 'not_sent')
        self.assertEqual(event['failure_code'], 'request_context_unavailable')
        self.assertNotIn('private failure detail', str(event))
        self.assertIsNone(event['finish_reason'])

    def test_unknown_finish_label_is_bounded_and_never_copied_as_private_text(self):
        with self.assertRaisesRegex(ProviderError, 'unsupported_finish'):
            self.generate(Response(finish='arbitrary private provider detail'))
        event = self.store.list_requests(self.run_id)['events'][0]
        self.assertEqual(event['finish_reason'], 'unknown')
        self.assertNotIn('arbitrary private provider detail', str(event))


if __name__ == '__main__':
    unittest.main()
