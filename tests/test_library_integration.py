"""Actual preserved source index + mocked agent action, entirely offline."""
import json
from pathlib import Path
import sqlite3

from core.library.store import LibraryStore
from tests.test_agent_loop import OfflineCase, loop


class RealLibraryActionIntegrationTests(OfflineCase):
    def test_real_source_excerpts_fit_action_bounds_and_persist_exact_references(self):
        from core import library
        corpus = Path(__file__).resolve().parents[1] / 'library' / 'corpus.json'
        store = LibraryStore(corpus, Path(self.tmp) / 'source-index.sqlite3')
        self.patch(library, 'get_library', return_value=store)
        self.llm.side_effect = ['options pricing timing', 'An interpretation to revisit when new evidence arrives.']
        state = self.state(hrv=80)
        result = loop.execute_action('tempest', 'browse_library', loop.load_soul('tempest'),
            loop.load_living('tempest'), self.memory(), self.forum, self.messages, state, 0,
            context={'market_data': {'status': 'not_supplied'}})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(state.hrv, 78)
        self.assertEqual(len(result['citations']), 3)
        self.assertEqual(self.llm.call_count, 2)
        prompt = self.llm.call_args.args[1][-1]['content']
        self.assertLessEqual(len(prompt), 6000)
        quoted = json.loads(prompt.split('Quoted SOURCE excerpts (JSON):\n', 1)[1])
        self.assertLessEqual(sum(len(hit['excerpt']) for hit in quoted['results']), 1800)
        for hit in quoted['results']:
            actual = store.read_section(hit['section_id'], offset=hit['offset'], max_chars=600)
            self.assertEqual(actual['text'], hit['excerpt'])
            self.assertEqual(actual['sha256'], hit['sha256'])
            self.assertEqual(actual['filename'], hit['filename'])
            self.assertEqual(actual['locator'], hit['locator'])
        episode = self.memory().get_recent_episodes()[0]
        citations = json.loads(episode['content'].split('\nLibrary sources: ', 1)[1])
        self.assertEqual(citations, result['citations'])
        with sqlite3.connect(self.memory().db_path) as connection:
            row = connection.execute('SELECT delta_coherence, effort, joy_score FROM episodes LIMIT 1').fetchone()
        self.assertEqual(row, (None, None, None))
        self.assertEqual(self.memory().read_journal(), [])
        self.broker.assert_not_called()
        self.creds.assert_not_called()
