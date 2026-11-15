"""Offline tests for the one existing approval queue and additive linkage."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.trading.queue import QUEUE_DB, TradeQueue, ensure_queue_schema
from core.trading.lineage import LineageConflict, LineageStore


def structure(qty=2, side="buy", price="3"):
    return {"symbol": "DEMO270115C00100000", "underlying": "DEMO", "expiry": "2027-01-15",
            "option_type": "call", "strike": "100", "side": side,
            "intent": "open" if side == "buy" else "close", "qty": qty,
            "order_type": "limit", "limit_price": price, "multiplier": 100}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "queue.sqlite3"
        self.network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def linked(self):
        store = LineageStore(self.db)
        inquiry = store.create_inquiry("alchemist", "optional idea", operation_key="inquiry")
        proposal = store.create_proposal(inquiry, "alchemist", structure(), operation_key="proposal")
        return store, inquiry, proposal, store.get_proposal(proposal, "alchemist")["queue_id"]

    def test_root_path_unchanged_and_alpaca_reexports(self):
        root = Path(__file__).resolve().parents[1]
        # QUEUE_DB follows DATA_DIR like every other store; with DATA_DIR unset
        # that is still <repo>/data, so existing local queues are not moved.
        from core.trading.queue import _queue_dir
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATA_DIR", None)
            self.assertEqual(_queue_dir(), root / "data")
        with patch.dict(os.environ, {"DATA_DIR": "/srv/paradox"}):
            self.assertEqual(_queue_dir(), Path("/srv/paradox"))
        source = (root / "core/trading/alpaca.py").read_text()
        self.assertIn("from core.trading.queue import QUEUE_DB, QUEUE_SCHEMA, TradeQueue", source)
        queue_source = (root / "core/trading/queue.py").read_text()
        self.assertNotIn("import requests", queue_source)
        self.assertNotIn("core.data_dir", queue_source)  # it creates directories at import
        self.assertNotIn("core.runtime", queue_source)

    def test_legacy_migration_preserves_rows_and_shape(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE trade_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, "
                         "proposal TEXT NOT NULL, status TEXT DEFAULT 'pending', reviewer_notes TEXT, "
                         "created_at TEXT NOT NULL, reviewed_at TEXT)")
            conn.execute("INSERT INTO trade_queue VALUES (17,'old_agent',?,'pending',NULL,'old-time',NULL)",
                         (json.dumps({"symbol": "LEGACY", "qty": 1}),))
            before = conn.execute("SELECT * FROM trade_queue").fetchall()
        queue = TradeQueue(self.db)
        with sqlite3.connect(self.db) as conn:
            ensure_queue_schema(conn)
            self.assertEqual(conn.execute("SELECT id,agent_id,proposal,status,reviewer_notes,created_at,reviewed_at FROM trade_queue").fetchall(), before)
            self.assertIsNone(conn.execute("SELECT lineage_proposal_id FROM trade_queue").fetchone()[0])
        self.assertEqual(queue.get_pending(), [{"id": 17, "agent_id": "old_agent", "proposal": {"symbol": "LEGACY", "qty": 1},
                                                "status": "pending", "created_at": "old-time"}])
        self.assertTrue(queue.approve(17, "old approved"))
        self.assertTrue(queue.reject(17, "legacy overwrite remains"))
        self.assertTrue(queue.approve(987654))
        self.assertEqual(queue.get_entry(17)["reviewer_notes"], "legacy overwrite remains")
        self.assertIsNone(queue.get_entry(987654))

    def test_legacy_enqueue_and_unguarded_list_excludes_linkage(self):
        store, inquiry, proposal, queue_id = self.linked()
        queue = TradeQueue(self.db)
        legacy_id = queue.enqueue("legacy", {"symbol": "OLD"})
        self.assertEqual([item["id"] for item in queue.get_pending()], [legacy_id])
        self.assertEqual({item["id"] for item in queue.get_pending(include_lineage=True)}, {queue_id, legacy_id})
        linked = queue.get_entry(queue_id)
        self.assertEqual(linked["lineage_proposal_id"], proposal)
        self.assertEqual(linked["proposal"]["mode"], "mock")
        self.assertEqual(store.get_inquiry(inquiry, viewer_agent_id="alchemist")["orders"], [])

    def test_linked_approval_idempotent_and_no_autosubmission(self):
        store, inquiry, proposal, queue_id = self.linked()
        queue = TradeQueue(self.db)
        self.assertTrue(queue.approve(queue_id, "operator approved"))
        original = queue.get_entry(queue_id)
        self.assertTrue(queue.approve(queue_id, "must not overwrite"))
        self.assertEqual(queue.get_entry(queue_id), original)
        self.assertFalse(queue.reject(queue_id, "conflicting reversal"))
        detail = store.get_inquiry(inquiry, viewer_agent_id="alchemist")
        events = [event for event in detail["events"] if event["kind"] == "proposal_reviewed"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["review_status"], "approved")
        self.assertEqual(events[0]["payload"]["source"], "operator")
        self.assertEqual(detail["orders"], [])
        self.assertEqual(detail["positions"], [])
        self.assertEqual(store.get_proposal(proposal, "alchemist")["review_status"], "approved")

    def test_linked_notes_bounded_and_legacy_notes_unchanged(self):
        store, inquiry, proposal, queue_id = self.linked()
        queue = TradeQueue(self.db)
        self.assertFalse(queue.approve(queue_id, "x" * 2001))
        self.assertFalse(queue.approve(queue_id, {"messages": ["private"]}))
        self.assertEqual(queue.get_entry(queue_id)["status"], "pending")
        self.assertTrue(queue.approve(queue_id, "x" * 2000))
        legacy_id = queue.enqueue("legacy", {"symbol": "OLD"})
        self.assertTrue(queue.approve(legacy_id, "x" * 2001))
        self.assertEqual(len(queue.get_entry(legacy_id)["reviewer_notes"]), 2001)

    def test_linked_rejection_cannot_reapprove_or_prepare(self):
        store, inquiry, proposal, queue_id = self.linked()
        queue = TradeQueue(self.db)
        self.assertTrue(queue.reject(queue_id, "not proceeding"))
        original = queue.get_entry(queue_id)
        self.assertTrue(queue.reject(queue_id, "new note ignored"))
        self.assertFalse(queue.approve(queue_id))
        self.assertEqual(queue.get_entry(queue_id), original)
        with self.assertRaises(LineageConflict):
            store.prepare_order(proposal, "alchemist")

    def test_linked_review_event_failure_rolls_back_queue(self):
        store, inquiry, proposal, queue_id = self.linked()
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TRIGGER fail_review BEFORE INSERT ON lineage_events "
                         "WHEN NEW.kind='proposal_reviewed' BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        queue = TradeQueue(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            queue.approve(queue_id)
        self.assertEqual(queue.get_entry(queue_id)["status"], "pending")
        self.assertFalse(any(e["kind"] == "proposal_reviewed" for e in store.get_inquiry(inquiry, viewer_agent_id="alchemist")["events"]))

    def test_linkage_unique_and_proposal_failure_rolls_back_queue(self):
        store = LineageStore(self.db)
        inquiry = store.create_inquiry("alchemist", "idea", operation_key="inquiry")
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TRIGGER fail_proposal BEFORE INSERT ON lineage_proposals "
                         "BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        with self.assertRaises(LineageConflict):
            store.create_proposal(inquiry, "alchemist", structure(), operation_key="proposal")
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM trade_queue").fetchone()[0], 0)
            conn.execute("DROP TRIGGER fail_proposal")
        proposal = store.create_proposal(inquiry, "alchemist", structure(), operation_key="proposal")
        with sqlite3.connect(self.db) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO trade_queue(agent_id,proposal,created_at,lineage_proposal_id) VALUES ('alchemist','{}','x',?)", (proposal,))

    def test_corrupt_cross_owner_queue_linkage_is_not_reviewed(self):
        store, inquiry, proposal, queue_id = self.linked()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE trade_queue SET agent_id='other' WHERE id=?", (queue_id,))
        queue = TradeQueue(self.db)
        self.assertFalse(queue.approve(queue_id))
        self.assertEqual(queue.get_entry(queue_id)["status"], "pending")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE trade_queue SET status='approved' WHERE id=?", (queue_id,))
        self.assertFalse(queue.approve(queue_id))


if __name__ == "__main__":
    unittest.main()
