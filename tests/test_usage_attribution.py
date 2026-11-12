"""Activity scopes change metadata only; model/provider/ledger calls are mocked."""
from unittest import mock

from core.usage.attribution import attribute_activity
from core.usage.context import current_usage_context, usage_scope
from tests.test_agent_loop import OfflineCase, MENU, loop, perplexity, council


class UsageAttributionTests(OfflineCase):
    def test_picker_and_action_share_wake_id_but_keep_distinct_activities(self):
        snapshots = []
        def response(*args, **kwargs):
            snapshots.append(current_usage_context())
            return '1' if len(snapshots) == 1 else 'An observed signal.'
        self.llm.side_effect = response
        self.patch(loop, 'get_available_actions', return_value=MENU)
        self.patch(loop, 'get_cross_agent_positions', return_value={})
        result = loop.agent_wake('tempest', 0)
        self.assertEqual(result['action'], 'monitor')
        self.assertEqual([s['activity'] for s in snapshots], ['choose_action', 'monitor'])
        self.assertIsNotNone(snapshots[0]['wake_id'])
        self.assertEqual(snapshots[0]['wake_id'], snapshots[1]['wake_id'])
        self.assertEqual(current_usage_context(), {'activity': 'unattributed', 'wake_id': None})
        self.assertEqual(self.llm.call_count, 2)
        self.broker.assert_not_called()

    def test_distinct_wakes_have_distinct_correlation_ids(self):
        identifiers = []
        def response(*args, **kwargs):
            context = current_usage_context()
            if context['activity'] == 'choose_action':
                identifiers.append(context['wake_id'])
                return '2'
            raise AssertionError('Rest must not call another model')
        self.llm.side_effect = response
        self.patch(loop, 'get_available_actions', return_value=MENU)
        self.patch(loop, 'get_cross_agent_positions', return_value={})
        for _ in range(2):
            self.assertEqual(loop.agent_wake('tempest', 0)['action'], 'rest')
        self.assertEqual(len(set(identifiers)), 2)
        self.assertEqual(self.llm.call_count, 2)

    def test_interval_rest_does_not_call_models_or_initialize_a_ledger(self):
        from core import usage
        factory = self.patch(usage, 'get_usage_store', side_effect=AssertionError('No ledger work during rest'))
        state = self.state(hrv=0, in_interval=True)
        self.hrv.save(state)
        result = loop.agent_wake('tempest', 0)
        self.assertEqual(result['wake'], 'interval')
        self.llm.assert_not_called()
        factory.assert_not_called()
        self.assertEqual(current_usage_context()['activity'], 'unattributed')

    def test_action_scopes_cover_external_research_and_restore_after_return(self):
        seen = []
        def research(*args, **kwargs):
            seen.append(current_usage_context())
            return {'answer': 'Source account', 'citations': [], 'model': 'offline'}
        self.patch(perplexity, 'is_available', return_value=True)
        external = self.patch(perplexity, 'research', side_effect=research)
        self.llm.side_effect = ['A short question', 'A source interpretation']
        with usage_scope('caller', wake_id='offline-wake'):
            result = self.execute('research', phase=0)
            self.assertEqual(current_usage_context(), {'activity': 'caller', 'wake_id': 'offline-wake'})
        self.assertEqual(result['action'], 'research')
        self.assertEqual(seen, [{'activity': 'research', 'wake_id': 'offline-wake'}])
        external.assert_called_once()
        self.assertEqual(self.llm.call_count, 2)

    def test_council_response_is_attributed_without_order_submission(self):
        seen = []
        def response(*args, **kwargs):
            seen.append(current_usage_context())
            return 'Neutral: more evidence would help.'
        self.patch(council, 'call_llm', side_effect=response)
        result = council.get_council_response('tempest', 'OFFLINE_BRIEF', self.forum)
        self.assertEqual(result['agent'], 'tempest')
        self.assertEqual(seen, [{'activity': 'council_response', 'wake_id': None}])
        self.assertEqual(current_usage_context()['activity'], 'unattributed')
        self.broker.assert_not_called()

    def test_exception_restores_outer_context_without_changing_failure(self):
        self.llm.side_effect = RuntimeError('offline failure')
        with usage_scope('caller', wake_id='offline-parent'):
            with self.assertRaisesRegex(RuntimeError, 'offline failure'):
                self.execute('monitor')
            self.assertEqual(current_usage_context(), {'activity': 'caller', 'wake_id': 'offline-parent'})
        self.assertEqual(current_usage_context()['activity'], 'unattributed')

    def test_unknown_action_keeps_unsupported_result_without_context_validation_failure(self):
        result = self.execute('an unsupported / unusual action')
        self.assertEqual(result, {'action': 'an unsupported / unusual action', 'status': 'unsupported_action'})
        self.llm.assert_not_called()
        self.assertEqual(current_usage_context()['activity'], 'unattributed')

    def test_decorator_preserves_wrapped_function_arguments_and_return_value(self):
        @attribute_activity('offline')
        def original(value, *, option=None):
            self.assertEqual(current_usage_context()['activity'], 'offline')
            return value, option
        sentinel = object()
        self.assertEqual(original(sentinel, option=3), (sentinel, 3))
        self.assertEqual(original.__name__, 'original')
        self.assertTrue(hasattr(original, '__wrapped__'))
