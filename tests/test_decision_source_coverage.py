"""Retain readable inquiry nuance while exposing incomplete source coverage."""
import unittest
from unittest.mock import Mock, patch
from core.runtime.rehearsal.continuity import owner_continuity, public_coverage


class DecisionSourceCoverageTests(unittest.TestCase):
    def test_unreadable_entry_does_not_hide_behind_readable_title(self):
        store = Mock()
        inquiry_id = '12345678-1234-4234-8234-123456789abc'
        store.list_jobs.return_value = [{'agent_id': 'siren', 'round': 1, 'wake_id': 'siren-r1',
                                        'record_refs': [{'kind': 'inquiry', 'id': inquiry_id}]}]
        title = {'inquiry_id': inquiry_id, 'title': 'A still-readable question',
                 'original_chars': 25, 'state': 'open'}
        unusable_entry = {'entry_id': '22345678-1234-4234-8234-123456789abc',
                          'kind': 'interpretation', 'source': 'agent',
                          'content': b'not a text field', 'original_chars': 16}
        with patch('core.runtime.rehearsal.continuity._read', side_effect=[title, unusable_entry]):
            result = owner_continuity(store, 'run', {'agent_id': 'siren', 'round': 2})
        self.assertTrue(result['unavailable'])
        self.assertEqual(result['excerpts'][0]['title'], 'A still-readable question')
        self.assertEqual(result['excerpts'][0]['entry_status'], 'unavailable')
        coverage = public_coverage(result)
        self.assertEqual(coverage['status'], 'truncated')
        self.assertTrue(coverage['truncated'])
        self.assertEqual(coverage['refs'][0]['id'], inquiry_id)
        self.assertNotIn('still-readable', str(coverage))


if __name__ == '__main__':
    unittest.main()
