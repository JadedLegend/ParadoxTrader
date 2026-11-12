"""Persistent fictional venue tests; no network, provider config or real assets."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from uuid import UUID

from core.trading.mock_broker import BrokerConflict, BrokerUnavailable, MockBroker


def demo_structure(**changes):
    result = {"symbol": "DEMO270115C00100000", "underlying": "DEMO", "expiry": "2027-01-15",
              "option_type": "call", "strike": "100", "side": "buy", "intent": "open",
              "qty": 2, "order_type": "limit", "limit_price": "2.50", "multiplier": 100}
    result.update(changes)
    return result


class MockBrokerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "venue.sqlite3"
        self.network = mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.broker = MockBroker(self.path)

    def count(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT COUNT(*) FROM mock_venue_orders").fetchone()[0]

    def test_explicit_persistent_path_and_private_file(self):
        with self.assertRaises(TypeError):
            MockBroker()
        for path in ("", ":memory:", "file:venue?mode=memory"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                MockBroker(path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect(self.path) as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse(any("queue" in name or "approval" in name for name in names))

    def test_import_is_lazy_and_never_imports_provider_configuration(self):
        script = """
import sys
from unittest import mock
with mock.patch('sqlite3.connect', side_effect=AssertionError('database IO')), mock.patch('os.mkdir', side_effect=AssertionError('directory IO')), mock.patch('socket.socket', side_effect=AssertionError('network IO')):
    import core.trading.mock_broker
    import core.trading.lifecycle
assert not any(name in sys.modules for name in ('requests', 'core.trading.alpaca', 'core.runtime.config', 'core.runtime.agent_loop'))
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_acceptance_exact_snapshot_idempotent_normalized_payload_fresh_values(self):
        first = self.broker.submit_order("client-one", demo_structure())
        self.assertEqual(set(first), {"broker", "client_order_id", "broker_order_id", "status", "revision",
                                      "structure", "qty", "filled_qty", "fills", "created_at", "updated_at"})
        self.assertEqual(first["broker"], "mock")
        self.assertEqual(first["status"], "accepted")
        self.assertEqual((first["revision"], first["qty"], first["filled_qty"], first["fills"]), (1, 2, 0, []))
        self.assertTrue(first["created_at"].endswith("Z"))
        UUID(first["broker_order_id"])
        same = self.broker.submit_order("client-one", demo_structure(limit_price="2.500", strike="100.00"))
        self.assertEqual(first, same)
        same["structure"]["qty"] = 999
        same["fills"].append({"corrupted": True})
        self.assertEqual(self.broker.lookup_order("client-one"), first)
        with self.assertRaises(BrokerConflict):
            self.broker.submit_order("client-one", demo_structure(qty=3))
        self.assertEqual(self.count(), 1)

    def test_restart_recovers_real_orders_full_fill_history_and_durable_controls(self):
        self.broker.submit_order("durable", demo_structure())
        partial = self.broker.fill_order("durable", 1, Decimal("2.400"))
        self.broker.reject_next = True
        restarted = MockBroker(self.path)
        self.assertTrue(restarted.reject_next)
        self.assertEqual(restarted.lookup_order("durable"), partial)
        complete = restarted.fill_order("durable", 1, "2.50")
        self.assertEqual((complete["status"], complete["filled_qty"], complete["revision"]), ("filled", 2, 3))
        self.assertEqual(complete["fills"][0], partial["fills"][0])
        self.assertEqual(complete["fills"][0]["price"], "2.4")
        for fill in complete["fills"]:
            self.assertEqual(set(fill), {"fill_id", "qty", "price", "created_at"})
            UUID(fill["fill_id"])
        self.assertEqual(MockBroker(self.path).lookup_order("durable"), complete)

    def test_rejection_is_durable_consumed_once_and_has_no_fills(self):
        self.broker.reject_next = True
        rejected = MockBroker(self.path).submit_order("reject", demo_structure())
        self.assertEqual(rejected["status"], "rejected")
        self.assertFalse(self.broker.reject_next)
        self.assertEqual(self.broker.submit_order("reject", demo_structure()), rejected)
        self.assertEqual(self.broker.cancel_order("reject"), rejected)
        with self.assertRaises(BrokerConflict):
            self.broker.fill_order("reject", 1, "2.4")
        self.assertEqual(self.broker.submit_order("next", demo_structure())["status"], "accepted")

    def test_timeout_after_commit_keeps_same_identity_and_count_one(self):
        self.broker.fail_after_accept_once = True
        with self.assertRaises(BrokerUnavailable):
            self.broker.submit_order("ambiguous", demo_structure())
        restarted = MockBroker(self.path)
        self.assertFalse(restarted.fail_after_accept_once)
        confirmed = restarted.lookup_order("ambiguous")
        self.assertEqual(confirmed["status"], "accepted")
        self.assertEqual(restarted.submit_order("ambiguous", demo_structure()), confirmed)
        self.assertEqual(self.count(), 1)

    def test_outage_is_not_authoritative_absence_and_never_creates_an_order(self):
        self.broker.unavailable = True
        restarted = MockBroker(self.path)
        self.assertTrue(restarted.unavailable)
        for action in (lambda: restarted.lookup_order("absent"),
                       lambda: restarted.submit_order("absent", demo_structure()),
                       lambda: restarted.cancel_order("absent"),
                       lambda: restarted.fill_order("absent", 1, "2.4")):
            with self.assertRaises(BrokerUnavailable):
                action()
        self.assertEqual(self.count(), 0)
        restarted.unavailable = False
        self.assertIsNone(restarted.lookup_order("absent"))
        self.assertIsNone(restarted.cancel_order("absent"))

    def test_cancellation_preserves_partial_fill_and_cannot_erase_filled_order(self):
        self.broker.submit_order("partial", demo_structure())
        partial = self.broker.fill_order("partial", 1, "2.4")
        canceled = self.broker.cancel_order("partial")
        self.assertEqual((canceled["status"], canceled["filled_qty"], canceled["revision"]), ("canceled", 1, 3))
        self.assertEqual(canceled["fills"], partial["fills"])
        self.assertEqual(self.broker.cancel_order("partial"), canceled)
        with self.assertRaises(BrokerConflict):
            self.broker.fill_order("partial", 1, "2.4")
        self.broker.submit_order("full", demo_structure(qty=1))
        full = self.broker.fill_order("full", 1, "2.5")
        self.assertEqual(self.broker.cancel_order("full"), full)
        with self.assertRaises(BrokerConflict):
            self.broker.fill_order("full", 1, "2.5")

    def test_cancel_unfilled_acceptance_preserves_identity_and_empty_fill_history(self):
        accepted = self.broker.submit_order("unfilled", demo_structure())
        canceled = self.broker.cancel_order("unfilled")
        self.assertEqual((canceled["status"], canceled["revision"], canceled["filled_qty"], canceled["fills"]),
                         ("canceled", 2, 0, []))
        self.assertEqual(canceled["broker_order_id"], accepted["broker_order_id"])
        self.assertEqual(MockBroker(self.path).lookup_order("unfilled"), canceled)

    def test_decimal_and_string_prices_share_normalized_precision(self):
        self.broker.submit_order("precision", demo_structure())
        first = self.broker.fill_order("precision", 1, Decimal("2.4000000000"))
        second = self.broker.fill_order("precision", 1, "2.4000000000")
        self.assertEqual(first["fills"][0]["price"], "2.4")
        self.assertEqual(second["fills"][1]["price"], "2.4")

    def test_whole_contracts_finite_bounded_prices_limit_and_no_overfills(self):
        accepted = self.broker.submit_order("buy", demo_structure())
        for qty in (0, -1, True, 0.5, "1", 3):
            with self.subTest(qty=qty), self.assertRaises(BrokerConflict):
                self.broker.fill_order("buy", qty, "2.4")
        for price in ("0", "-1", "NaN", "Infinity", "1e0", "1000001", "0.000000001", 2.4, True, "2.51"):
            with self.subTest(price=price), self.assertRaises(BrokerConflict):
                self.broker.fill_order("buy", 1, price)
        self.assertEqual(self.broker.lookup_order("buy"), accepted)
        self.broker.submit_order("sell", demo_structure(side="sell", intent="close", limit_price="2.70"))
        with self.assertRaises(BrokerConflict):
            self.broker.fill_order("sell", 1, "2.69")
        self.assertEqual(self.broker.fill_order("sell", 2, "2.70")["status"], "filled")

    def test_unsupported_structure_never_persists_and_reject_flag_not_consumed(self):
        self.broker.reject_next = True
        invalid = [{}, demo_structure(qty=True), demo_structure(qty=0), demo_structure(qty=1.5),
                   demo_structure(side="sell", intent="open"), demo_structure(side="buy", intent="close"),
                   demo_structure(multiplier=1), demo_structure(strike="101"), demo_structure(underlying="REAL"),
                   demo_structure(expiry="2027-01-16"), demo_structure(option_type="put"),
                   demo_structure(order_type="market"), demo_structure(limit_price="NaN"),
                   demo_structure(authorization="approved"), demo_structure(limit_price="1e0")]
        for structure in invalid:
            with self.subTest(structure=structure), self.assertRaises(BrokerConflict):
                self.broker.submit_order("invalid", structure)
        self.assertEqual(self.count(), 0)
        self.assertTrue(self.broker.reject_next)

    def test_concurrent_identical_dispatches_are_one_venue_order(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: MockBroker(self.path).submit_order("same", demo_structure()), range(8)))
        self.assertTrue(all(snapshot == results[0] for snapshot in results))
        self.assertEqual(self.count(), 1)

    def test_database_fill_records_are_append_only(self):
        self.broker.submit_order("one", demo_structure())
        fill = self.broker.fill_order("one", 1, "2.4")["fills"][0]
        for query in ("DELETE FROM mock_venue_fills WHERE fill_id = ?", "UPDATE mock_venue_fills SET price = '1' WHERE fill_id = ?"):
            with sqlite3.connect(self.path) as conn, self.assertRaises(sqlite3.IntegrityError):
                conn.execute(query, (fill["fill_id"],))


if __name__ == "__main__":
    unittest.main()
