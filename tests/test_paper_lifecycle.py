"""One-agent offline lifecycle integration, including durable crash windows."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from core.trading.lineage.errors import LineageError
from core.trading.lineage.store import LineageStore
from core.trading.lifecycle import PaperLifecycle
from core.trading.mock_broker import BrokerConflict, BrokerUnavailable, MockBroker
from core.trading.queue import TradeQueue
from tests.test_mock_broker import demo_structure


class PaperLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "existing-trade-queue.sqlite3"
        self.venue_path = Path(self.tmp.name) / "external-mock.sqlite3"
        self.network = mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.store = LineageStore(self.path)
        self.broker = MockBroker(self.venue_path)
        self.service = PaperLifecycle(self.store, self.broker)
        self.inquiry = self.store.create_inquiry("alchemist", "Fictional options inquiry", operation_key="inquiry")
        self.queue = TradeQueue(self.path)
        self.sequence = 0

    def proposal(self, structure=None, *, approve=True, agent_id="alchemist", inquiry=None):
        self.sequence += 1
        proposal_id = self.store.create_proposal(inquiry or self.inquiry, agent_id, structure or demo_structure(),
                                                 thesis="Optional synthetic hypothesis, not execution evidence",
                                                 operation_key=f"proposal-{self.sequence}")
        proposal = self.store.get_proposal(proposal_id, agent_id)
        if approve:
            self.assertTrue(self.queue.approve(proposal["queue_id"], "Explicit test-operator approval"))
        return proposal_id

    def count(self, table, *, venue=False):
        with sqlite3.connect(self.venue_path if venue else self.path) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def detail(self):
        return self.store.get_inquiry(self.inquiry, viewer_agent_id="alchemist")

    def restart(self):
        self.store = LineageStore(self.path)
        self.broker = MockBroker(self.venue_path)
        self.service = PaperLifecycle(self.store, self.broker)

    def open_full(self):
        order = self.service.submit(self.proposal())
        self.broker.fill_order(order["client_order_id"], 1, "2.40")
        self.service.reconcile(order["order_id"])
        self.broker.fill_order(order["client_order_id"], 1, "2.50")
        return self.service.reconcile(order["order_id"])

    def _crash_submit(self, proposal_id, stage):
        script = """
import os
import sys
from unittest import mock
from core.trading.lineage.store import LineageStore
from core.trading.mock_broker import MockBroker
from core.trading.lifecycle import PaperLifecycle
with mock.patch('socket.socket', side_effect=AssertionError('network forbidden')):
    store = LineageStore(sys.argv[1])
    broker = MockBroker(sys.argv[2])
    def crash(*args):
        os._exit(23)
    if sys.argv[4] == 'before_dispatch':
        broker.lookup_order = crash
    else:
        store.apply_snapshot = crash
    PaperLifecycle(store, broker).submit(sys.argv[3])
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.path), str(self.venue_path), proposal_id, stage],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 23, result.stderr)

    def test_hard_process_exit_before_dispatch_leaves_reusable_durable_intent(self):
        proposal_id = self.proposal()
        self._crash_submit(proposal_id, "before_dispatch")
        self.assertEqual(self.count("lineage_orders"), 1)
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)
        intent = self.store.prepare_order(proposal_id, "alchemist")
        self.assertEqual((intent["status"], intent["broker_revision"]), ("pending_submission", 0))
        self.restart()
        accepted = self.service.submit(proposal_id)
        self.assertEqual((accepted["order_id"], accepted["client_order_id"]), (intent["order_id"], intent["client_order_id"]))
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)

    def test_hard_process_exit_after_venue_acceptance_recovers_without_dispatch(self):
        proposal_id = self.proposal()
        self._crash_submit(proposal_id, "after_acceptance")
        self.assertEqual(self.count("lineage_orders"), 1)
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)
        intent = self.store.prepare_order(proposal_id, "alchemist")
        self.assertEqual((intent["status"], intent["broker_revision"]), ("pending_submission", 0))
        self.restart()
        with mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("duplicate after crash")):
            recovered = self.service.reconcile(intent["order_id"])
        self.assertEqual((recovered["status"], recovered["sync_state"]), ("accepted", "ok"))
        self.assertEqual(recovered["client_order_id"], intent["client_order_id"])
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)

    def test_unapproved_rejected_other_agent_and_nonmock_denied_without_dispatch(self):
        unapproved = self.proposal(approve=False)
        with mock.patch.object(self.broker, "lookup_order", side_effect=AssertionError("must not look up")), \
                mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("must not dispatch")):
            with self.assertRaises(LineageError):
                self.service.submit(unapproved)
        self.assertEqual(self.count("lineage_orders"), 0)
        self.assertTrue(self.queue.reject(self.store.get_proposal(unapproved, "alchemist")["queue_id"]))
        with self.assertRaises(LineageError):
            self.service.submit(unapproved)
        other = self.store.create_inquiry("tempest", "Private other agent", operation_key="other")
        disallowed = self.proposal(agent_id="tempest", inquiry=other)
        with self.assertRaises(LineageError):
            self.service.submit(disallowed)
        with self.assertRaises(LineageError):
            PaperLifecycle(self.store, object())
        with self.assertRaises(LineageError):
            PaperLifecycle(self.store, self.broker, agent_id="tempest")
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)

    def test_intent_committed_before_any_broker_lookup_or_dispatch(self):
        proposal_id = self.proposal()
        original_lookup = self.broker.lookup_order
        original_submit = self.broker.submit_order
        seen = []

        def verify_lookup(client_id):
            durable = LineageStore(self.path).prepare_order(proposal_id, "alchemist")
            self.assertEqual(client_id, durable["client_order_id"])
            self.assertEqual(durable["status"], "pending_submission")
            seen.append("lookup")
            return original_lookup(client_id)

        def verify_submit(client_id, structure):
            durable = LineageStore(self.path).prepare_order(proposal_id, "alchemist")
            self.assertEqual((client_id, structure), (durable["client_order_id"], durable["structure"]))
            seen.append("submit")
            return original_submit(client_id, structure)

        with mock.patch.object(self.broker, "lookup_order", side_effect=verify_lookup), \
                mock.patch.object(self.broker, "submit_order", side_effect=verify_submit):
            order = self.service.submit(proposal_id)
        self.assertEqual(seen, ["lookup", "submit"])
        self.assertEqual((order["status"], order["sync_state"], order["broker"]), ("accepted", "ok", "mock"))
        self.assertEqual(self.count("lineage_orders"), 1)
        self.assertEqual(self.count("lineage_positions"), 0)
        self.assertEqual(self.count("lineage_fills"), 0)

    def test_timeout_after_acceptance_restart_same_client_id_count_one(self):
        proposal_id = self.proposal()
        self.broker.fail_after_accept_once = True
        unknown = self.service.submit(proposal_id)
        self.assertEqual((unknown["status"], unknown["sync_state"]), ("submission_unknown", "submission_unknown"))
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)
        self.restart()
        with mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("duplicate dispatch")):
            confirmed = self.service.submit(proposal_id)
        self.assertEqual(confirmed["client_order_id"], unknown["client_order_id"])
        self.assertEqual((confirmed["status"], confirmed["sync_state"]), ("accepted", "ok"))
        self.assertEqual(self.service.reconcile(confirmed["order_id"]), confirmed)
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)

    def test_lookup_outage_retains_durable_intent_and_never_posts(self):
        proposal_id = self.proposal()
        self.broker.unavailable = True
        with mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("outage is not absence")):
            issue = self.service.submit(proposal_id)
        self.assertEqual(issue["sync_state"], "unavailable")
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)
        self.assertEqual(self.count("lineage_orders"), 1)
        self.broker.unavailable = False
        accepted = self.service.submit(proposal_id)
        self.assertEqual(accepted["client_order_id"], issue["client_order_id"])
        self.assertEqual(accepted["status"], "accepted")

    def test_failure_before_persistence_authoritative_absence_retries_same_id(self):
        proposal_id = self.proposal()
        with mock.patch.object(self.broker, "submit_order", side_effect=BrokerUnavailable("SENSITIVE MOCK ERROR")):
            unknown = self.service.submit(proposal_id)
        self.assertEqual(unknown["sync_state"], "submission_unknown")
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)
        self.restart()
        self.assertIsNone(self.broker.lookup_order(unknown["client_order_id"]))
        confirmed = self.service.submit(proposal_id)
        self.assertEqual((confirmed["order_id"], confirmed["client_order_id"]), (unknown["order_id"], unknown["client_order_id"]))
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)
        self.assertNotIn("SENSITIVE MOCK ERROR", str(self.detail()))

    def test_reconcile_never_creates_or_dispatches_on_authoritative_absence(self):
        prepared = self.store.prepare_order(self.proposal(), "alchemist")
        with mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("read-only reconciliation")):
            unknown = self.service.reconcile(prepared["order_id"])
        self.assertEqual(unknown["sync_state"], "submission_unknown")
        self.assertEqual(unknown["client_order_id"], prepared["client_order_id"])
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)

    def test_confirmed_order_disappearance_is_unknown_never_a_second_submission(self):
        proposal_id = self.proposal()
        accepted = self.service.submit(proposal_id)
        with mock.patch.object(self.broker, "lookup_order", return_value=None), \
                mock.patch.object(self.broker, "submit_order", side_effect=AssertionError("confirmed order disappeared")):
            unknown = self.service.submit(proposal_id)
        self.assertEqual((unknown["status"], unknown["sync_state"]), ("accepted", "submission_unknown"))
        self.assertEqual(unknown["broker_order_id"], accepted["broker_order_id"])
        self.assertEqual(self.count("mock_venue_orders", venue=True), 1)

    def test_venue_rejection_is_confirmed_and_does_not_create_a_holding(self):
        self.broker.reject_next = True
        order = self.service.submit(self.proposal())
        self.assertEqual((order["status"], order["sync_state"]), ("rejected", "ok"))
        self.assertEqual(self.service.cancel(order["order_id"]), order)
        self.assertEqual(self.count("lineage_positions"), 0)
        self.assertEqual(self.count("lineage_fills"), 0)

    def test_full_open_partial_restart_close_one_position_and_optional_review(self):
        self.store.add_entry(self.inquiry, "alchemist", "observation", "Synthetic observation", operation_key="observation")
        opening = self.service.submit(self.proposal())
        self.assertEqual(self.detail()["positions"], [])
        first = self.broker.fill_order(opening["client_order_id"], 1, "2.40")
        partial = self.service.reconcile(opening["order_id"])
        first_detail = self.detail()
        position_id = first_detail["positions"][0]["position_id"]
        self.assertEqual((partial["status"], partial["filled_qty"]), ("partially_filled", 1))
        self.assertEqual(first_detail["positions"][0]["qty"], 1)
        self.restart()
        self.assertEqual(self.service.reconcile(opening["order_id"])["filled_qty"], 1)
        completed = self.broker.fill_order(opening["client_order_id"], 1, "2.50")
        self.assertEqual(first["fills"][0], completed["fills"][0])
        self.assertEqual(self.service.reconcile(opening["order_id"])["status"], "filled")
        closing = self.service.submit(self.proposal(demo_structure(side="sell", intent="close", limit_price="2.70")))
        self.broker.fill_order(closing["client_order_id"], 1, "2.70")
        self.assertEqual(self.service.reconcile(closing["order_id"])["status"], "partially_filled")
        self.restart()
        self.broker.fill_order(closing["client_order_id"], 1, "2.70")
        final = self.service.reconcile(closing["order_id"])
        self.assertEqual((final["status"], final["filled_qty"]), ("filled", 2))
        self.assertEqual(self.service.cancel(final["order_id"])["status"], "filled")
        self.assertEqual(self.service.reconcile(final["order_id"])["status"], "filled")
        detail = self.detail()
        self.assertEqual(len(detail["positions"]), 1)
        position = detail["positions"][0]
        self.assertEqual((position["position_id"], position["qty"], position["status"]), (position_id, 0, "closed"))
        expected_gross = (Decimal("2.70") * 2 - Decimal("2.40") - Decimal("2.50")) * 100
        self.assertEqual(Decimal(position["gross_realized_pnl"]), expected_gross)
        for key in ("fees", "market_value", "unrealized_pnl"):
            self.assertIsNone(position[key])
        self.assertEqual(position["mark_status"], "unavailable")
        self.assertEqual(position["multiplier"], 100)
        self.assertEqual(len(detail["fills"]), 4)
        self.assertEqual({fill["authority"] for fill in detail["fills"]}, {"mock_broker"})
        review = self.store.add_review(self.inquiry, "alchemist", "Optional later interpretation; not broker evidence",
                                      proposal_id=closing["proposal_id"], order_id=closing["order_id"], position_id=position_id,
                                      operation_key="optional-review")
        self.assertEqual(self.detail()["reviews"][0]["review_id"], review)
        self.assertEqual(self.count("mock_venue_orders", venue=True), 2)

    def test_cancel_partial_preserves_holding_and_outage_preserves_confirmed_state(self):
        order = self.service.submit(self.proposal())
        self.broker.fill_order(order["client_order_id"], 1, "2.4")
        partial = self.service.reconcile(order["order_id"])
        self.broker.unavailable = True
        with mock.patch.object(self.broker, "cancel_order", side_effect=AssertionError("outage cannot cancel")):
            unavailable = self.service.cancel(order["order_id"])
        for key in ("status", "filled_qty", "broker_order_id", "broker_revision"):
            self.assertEqual(unavailable[key], partial[key])
        self.assertEqual(unavailable["sync_state"], "unavailable")
        self.broker.unavailable = False
        canceled = self.service.cancel(order["order_id"])
        self.assertEqual((canceled["status"], canceled["filled_qty"]), ("canceled", 1))
        self.assertEqual(self.detail()["positions"][0]["qty"], 1)
        self.assertEqual(len(self.detail()["fills"]), 1)

    def test_cancel_missing_and_timeout_never_erase_fills(self):
        order = self.service.submit(self.proposal())
        self.broker.fill_order(order["client_order_id"], 1, "2.4")
        partial = self.service.reconcile(order["order_id"])
        with mock.patch.object(self.broker, "lookup_order", return_value=None), \
                mock.patch.object(self.broker, "cancel_order", side_effect=AssertionError("not found cannot cancel")):
            missing = self.service.cancel(order["order_id"])
        self.assertEqual((missing["status"], missing["filled_qty"], missing["sync_state"]), ("partially_filled", 1, "submission_unknown"))
        original = self.broker.cancel_order

        def timeout(client_id):
            original(client_id)
            raise TimeoutError("SECRET cancel acknowledgement")

        with mock.patch.object(self.broker, "cancel_order", side_effect=timeout):
            unknown = self.service.cancel(order["order_id"])
        self.assertEqual((unknown["status"], unknown["filled_qty"], unknown["sync_state"]), (partial["status"], 1, "submission_unknown"))
        self.restart()
        confirmed = self.service.reconcile(order["order_id"])
        self.assertEqual((confirmed["status"], confirmed["filled_qty"], confirmed["sync_state"]), ("canceled", 1, "ok"))
        self.assertEqual(self.detail()["positions"][0]["qty"], 1)
        self.assertNotIn("SECRET cancel", str(self.detail()))

    def test_fill_commit_failure_rolls_back_fills_position_pnl_retry_idempotent(self):
        self.open_full()
        closing = self.service.submit(self.proposal(demo_structure(side="sell", intent="close", limit_price="2.70")))
        self.broker.fill_order(closing["client_order_id"], 1, "2.70")
        partial = self.service.reconcile(closing["order_id"])
        before = deepcopy(self.detail())
        self.broker.fill_order(closing["client_order_id"], 1, "2.70")
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TRIGGER synthetic_local_commit_failure AFTER INSERT ON lineage_fills BEGIN SELECT RAISE(ABORT, 'SECRET transaction failure'); END")
        failed = self.service.reconcile(closing["order_id"])
        self.assertEqual(failed["sync_state"], "failed")
        self.assertEqual((failed["status"], failed["filled_qty"], failed["broker_revision"]),
                         (partial["status"], partial["filled_qty"], partial["broker_revision"]))
        after = self.detail()
        self.assertEqual(after["positions"], before["positions"])
        self.assertEqual(after["fills"], before["fills"])
        self.assertNotIn("SECRET transaction failure", str(after))
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TRIGGER synthetic_local_commit_failure")
        self.restart()
        confirmed = self.service.reconcile(closing["order_id"])
        self.assertEqual((confirmed["status"], confirmed["filled_qty"]), ("filled", 2))
        stable = deepcopy(self.detail())
        self.service.reconcile(closing["order_id"])
        self.assertEqual(self.detail(), stable)
        self.assertEqual(len(stable["fills"]), 4)
        expected = (Decimal("2.70") * 2 - Decimal("2.40") - Decimal("2.50")) * 100
        self.assertEqual(Decimal(stable["positions"][0]["gross_realized_pnl"]), expected)

    def test_invalid_snapshots_fail_without_partial_application_or_raw_errors(self):
        order = self.service.submit(self.proposal())
        baseline = deepcopy(self.detail())
        valid = self.broker.fill_order(order["client_order_id"], 1, "2.4")
        cases = []
        for field, bad in (("broker", "live"), ("client_order_id", "wrong"), ("broker_order_id", "wrong"),
                           ("qty", True), ("filled_qty", 2), ("revision", 0), ("status", "filled"),
                           ("created_at", "invalid")):
            invalid = deepcopy(valid)
            invalid[field] = bad
            cases.append(invalid)
        invalid = deepcopy(valid)
        invalid["fills"][0]["price"] = "NaN"
        cases.append(invalid)
        invalid = deepcopy(valid)
        invalid["fills"].append(deepcopy(invalid["fills"][0]))
        cases.append(invalid)
        for snapshot in cases:
            with self.subTest(snapshot=snapshot), mock.patch.object(self.broker, "lookup_order", return_value=snapshot), \
                    mock.patch.object(self.store, "apply_snapshot", side_effect=AssertionError("invalid evidence reached store")) as apply:
                failed = self.service.reconcile(order["order_id"])
                self.assertEqual(failed["sync_state"], "failed")
                apply.assert_not_called()
                self.assertEqual(self.detail()["fills"], baseline["fills"])
                self.assertEqual(self.detail()["positions"], baseline["positions"])
        self.assertEqual(self.service.reconcile(order["order_id"])["filled_qty"], 1)

    def test_stale_and_equal_revision_reconciliation_and_changed_fill_rejected(self):
        order = self.service.submit(self.proposal())
        first = self.broker.fill_order(order["client_order_id"], 1, "2.4")
        self.service.reconcile(order["order_id"])
        second = self.broker.fill_order(order["client_order_id"], 1, "2.5")
        final = self.service.reconcile(order["order_id"])
        with mock.patch.object(self.broker, "lookup_order", return_value=first):
            stale = self.service.reconcile(order["order_id"])
        self.assertEqual((stale["status"], stale["filled_qty"], stale["broker_revision"]), ("filled", 2, final["broker_revision"]))
        self.assertEqual(self.service.reconcile(order["order_id"])["status"], "filled")
        changed = deepcopy(second)
        changed["revision"] += 1
        changed["fills"][0]["price"] = "2.3"
        with mock.patch.object(self.broker, "lookup_order", return_value=changed):
            failed = self.service.reconcile(order["order_id"])
        self.assertEqual((failed["sync_state"], failed["filled_qty"]), ("failed", 2))
        self.assertEqual(len(self.detail()["fills"]), 2)

    def test_close_holds_prevent_overselling_unknown_and_partial_orders(self):
        self.open_full()
        close_structure = demo_structure(side="sell", intent="close", limit_price="2.70")
        first_proposal = self.proposal(close_structure)
        self.broker.unavailable = True
        first = self.service.submit(first_proposal)
        self.assertEqual(first["sync_state"], "unavailable")
        second = self.proposal(demo_structure(side="sell", intent="close", limit_price="2.70", qty=1))
        with self.assertRaises(LineageError):
            self.service.submit(second)
        self.broker.unavailable = False
        first = self.service.submit(first_proposal)
        self.broker.fill_order(first["client_order_id"], 1, "2.70")
        self.service.reconcile(first["order_id"])
        with self.assertRaises(LineageError):
            self.service.submit(second)
        self.service.cancel(first["order_id"])
        released = self.service.submit(second)
        self.assertEqual(released["status"], "accepted")
        self.assertEqual(self.detail()["positions"][0]["qty"], 1)

    def test_close_without_confirmed_holdings_is_not_dispatched(self):
        proposal_id = self.proposal(demo_structure(side="sell", intent="close", limit_price="2.70"))
        with self.assertRaises(LineageError):
            self.service.submit(proposal_id)
        self.assertEqual(self.count("lineage_orders"), 0)
        self.assertEqual(self.count("mock_venue_orders", venue=True), 0)

    def test_broker_conflict_is_failed_not_fictional_rejection(self):
        proposal_id = self.proposal()
        with mock.patch.object(self.broker, "submit_order", side_effect=BrokerConflict("SECRET invalid request")):
            failed = self.service.submit(proposal_id)
        self.assertEqual((failed["status"], failed["sync_state"]), ("pending_submission", "failed"))
        self.assertEqual(self.count("lineage_positions"), 0)
        self.assertNotIn("SECRET invalid", str(self.detail()))


if __name__ == "__main__":
    unittest.main()
