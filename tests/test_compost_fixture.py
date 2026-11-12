"""All example notes are scripted temporary-store data, not real agent output."""
import json
import unittest
from scripts.build_compost_fixture import build_compost_fixture, OUTPUT, RUN_ID


class CompostFixtureTests(unittest.TestCase):
    def test_checked_in_journals_share_actual_session_source(self):
        fixture = build_compost_fixture()
        self.assertEqual(json.loads(OUTPUT.read_text()), fixture)
        self.assertEqual(fixture['kind'], 'fixture')
        self.assertIn('scripted', fixture['provenance'].lower())
        self.assertEqual(fixture['runs'][0]['run_id'], RUN_ID)
        self.assertEqual(fixture['runs'][0]['mode'], 'offline')

    def test_distillation_keeps_all_six_released_originals_reachable(self):
        notes = build_compost_fixture()['journals'][RUN_ID]['tempest']
        digest = next(note for note in notes if note['note_kind'] == 'distillation')
        sources = {note['id']: note for note in notes}
        self.assertEqual(len(digest['source_ids']), 6)
        for source_id in digest['source_ids']:
            original = sources[source_id]
            self.assertEqual(original['note_kind'], 'compost')
            self.assertEqual(original['state'], 'released')
            self.assertIn('Scripted compost', original['content'])
        self.assertTrue(any(note['note_kind'] == 'compost' and note['state'] == 'active' for note in notes))
        self.assertEqual(set(digest['channels']), {'idea', 'orientation'})

    def test_accounts_are_separate_source_backed_mechanical_records(self):
        fixture = build_compost_fixture()
        for scope, accounts in fixture['witnesses'][RUN_ID].items():
            for account in accounts:
                self.assertEqual(account['scope'], scope)
                self.assertEqual(account['author'], 'witness')
                self.assertEqual(account['method'], 'mechanical')
                self.assertNotIn('Scripted compost', account['content'])
                self.assertNotIn('messages', account)
                self.assertNotIn('reasoning', account)
        self.assertTrue(fixture['witnesses'][RUN_ID]['steward'])

    def test_idea_destination_reuses_actual_owned_inquiry_headers(self):
        fixture = build_compost_fixture()
        headers = fixture['sources'][RUN_ID]['alchemist']
        self.assertTrue(headers)
        for header in headers:
            self.assertEqual(header['agent_id'], 'alchemist')
            self.assertEqual(header['kind'], 'inquiry')
            self.assertEqual(header['provenance'], 'lineage_inquiries')
            self.assertFalse(header['proposal_ids'])
            self.assertNotIn('interpretation', header)
            self.assertNotIn('journal', header)


if __name__ == '__main__':
    unittest.main()
