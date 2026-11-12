"""All-seven preparation is offline metadata, not a launched scheduler."""
import ast
import sqlite3
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from core.runtime import cohort
from core.runtime.inquiry import AGENT_IDS, get_inquiry_receipt, run_inquiry
from core.trading.lineage import LineageConflict, LineageError, LineageStore


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(TemporaryDirectory(prefix="cohort-test-"))
        self.db = Path(self.temp) / "private" / "trade_queue.sqlite3"
        for target in ("socket.create_connection", "socket.socket.connect", "socket.socket.connect_ex", "urllib.request.urlopen"):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError("network forbidden")))
            self.addCleanup(guard.assert_not_called)

    def prepare(self, run_id="arrival-1", **kwargs):
        return cohort.prepare_cohort(run_id, db_path=self.db, **kwargs)

    def test_prepare_has_seven_distinct_stable_ids_common_arrival_phase_zero(self):
        arrival = "2026-11-12T15:00:00+00:00"
        result = self.prepare(arrival_at=arrival)
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["replayed"])
        self.assertEqual(len(result["wakes"]), 7)
        self.assertEqual({row["agent_id"] for row in result["wakes"]}, set(AGENT_IDS))
        self.assertEqual(len({row["wake_id"] for row in result["wakes"]}), 7)
        self.assertEqual({row["arrival_at"] for row in result["wakes"]}, {arrival})
        self.assertEqual({row["phase"] for row in result["wakes"]}, {0})
        self.assertEqual({row["cohort_id"] for row in result["wakes"]}, {result["cohort_id"]})
        self.assertEqual({row["status"] for row in result["wakes"]}, {"prepared"})
        for row in result["wakes"]:
            self.assertEqual(str(uuid.UUID(row["wake_id"])), row["wake_id"])
            self.assertEqual(row["operation_id"], row["wake_id"])
            self.assertIsNone(get_inquiry_receipt(row["agent_id"], row["wake_id"], db_path=self.db))
        replay = self.prepare(arrival_at=arrival)
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["wakes"], result["wakes"])
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)

    def test_preparation_starts_no_wakes_source_records_or_trading(self):
        self.prepare()
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohort_wakes").fetchone()[0], 7)
            for table in ("lineage_inquiries", "lineage_entries", "lineage_events", "lineage_operations",
                          "trade_queue", "lineage_proposals", "lineage_orders"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='inquiry_operations'").fetchone())
        source = Path(cohort.__file__).read_text()
        imports = [node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)]
        for name in imports:
            self.assertFalse(any(part in name for part in ("agent_loop", "scheduler", "alpaca", "broker", "memory", "config", "llm")), name)
        called = [node.func.id for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        for forbidden in ("run_inquiry", "agent_wake", "call_llm", "schedule", "submit_trade"):
            self.assertNotIn(forbidden, called)

    def test_default_arrival_has_no_volatile_timestamp_and_distinct_runs(self):
        first = self.prepare()
        replay = self.prepare()
        self.assertIsNone(first["arrival_at"])
        self.assertEqual(first["wakes"], replay["wakes"])
        other = self.prepare(run_id="arrival-2")
        self.assertNotEqual(first["cohort_id"], other["cohort_id"])
        self.assertFalse({row["wake_id"] for row in first["wakes"]} & {row["wake_id"] for row in other["wakes"]})

    def test_conflicting_arrival_reuse_is_rejected_and_preserves_original(self):
        first = self.prepare(arrival_at="2026-11-12T15:00:00+00:00")
        for arrival in (None, "2026-11-12T16:00:00+00:00"):
            with self.subTest(arrival=arrival), self.assertRaises(LineageConflict):
                self.prepare(arrival_at=arrival)
        replay = self.prepare(arrival_at=first["arrival_at"])
        self.assertEqual(first["wakes"], replay["wakes"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohorts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohort_wakes").fetchone()[0], 7)

    def test_invalid_parameters_fail_before_database_creation(self):
        for run_id in (None, True, "", " ", "x" * 201):
            with self.subTest(run_id=run_id), self.assertRaises(LineageError):
                self.prepare(run_id=run_id)
        for arrival in (False, 123, "", "not-a-date", "2026-11-12", "2026-11-12T15:00:00", "x" * 101):
            with self.subTest(arrival=arrival), self.assertRaises(LineageError):
                self.prepare(arrival_at=arrival)
        for path in (None, "", " ", ":memory:"):
            with self.subTest(path=path), self.assertRaises(LineageError):
                cohort.prepare_cohort("run", db_path=path)
        self.assertFalse(self.db.exists())

    def test_concurrent_preparation_deduplicates_same_run(self):
        with ThreadPoolExecutor(max_workers=7) as pool:
            results = list(pool.map(lambda _: self.prepare(), range(7)))
        self.assertEqual(sum(not result["replayed"] for result in results), 1)
        self.assertTrue(all(result["wakes"] == results[0]["wakes"] for result in results))
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohorts").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohort_wakes").fetchone()[0], 7)

    def test_all_seven_can_optionally_leave_alone_without_queue_entries(self):
        prepared = self.prepare()
        model = mock.Mock(return_value='{"operation":"none"}')
        for wake in prepared["wakes"]:
            result = run_inquiry(wake["agent_id"], wake["operation_id"], db_path=self.db, model_call=model)
            self.assertEqual(result["status"], "no_change")
        self.assertEqual(model.call_count, 7)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_commands").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_inquiries").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trade_queue").fetchone()[0], 0)

    def test_cohort_wake_ids_correlate_separate_private_owned_inquiries(self):
        prepared = self.prepare()
        for wake in prepared["wakes"]:
            result = run_inquiry(wake["agent_id"], wake["wake_id"], db_path=self.db,
                                 model_call=lambda _: '{"operation":"start","title":"Optional question"}')
            detail = LineageStore(self.db).get_inquiry(result["inquiry_id"], viewer_agent_id=wake["agent_id"])
            self.assertEqual(detail["inquiry"]["agent_id"], wake["agent_id"])
            self.assertEqual((detail["inquiry"]["phase"], detail["inquiry"]["visibility"]), (0, "owner"))
            receipt = get_inquiry_receipt(wake["agent_id"], wake["wake_id"], db_path=self.db)
            self.assertEqual(receipt["operation_id"], wake["wake_id"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lineage_inquiries").fetchone()[0], 7)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trade_queue").fetchone()[0], 0)

    def test_cohort_rows_are_immutable(self):
        prepared = self.prepare()
        with sqlite3.connect(self.db) as conn:
            for statement in ("UPDATE inquiry_cohorts SET parameters='{}'", "DELETE FROM inquiry_cohorts",
                              "UPDATE inquiry_cohort_wakes SET agent_id='other'", "DELETE FROM inquiry_cohort_wakes"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(statement)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT OR REPLACE INTO inquiry_cohorts (run_id,cohort_id,parameters) VALUES (?,?,?)",
                             (prepared["run_id"], prepared["cohort_id"], '{}'))
            wake = prepared["wakes"][0]
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT OR REPLACE INTO inquiry_cohort_wakes VALUES (?,?,?,0,NULL)",
                             (wake["cohort_id"], wake["agent_id"], wake["wake_id"]))

    def test_corrupt_stored_membership_is_not_invented_on_replay(self):
        prepared = self.prepare()
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TRIGGER inquiry_cohort_wakes_no_delete")
            conn.execute("DELETE FROM inquiry_cohort_wakes WHERE agent_id=?", (AGENT_IDS[0],))
        with self.assertRaises(LineageConflict):
            self.prepare()
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM inquiry_cohort_wakes WHERE cohort_id=?",
                                          (prepared["cohort_id"],)).fetchone()[0], 6)


if __name__ == "__main__":
    unittest.main()
