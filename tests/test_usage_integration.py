"""Real private ledger + mocked HTTP requests; no connected provider calls."""
import json
from pathlib import Path
from unittest import mock

from core.runtime import llm
from core.usage import store as usage_store
from core.usage.context import usage_scope
from core.usage.pricing import PricingTable
from core.usage.store import UsageStore
from tests.test_agent_loop import OfflineCase


class UsageProviderLedgerIntegrationTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.ledger = UsageStore(Path(self.tmp) / 'usage.sqlite3', PricingTable())
        self.patch(usage_store, 'get_usage_store', return_value=self.ledger)
        self.patch(llm, '_get_api_key', return_value='OFFLINE_KEY_NEVER_STORE')
        self.patch(llm.time, 'sleep')

    @staticmethod
    def response(data, status=200):
        response = mock.Mock()
        response.status_code = status
        response.json.return_value = data
        response.raise_for_status.return_value = None
        return response

    def call(self, retries=1):
        return llm._call_llm_raw('tempest', [{'role': 'user', 'content': 'PRIVATE_QUERY_NEVER_STORE'}],
            'PRIVATE_SYSTEM_NEVER_STORE', 0.7, 100, 'offline/model', retries, 0)

    def test_retry_attempts_have_one_correlation_and_known_unknown_subtotals(self):
        response = self.response({'choices': [{'message': {'content': 'PRIVATE_ANSWER_NEVER_STORE'}}],
            'model': 'offline/model', 'usage': {'prompt_tokens': 10, 'completion_tokens': 5,
            'total_tokens': 15, 'prompt_tokens_details': {'cached_tokens': 0}, 'cost': '0.0002'}})
        post = self.patch(llm.requests, 'post', side_effect=[llm.requests.Timeout('PRIVATE_EXCEPTION_NEVER_STORE'), response])
        with usage_scope('monitor', wake_id='offline-wake'):
            self.assertEqual(self.call(retries=2), 'PRIVATE_ANSWER_NEVER_STORE')
        events = self.ledger.list_events()['events']
        self.assertEqual(len(events), 2)
        self.assertEqual(len({e['call_id'] for e in events}), 1)
        self.assertEqual({e['attempt'] for e in events}, {1, 2})
        self.assertTrue(all(e['wake_id'] == 'offline-wake' and e['activity'] == 'monitor' for e in events))
        summary = self.ledger.summary()['summary']
        self.assertEqual(summary['requests'], 2)
        self.assertEqual(summary['failed_requests'], 1)
        self.assertEqual(summary['unknown_cost_requests'], 1)
        self.assertEqual(summary['reported_cost_usd'], '0.0002')
        self.assertIsNone(summary['estimated_cost_usd'])
        self.assertEqual(summary['usage_known_requests'], 1)
        rendered = json.dumps(events)
        for sentinel in ('PRIVATE_QUERY', 'PRIVATE_SYSTEM', 'PRIVATE_ANSWER', 'PRIVATE_EXCEPTION', 'OFFLINE_KEY'):
            self.assertNotIn(sentinel, rendered)
        self.assertEqual(post.call_count, 2)

    def test_reported_zero_survives_malformed_optional_cache_and_reasoning_counts(self):
        response = self.response({'choices': [{'message': {'content': 'offline answer'}}],
            'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'cost': 0,
                'prompt_tokens_details': {'cached_tokens': 999},
                'completion_tokens_details': {'reasoning_tokens': 999}}})
        post = self.patch(llm.requests, 'post', return_value=response)
        self.assertEqual(self.call(), 'offline answer')
        event = self.ledger.list_events()['events'][0]
        self.assertEqual(event['cost_status'], 'reported')
        self.assertEqual(event['cost_usd'], '0')
        self.assertIsNone(event['cached_input_tokens'])
        self.assertIsNone(event['reasoning_tokens'])
        self.assertEqual(self.ledger.summary()['summary']['requests'], 1)
        post.assert_called_once()
