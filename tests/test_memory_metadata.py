"""Offline episode metadata contract, including each real episode-producing handler.

Run: python -m unittest tests.test_memory_metadata -v
The wake fixture blocks sockets, HTTP, research, real LLMs, identity writes,
trade submission, and council execution. Every database lives in a temporary dir.
"""
import inspect
import json
from pathlib import Path
import re
import sqlite3

from tests.test_agent_loop import OfflineCase, ThresholdMemory, loop


# One separately reported parameterized unittest per implemented episode action.
# Roaming and research choose a question before synthesizing; all calls are mocks.
EPISODE_ACTIONS = {
    "monitor": 1,
    "research": 2,
    "browse_library": 2,
    "analyze": 1,
    "roam": 2,
    "forum_post": 1,
    "direct_message": 1,
    "propose_trade": 1,
    "review_position": 1,
    "analyze_volatility": 1,
    "analyze_sentiment": 1,
    "analyze_correlation": 1,
    "analyze_macro": 1,
    "analyze_risk": 1,
    "analyze_options": 1,
    "analyze_consensus": 1,
    "roam_momentum": 2,
    "roam_contrarian": 2,
}


LEGACY_EPISODE_SCHEMA = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT 'symmetry',
    delta_coherence REAL DEFAULT 0.0,
    effort REAL DEFAULT 1.0,
    joy_score REAL GENERATED ALWAYS AS (delta_coherence / (1.0 + effort)) VIRTUAL,
    tags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
"""


def metadata_row(memory, episode_id):
    with sqlite3.connect(memory.db_path) as conn:
        return conn.execute(
            "SELECT delta_coherence, effort, joy_score FROM episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()


def full_episode_row(memory, episode_id):
    with sqlite3.connect(memory.db_path) as conn:
        return conn.execute(
            "SELECT id, title, content, phase, delta_coherence, effort, joy_score, tags, created_at "
            "FROM episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()


class MemoryMetadataTests(OfflineCase):
    def test_store_episode_measurement_defaults_are_none(self):
        parameters = inspect.signature(ThresholdMemory.store_episode).parameters
        self.assertIsNone(parameters["delta_coherence"].default)
        self.assertIsNone(parameters["effort"].default)

    def test_default_episode_persists_sql_nulls_and_reports_not_measured_after_reopen(self):
        memory = self.memory()
        episode_id = memory.store_episode("DEFAULT_NULL_SENTINEL", "An observation, not a measured gain")
        self.assertEqual(metadata_row(memory, episode_id), (None, None, None))
        reopened = ThresholdMemory(memory.db_path)
        self.assertEqual(metadata_row(reopened, episode_id), (None, None, None))
        result = reopened.query("DEFAULT_NULL_SENTINEL")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], episode_id)
        self.assertIsNone(result[0]["joy"])
        self.assertEqual(result[0]["joy_status"], "not_measured")
        self.assertEqual(json.loads(json.dumps(result))[0]["joy"], None)

    def test_fresh_sql_schema_does_not_invent_measurements_when_columns_are_omitted(self):
        memory = self.memory()
        with sqlite3.connect(memory.db_path) as conn:
            episode_id = conn.execute(
                "INSERT INTO episodes (title, content, created_at) VALUES (?, ?, ?)",
                ("RAW_NULL_SENTINEL", "unspecified measurements", "2026-01-01T00:00:00+00:00"),
            ).lastrowid
        self.assertEqual(metadata_row(memory, episode_id), (None, None, None))
        result = memory.query("RAW_NULL_SENTINEL")[0]
        self.assertIsNone(result["joy"])
        self.assertEqual(result["joy_status"], "not_measured")

    def test_partial_or_explicitly_null_measurements_never_become_zero_or_crash_query(self):
        memory = self.memory()
        for coherence, effort in ((None, None), (None, 2.0), (3.0, None), (0.0, None), (None, 0.0)):
            with self.subTest(coherence=coherence, effort=effort):
                episode_id = memory.store_episode(
                    "PARTIAL_NULL_SENTINEL", "unmeasured episode",
                    delta_coherence=coherence, effort=effort,
                )
                self.assertEqual(metadata_row(memory, episode_id), (coherence, effort, None))
                result = next(item for item in memory.query("PARTIAL_NULL_SENTINEL", limit=10)
                              if item["id"] == episode_id)
                self.assertIsNone(result["joy"])
                self.assertEqual(result["joy_status"], "not_measured")

    def test_explicit_numeric_legacy_values_in_new_records_remain_supplied_including_zero(self):
        memory = self.memory()
        for coherence, effort, joy in ((3.0, 2.0, 1.0), (0.0, 0.0, 0.0), (-2.0, 1.0, -1.0)):
            with self.subTest(coherence=coherence, effort=effort):
                episode_id = memory.store_episode(
                    "LEGACY_NUMERIC_SENTINEL", "explicit prior-style measures", phase="break",
                    delta_coherence=coherence, effort=effort, tags=["explicit", "legacy"],
                )
                self.assertEqual(metadata_row(memory, episode_id), (coherence, effort, joy))
                reopened = ThresholdMemory(memory.db_path)
                self.assertEqual(metadata_row(reopened, episode_id), (coherence, effort, joy))
                result = next(item for item in reopened.query("LEGACY_NUMERIC_SENTINEL", limit=10)
                              if item["id"] == episode_id)
                self.assertEqual(result["joy"], joy)
                self.assertEqual(result["joy_status"], "legacy_supplied")

    def test_existing_old_schema_numeric_history_is_not_rewritten_and_new_defaults_are_null(self):
        path = str(Path(self.tmp) / "legacy-memory.sqlite3")
        with sqlite3.connect(path) as conn:
            conn.executescript(LEGACY_EPISODE_SCHEMA)
            explicit_id = conn.execute(
                "INSERT INTO episodes (id, title, content, phase, delta_coherence, effort, tags, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (41, "EXISTING_EXPLICIT_SENTINEL", "Keep the historical account", "novelty", 3.0, 2.0,
                 '["historical"]', "2024-01-02T03:04:05+00:00"),
            ).lastrowid
            # A value generated by the old schema's default is still historical
            # numeric data; opening the database must not silently erase it.
            default_id = conn.execute(
                "INSERT INTO episodes (title, content, created_at) VALUES (?, ?, ?)",
                ("EXISTING_DEFAULT_SENTINEL", "An old record", "2024-01-03T03:04:05+00:00"),
            ).lastrowid
            before = conn.execute(
                "SELECT id, title, content, phase, delta_coherence, effort, joy_score, tags, created_at "
                "FROM episodes ORDER BY id"
            ).fetchall()
        memory = ThresholdMemory(path)
        self.assertEqual(full_episode_row(memory, explicit_id), before[0])
        self.assertEqual(full_episode_row(memory, default_id), before[1])
        new_id = memory.store_episode("NEW_UNMEASURED_SENTINEL", "New automatic account")
        explicit_new_id = memory.store_episode(
            "NEW_EXPLICIT_SENTINEL", "Explicit imported values", delta_coherence=4.0, effort=1.0,
        )
        reopened = ThresholdMemory(path)
        self.assertEqual(full_episode_row(reopened, explicit_id), before[0])
        self.assertEqual(full_episode_row(reopened, default_id), before[1])
        self.assertEqual(metadata_row(reopened, new_id), (None, None, None))
        self.assertEqual(metadata_row(reopened, explicit_new_id), (4.0, 1.0, 2.0))
        for query, expected_joy in (("EXISTING_EXPLICIT_SENTINEL", 1.0),
                                    ("EXISTING_DEFAULT_SENTINEL", 0.0)):
            result = reopened.query(query)[0]
            self.assertEqual(result["joy"], expected_joy)
            self.assertEqual(result["joy_status"], "legacy_supplied")
        self.assertEqual(reopened.query("NEW_UNMEASURED_SENTINEL")[0]["joy_status"], "not_measured")

    def test_default_lexical_scores_do_not_weight_any_phase(self):
        memory = self.memory()
        ids = [memory.store_episode(f"Record {phase}", "EQUAL_OVERLAP_SENTINEL", phase=phase)
               for phase in ("symmetry", "tension", "break", "novelty", "reintegration")]
        results = memory.query("EQUAL_OVERLAP_SENTINEL", limit=10)
        self.assertEqual({item["id"] for item in results}, set(ids))
        self.assertEqual({item["score"] for item in results}, {1.0})
        self.assertTrue(all(item["joy"] is None for item in results))
        self.assertTrue(all(item["joy_status"] == "not_measured" for item in results))

    def test_lexical_overlap_beats_phase_heuristics_by_default(self):
        memory = self.memory()
        strong = memory.store_episode("Strong match", "alpha beta gamma", phase="symmetry")
        weak = memory.store_episode("Weak match", "alpha beta", phase="break")
        results = memory.query("alpha beta gamma")
        self.assertEqual([item["id"] for item in results], [strong, weak])
        self.assertEqual([item["score"] for item in results], [3.0, 2.0])

    def test_explicit_phase_bias_can_apply_a_heuristic_without_measuring_joy(self):
        memory = self.memory()
        symmetry = memory.store_episode("Ordinary match", "BIAS_SENTINEL", phase="symmetry")
        novelty = memory.store_episode("Chosen match", "BIAS_SENTINEL", phase="novelty")
        plain = {item["id"]: item for item in memory.query("BIAS_SENTINEL")}
        self.assertEqual(plain[symmetry]["score"], plain[novelty]["score"])
        biased = memory.query("BIAS_SENTINEL", phase_bias="novelty")
        self.assertEqual(biased[0]["id"], novelty)
        self.assertGreater(biased[0]["score"], biased[1]["score"])
        for item in biased:
            self.assertIsNone(item["joy"])
            self.assertEqual(item["joy_status"], "not_measured")
        self.assertEqual(metadata_row(memory, symmetry), (None, None, None))
        self.assertEqual(metadata_row(memory, novelty), (None, None, None))

    def test_legacy_numeric_joy_never_controls_default_lexical_rank(self):
        memory = self.memory()
        strong = memory.store_episode("Better evidence", "alpha beta gamma", delta_coherence=0.0, effort=1.0)
        weak = memory.store_episode("Weaker evidence", "alpha", delta_coherence=9999.0, effort=0.0)
        results = memory.query("alpha beta gamma")
        self.assertEqual([item["id"] for item in results], [strong, weak])
        self.assertTrue(all(item["joy_status"] == "legacy_supplied" for item in results))
        self.assertEqual(results[0]["joy"], 0.0)
        self.assertEqual(results[1]["joy"], 9999.0)

    def test_query_empty_unknown_and_limit_remain_safe_with_null_records(self):
        memory = self.memory()
        for index in range(3):
            memory.store_episode(f"Record {index}", "LIMIT_SENTINEL")
        self.assertEqual(memory.query(""), [])
        self.assertEqual(memory.query("NO_MATCH_SENTINEL"), [])
        self.assertEqual(memory.query("LIMIT_SENTINEL", limit=0), [])
        self.assertEqual(len(memory.query("LIMIT_SENTINEL", limit=1)), 1)

    def test_episode_handler_parameters_cover_all_implemented_episode_actions(self):
        implemented = set(re.findall(r'(?:if|elif) action == "([^"]+)"', inspect.getsource(loop.execute_action)))
        self.assertEqual(implemented - {"rest", "journal", "inquire"}, set(EPISODE_ACTIONS))


class AutomaticHandlerMetadataTests(OfflineCase):
    """Run actual handlers, not a mocked execute_action or mocked store_episode."""


def _automatic_handler_test(action, llm_calls):
    def test(self):
        memory = self.memory()
        legacy_id = memory.store_episode(
            "LEGACY_BEFORE_ACTION", "Unchanged historical evidence", phase="break",
            delta_coherence=3.0, effort=2.0, tags=["legacy"],
        )
        legacy_before = full_episode_row(memory, legacy_id)
        marker = f"OFFLINE_AUTOMATIC_{action}"
        self.llm.return_value = marker
        if action == "browse_library":
            from core import library
            from unittest import mock
            source = {
                "document_id": "doc-111111111111", "section_id": "doc-111111111111-s00001",
                "title": "Offline source", "filename": "offline.md", "sha256": "1" * 64,
                "locator": "Markdown lines 1–2", "offset": 0, "next_offset": None,
                "truncated": False, "excerpt": "Source account for an optional interpretation.",
            }
            store = mock.Mock()
            store.search.return_value = {"status": "ok", "query": marker, "results": [source]}
            self.patch(library, "get_library", return_value=store)
        result = self.execute(action, phase=3)
        self.assertEqual(result["action"], action)
        self.assertNotEqual(result.get("status"), "unsupported_action")
        self.assertEqual(self.llm.call_count, llm_calls)
        episodes = memory.get_recent_episodes()
        self.assertEqual(len(episodes), 2)
        fresh = [episode for episode in episodes if episode["id"] != legacy_id]
        self.assertEqual(len(fresh), 1)
        if action == "browse_library":
            self.assertTrue(fresh[0]["content"].startswith(marker + "\nLibrary sources: "))
            self.assertIn("doc-111111111111-s00001", fresh[0]["content"])
        else:
            self.assertEqual(fresh[0]["content"], marker)
        self.assertEqual(metadata_row(memory, fresh[0]["id"]), (None, None, None))
        self.assertEqual(full_episode_row(memory, legacy_id), legacy_before)
        reopened = ThresholdMemory(memory.db_path)
        self.assertEqual(metadata_row(reopened, fresh[0]["id"]), (None, None, None))
        self.assertEqual(full_episode_row(reopened, legacy_id), legacy_before)
        retrieved = reopened.query(marker)
        self.assertEqual(len(retrieved), 1)
        self.assertIsNone(retrieved[0]["joy"])
        self.assertEqual(retrieved[0]["joy_status"], "not_measured")
        self.assertEqual(reopened.query("LEGACY_BEFORE_ACTION")[0]["joy"], 1.0)
        self.assertEqual(reopened.query("LEGACY_BEFORE_ACTION")[0]["joy_status"], "legacy_supplied")
        self.assertEqual(memory.read_journal(), [])
        self.broker.assert_not_called()
    test.__name__ = f"test_{action}_creates_sql_null_metadata_and_preserves_legacy"
    test.__doc__ = f"Real {action} handler writes no invented coherence, effort, or joy."
    return test


for _action, _llm_calls in EPISODE_ACTIONS.items():
    setattr(AutomaticHandlerMetadataTests,
            f"test_{_action}_creates_sql_null_metadata_and_preserves_legacy",
            _automatic_handler_test(_action, _llm_calls))
