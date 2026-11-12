"""No providers, sockets, account configuration, journals, or services required."""
import copy
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from core.trading.lineage import (LineageAccessError, LineageConflict, LineageError,
                                  LineageNotFound, LineageStore, get_default_lineage_store)
from core.trading.queue import QUEUE_DB, TradeQueue
from tests.test_lineage_queue import structure

T0 = "2026-11-01T00:00:00+00:00"
T1 = "2026-11-01T00:01:00+00:00"


def fill(fill_id, qty=1, price="2", created_at=T1):
    return {"fill_id": fill_id, "qty": qty, "price": price, "created_at": created_at}


def snapshot(order, revision=1, status="accepted", fills=None):
    fills = [] if fills is None else fills
    return {"broker": "mock", "client_order_id": order["client_order_id"],
            "broker_order_id": "broker-" + order["order_id"], "status": status, "revision": revision,
            "structure": copy.deepcopy(order["structure"]), "qty": order["qty"],
            "filled_qty": sum(item["qty"] for item in fills), "fills": copy.deepcopy(fills),
            "created_at": T0, "updated_at": T1}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "nested" / "trade_queue.sqlite3"
        self.store = LineageStore(self.db)
        self.counter = 0
        self.network = patch("socket.socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def key(self):
        self.counter += 1
        return f"op-{self.counter}"

    def inquiry(self, agent="alchemist", **kwargs):
        return self.store.create_inquiry(agent, "An optional idea", operation_key=self.key(), **kwargs)

    def proposal(self, inquiry=None, qty=2, side="buy", price="3", agent="alchemist", approve=True):
        inquiry = self.inquiry(agent) if inquiry is None else inquiry
        proposal = self.store.create_proposal(inquiry, agent, structure(qty, side, price),
                                              thesis="fictional thesis", horizon="weeks", uncertainty="unknown", operation_key=self.key())
        if approve:
            TradeQueue(self.db).approve(self.store.get_proposal(proposal, agent)["queue_id"], "offline operator")
        return inquiry, proposal

    def order(self, inquiry=None, qty=2, side="buy", price="3", agent="alchemist"):
        inquiry, proposal = self.proposal(inquiry, qty, side, price, agent)
        return inquiry, self.store.prepare_order(proposal, agent)

    def detail(self, inquiry, agent="alchemist", **kwargs):
        return self.store.get_inquiry(inquiry, viewer_agent_id=agent, **kwargs)

    def open_position(self, qty=2, price="2", inquiry=None):
        inquiry, order = self.order(inquiry, qty=qty)
        self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, status="filled", fills=[fill("open-" + order["order_id"], qty, price)]))
        return inquiry, order, self.detail(inquiry)["positions"][0]

    def test_construction_default_and_unauthenticated_reads_are_lazy(self):
        self.assertFalse(self.db.exists())
        default = get_default_lineage_store()
        self.assertEqual(default.db_path, str(QUEUE_DB))
        with self.assertRaises(LineageAccessError):
            self.store.list_inquiries("alchemist")
        with self.assertRaises(LineageAccessError):
            self.store.get_inquiry("anything")
        self.assertFalse(self.db.exists())

    def test_new_database_private_existing_permissions_not_rewritten(self):
        self.inquiry()
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        self.db.chmod(0o640)
        self.inquiry()
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o640)
        queue_db = Path(self.temp.name) / "new-queue.sqlite3"
        TradeQueue(queue_db)
        self.assertEqual(queue_db.stat().st_mode & 0o777, 0o600)

    def test_inquiry_idempotency_survives_restart_and_conflicts(self):
        inquiry = self.store.create_inquiry("alchemist", "same", operation_key="same")
        restarted = LineageStore(self.db)
        self.assertEqual(restarted.create_inquiry("alchemist", "same", operation_key="same"), inquiry)
        with self.assertRaises(LineageConflict):
            restarted.create_inquiry("alchemist", "different", operation_key="same")
        other = restarted.create_inquiry("other", "same", operation_key="same")
        self.assertNotEqual(other, inquiry)
        self.assertEqual(len(self.detail(inquiry)["events"]), 1)

    def test_optional_entries_pause_abandon_and_revisit_do_not_order(self):
        inquiry = self.inquiry()
        entry = self.store.add_entry(inquiry, "alchemist", "observation", "explicit observation", source="external", operation_key="entry")
        self.assertEqual(LineageStore(self.db).add_entry(inquiry, "alchemist", "observation", "explicit observation", source="external", operation_key="entry"), entry)
        self.store.add_entry(inquiry, "alchemist", "interpretation", "a tentative view", source="agent", operation_key="interpretation")
        self.store.set_inquiry_state(inquiry, "alchemist", "paused", reason="optional pause", operation_key="paused")
        self.store.set_inquiry_state(inquiry, "alchemist", "abandoned", operation_key="abandoned")
        event = self.store.set_inquiry_state(inquiry, "alchemist", "open", reason="revisit", operation_key="revisited")
        self.assertEqual(LineageStore(self.db).set_inquiry_state(inquiry, "alchemist", "open", reason="revisit", operation_key="revisited"), event)
        detail = self.detail(inquiry)
        self.assertEqual(detail["inquiry"]["state"], "open")
        self.assertEqual([entry["content"] for entry in detail["entries"]], ["explicit observation", "a tentative view"])
        self.assertIn("inquiry_revisited", [event["kind"] for event in detail["events"]])
        self.assertEqual(detail["proposals"], [])
        self.assertEqual(detail["orders"], [])

    def test_operation_keys_scope_all_kinds_and_never_overwrite(self):
        inquiry = self.inquiry()
        entry = self.store.add_entry(inquiry, "alchemist", "observation", "first", operation_key="global-key")
        with self.assertRaises(LineageConflict):
            self.store.add_entry(inquiry, "alchemist", "observation", "changed", operation_key="global-key")
        with self.assertRaises(LineageConflict):
            self.store.set_inquiry_state(inquiry, "alchemist", "paused", operation_key="global-key")
        self.assertEqual(self.detail(inquiry)["entries"][0]["entry_id"], entry)
        self.assertEqual(self.detail(inquiry)["entries"][0]["content"], "first")

    def test_structured_private_fields_and_unknown_sources_rejected(self):
        inquiry = self.inquiry()
        for payload in ({"messages": ["private"]}, ["journal"], None):
            with self.subTest(payload=payload), self.assertRaises(LineageError):
                self.store.add_entry(inquiry, "alchemist", "observation", payload, operation_key=self.key())
        with self.assertRaises(LineageError):
            self.store.add_entry(inquiry, "alchemist", "observation", "explicit", source="journal", operation_key=self.key())
        with self.assertRaises(LineageError):
            self.store.add_review(inquiry, "alchemist", {"config": "private"}, operation_key=self.key())
        invalid = structure()
        invalid["messages"] = ["private"]
        with self.assertRaises(LineageError):
            self.store.create_proposal(inquiry, "alchemist", invalid, operation_key=self.key())
        self.assertNotIn("journals", self.detail(inquiry))

    def test_structure_validation_occ_whole_contract_and_long_only(self):
        inquiry = self.inquiry()
        for key, value in (("qty", 1.5), ("qty", True), ("qty", 0), ("intent", "short"), ("strike", "101"),
                           ("expiry", "2027-02-01"), ("underlying", "OTHER"), ("option_type", "put"),
                           ("multiplier", 1), ("order_type", "market"), ("limit_price", "NaN"),
                           ("limit_price", 2.0), ("limit_price", "0")):
            bad = structure()
            bad[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(LineageError):
                self.store.create_proposal(inquiry, "alchemist", bad, operation_key=self.key())
        valid = structure()
        valid.update({"strike": "100.000", "limit_price": "3.00"})
        proposal = self.store.create_proposal(inquiry, "alchemist", valid, operation_key="normalized")
        self.assertEqual(self.store.get_proposal(proposal, "alchemist")["structure"]["limit_price"], "3")
        self.assertEqual(self.store.create_proposal(inquiry, "alchemist", structure(), operation_key="normalized"), proposal)

    def test_execution_price_bounds_reject_extreme_magnitude_and_scale(self):
        inquiry = self.inquiry()
        for price in ("9" * 100, "1000000.00000001", "0.000000001", "1.123456789"):
            invalid = structure(price=price)
            with self.subTest(price=price), self.assertRaises(LineageError):
                self.store.create_proposal(inquiry, "alchemist", invalid, operation_key=self.key())
        for price in ("1000000.00000000", "0.0000000100", "1.123456780000"):
            self.store.create_proposal(inquiry, "alchemist", structure(price=price), operation_key=self.key())
        _, opening, position = self.open_position(qty=1)
        _, closing = self.order(inquiry, qty=1, side="sell", price="0.00000001")
        before = self.detail(inquiry)
        for price in ("1000001", "1.123456789", "0.000000001"):
            with self.subTest(fill_price=price), self.assertRaises(LineageError):
                self.store.apply_snapshot(closing["order_id"], "alchemist",
                                          snapshot(closing, status="filled", fills=[fill("extreme-fill", 1, price)]))
            self.assertEqual(self.detail(inquiry), before)

    def test_proposal_pending_and_stable_order_after_explicit_approval(self):
        inquiry, proposal = self.proposal(approve=False)
        with self.assertRaises(LineageConflict):
            self.store.prepare_order(proposal, "alchemist")
        queue_id = self.store.get_proposal(proposal, "alchemist")["queue_id"]
        TradeQueue(self.db).approve(queue_id)
        order = self.store.prepare_order(proposal, "alchemist")
        self.assertEqual(LineageStore(self.db).prepare_order(proposal, "alchemist"), order)
        self.assertEqual(order["status"], "pending_submission")
        self.assertEqual(order["broker_revision"], 0)
        self.assertIsNone(order["broker_order_id"])
        self.assertEqual(len(self.detail(inquiry)["orders"]), 1)
        self.assertEqual(self.detail(inquiry)["positions"], [])
        self.assertFalse(TradeQueue(self.db).reject(queue_id))

    def test_mutators_reject_foreign_owners_and_cross_inquiry_references(self):
        own = self.inquiry()
        foreign = self.inquiry("other")
        for method, args in ((self.store.add_entry, (foreign, "alchemist", "observation", "bad")),
                             (self.store.set_inquiry_state, (foreign, "alchemist", "paused")),
                             (self.store.create_proposal, (foreign, "alchemist", structure())),
                             (self.store.add_review, (foreign, "alchemist", "bad"))):
            with self.subTest(method=method), self.assertRaises(LineageAccessError):
                method(*args, operation_key=self.key())
        _, other_proposal = self.proposal(foreign, agent="other")
        with self.assertRaises(LineageAccessError):
            self.store.get_proposal(other_proposal, "alchemist")
        with self.assertRaises(LineageAccessError):
            self.store.prepare_order(other_proposal, "alchemist")
        with self.assertRaises(LineageAccessError):
            self.store.add_review(own, "alchemist", "bad", proposal_id=other_proposal, operation_key=self.key())
        different, different_proposal = self.proposal()
        with self.assertRaises(LineageConflict):
            self.store.add_review(own, "alchemist", "bad", proposal_id=different_proposal, operation_key=self.key())
        different_order = self.store.prepare_order(different_proposal, "alchemist")
        with self.assertRaises(LineageConflict):
            self.store.add_review(own, "alchemist", "bad", order_id=different_order["order_id"], operation_key=self.key())
        with self.assertRaises(LineageAccessError):
            self.store.get_order(different_order["order_id"], "other")
        with self.assertRaises(LineageAccessError):
            self.store.mark_order_issue(different_order["order_id"], "other", "failed")
        with self.assertRaises(LineageAccessError):
            self.store.apply_snapshot(different_order["order_id"], "other", snapshot(different_order))

    def test_phase_zero_never_becomes_peer_visible_and_identity_required(self):
        zero = self.inquiry(phase=0, visibility="community")
        community = self.inquiry(phase=1, visibility="community")
        owner_only = self.inquiry(phase=1, visibility="owner")
        self.assertEqual(self.detail(zero)["inquiry"]["inquiry_id"], zero)
        for inquiry, phase in ((zero, 9), (community, 0), (owner_only, 9)):
            with self.subTest(inquiry=inquiry), self.assertRaises(LineageAccessError):
                self.store.get_inquiry(inquiry, viewer_agent_id="other", phase=phase)
        self.assertEqual(self.store.get_inquiry(community, viewer_agent_id="other", phase=1)["inquiry"]["inquiry_id"], community)
        own = self.store.list_inquiries("alchemist", viewer_agent_id="alchemist")
        peer = self.store.list_inquiries("alchemist", viewer_agent_id="other", phase=5)
        self.assertEqual(own["total"], 3)
        self.assertEqual([item["inquiry_id"] for item in peer["inquiries"]], [community])
        self.assertEqual(self.store.list_inquiries("alchemist", viewer_agent_id="other", phase=0)["total"], 0)
        self.assertEqual(self.store.get_inquiry(zero, operator=True)["inquiry"]["inquiry_id"], zero)
        with self.assertRaises(LineageAccessError):
            self.store.get_inquiry(zero, operator="true")

    def test_reads_bound_categories_and_return_fresh_dtos(self):
        inquiry = self.inquiry()
        for number in range(101):
            self.store.add_entry(inquiry, "alchemist", "observation", f"item-{number}", operation_key=f"entry-{number}")
        detail = self.detail(inquiry)
        self.assertTrue(detail["truncated"])
        self.assertEqual(len(detail["entries"]), 100)
        self.assertEqual(len(detail["events"]), 100)
        detail["inquiry"]["title"] = "local mutation"
        self.assertEqual(self.detail(inquiry)["inquiry"]["title"], "An optional idea")
        for number in range(100):
            self.store.create_inquiry("alchemist", f"inquiry-{number}", operation_key=f"inquiry-{number}")
        listing = self.store.list_inquiries("alchemist", viewer_agent_id="alchemist", limit=1000)
        self.assertEqual((listing["total"], listing["limit"], len(listing["inquiries"])), (101, 100, 100))
        self.assertEqual(len(self.store.list_inquiries("alchemist", viewer_agent_id="alchemist", limit=100, offset=100)["inquiries"]), 1)

    def test_immutable_history_rejects_update_and_delete(self):
        inquiry, order, position = self.open_position()
        self.store.add_entry(inquiry, "alchemist", "observation", "original", operation_key=self.key())
        self.store.add_review(inquiry, "alchemist", "later view", position_id=position["position_id"], operation_key=self.key())
        with sqlite3.connect(self.db) as conn:
            for table in ("entries", "proposals", "fills", "reviews", "events", "operations"):
                for action in ("UPDATE", "DELETE"):
                    statement = f"UPDATE lineage_{table} SET agent_id=agent_id" if action == "UPDATE" else f"DELETE FROM lineage_{table}"
                    with self.subTest(table=table, action=action), self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(statement)

    def test_acceptance_creates_no_holdings_and_issues_preserve_confirmation(self):
        inquiry, order = self.order()
        accepted = snapshot(order)
        confirmed = self.store.apply_snapshot(order["order_id"], "alchemist", accepted)
        self.assertEqual(confirmed["status"], "accepted")
        self.assertEqual(self.detail(inquiry)["positions"], [])
        unavailable = self.store.mark_order_issue(order["order_id"], "alchemist", "unavailable")
        self.assertEqual(unavailable["status"], "accepted")
        self.assertEqual(unavailable["broker_order_id"], confirmed["broker_order_id"])
        self.assertEqual(unavailable["broker_revision"], 1)
        self.assertEqual(unavailable["sync_state"], "unavailable")
        restored = self.store.apply_snapshot(order["order_id"], "alchemist", accepted)
        self.assertEqual(restored["sync_state"], "ok")

    def test_unknown_submission_is_durable_and_issue_idempotent(self):
        inquiry, order = self.order()
        unknown = self.store.mark_order_issue(order["order_id"], "alchemist", "submission_unknown")
        self.assertEqual(unknown["status"], "submission_unknown")
        self.assertEqual(LineageStore(self.db).get_order(order["order_id"], "alchemist"), unknown)
        before = self.detail(inquiry)
        self.assertEqual(self.store.mark_order_issue(order["order_id"], "alchemist", "submission_unknown"), unknown)
        self.assertEqual(self.detail(inquiry), before)
        with self.assertRaises(LineageError):
            self.store.mark_order_issue(order["order_id"], "alchemist", "not_found")

    def test_partial_full_duplicate_stale_and_equal_canonical_snapshots(self):
        inquiry, order = self.order(qty=3)
        partial = snapshot(order, status="partially_filled", fills=[fill("one", 1, "2.00")])
        self.store.apply_snapshot(order["order_id"], "alchemist", partial)
        self.assertEqual(self.detail(inquiry)["positions"][0]["qty"], 1)
        before = self.detail(inquiry)
        equal = copy.deepcopy(partial)
        equal["fills"][0]["price"] = "2"
        equal["structure"]["limit_price"] = "3.000"
        self.store.apply_snapshot(order["order_id"], "alchemist", equal)
        self.assertEqual(self.detail(inquiry), before)
        full = snapshot(order, revision=2, status="filled", fills=[fill("one", 1, "2"), fill("two", 2, "2.5")])
        result = LineageStore(self.db).apply_snapshot(order["order_id"], "alchemist", full)
        self.assertEqual((result["filled_qty"], result["status"]), (3, "filled"))
        detail = self.detail(inquiry)
        self.assertEqual(len(detail["fills"]), 2)
        self.assertEqual(detail["positions"][0]["qty"], 3)
        self.assertEqual(Decimal(detail["positions"][0]["average_entry_price"]).quantize(Decimal(".000001")), Decimal("2.333333"))
        self.assertEqual(self.store.apply_snapshot(order["order_id"], "alchemist", partial), result)
        self.assertEqual(self.detail(inquiry), detail)
        same_reversed = copy.deepcopy(full)
        same_reversed["fills"].reverse()
        self.assertEqual(self.store.apply_snapshot(order["order_id"], "alchemist", same_reversed), result)
        conflict = copy.deepcopy(full)
        conflict["updated_at"] = "different"
        with self.assertRaises(LineageConflict):
            self.store.apply_snapshot(order["order_id"], "alchemist", conflict)
        self.assertEqual(self.detail(inquiry), detail)

    def test_canceled_and_terminal_states_preserve_partial_fills(self):
        for terminal in ("canceled",):
            with self.subTest(terminal=terminal):
                inquiry, order = self.order(qty=2)
                execution = fill(terminal + "-fill", 1, "2")
                self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, status="partially_filled", fills=[execution]))
                terminal_snapshot = snapshot(order, revision=2, status=terminal, fills=[execution])
                result = self.store.apply_snapshot(order["order_id"], "alchemist", terminal_snapshot)
                self.assertEqual(result["filled_qty"], 1)
                self.assertEqual(self.detail(inquiry)["positions"][0]["qty"], 1)
                before = self.detail(inquiry)
                with self.assertRaises(LineageConflict):
                    self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, revision=3, status="partially_filled", fills=[execution]))
                with self.assertRaises(LineageConflict):
                    self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, revision=3, status="filled", fills=[execution, fill(terminal + "-extra", 1)]))
                self.assertEqual(self.detail(inquiry), before)

    def test_rejected_snapshots_cannot_fabricate_partial_or_full_executions(self):
        inquiry, order = self.order(qty=2)
        before = self.detail(inquiry)
        for qty in (1, 2):
            with self.subTest(qty=qty), self.assertRaises(LineageConflict):
                self.store.apply_snapshot(order["order_id"], "alchemist",
                                          snapshot(order, status="rejected", fills=[fill("fabricated", qty)]))
            self.assertEqual(self.detail(inquiry), before)
        rejected = self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, status="rejected"))
        self.assertEqual((rejected["status"], rejected["filled_qty"]), ("rejected", 0))
        self.assertEqual(self.detail(inquiry)["positions"], [])
        self.assertEqual(self.detail(inquiry)["fills"], [])

    def test_rejected_snapshot_cannot_erase_confirmed_partial_fills(self):
        inquiry, order = self.order(qty=2)
        execution = fill("confirmed-partial", 1)
        self.store.apply_snapshot(order["order_id"], "alchemist",
                                  snapshot(order, status="partially_filled", fills=[execution]))
        before = self.detail(inquiry)
        for executions in ([], [execution]):
            with self.subTest(executions=executions), self.assertRaises(LineageConflict):
                self.store.apply_snapshot(order["order_id"], "alchemist",
                                          snapshot(order, revision=2, status="rejected", fills=executions))
            self.assertEqual(self.detail(inquiry), before)

    def test_atomic_rejection_overfill_bad_price_identity_and_fill_changes(self):
        inquiry, order = self.order(qty=2)
        initial = snapshot(order, status="partially_filled", fills=[fill("stable", 1, "2")])
        self.store.apply_snapshot(order["order_id"], "alchemist", initial)
        before = self.detail(inquiry)
        bad = []
        overfill = snapshot(order, revision=2, status="filled", fills=[fill("stable", 1), fill("excess", 2)])
        bad.append(overfill)
        bad.append(snapshot(order, revision=2, status="filled", fills=[fill("stable", 1), fill("bad-limit", 1, "4")]))
        bad.append(snapshot(order, revision=2, status="filled", fills=[fill("stable", 1), fill("bad-price", 1, "NaN")]))
        bad.append(snapshot(order, revision=2, status="filled", fills=[fill("stable", 1, "2.1"), fill("new", 1)]))
        bad.append(snapshot(order, revision=2, status="filled", fills=[fill("stable", 1, "2", "changed"), fill("new", 1)]))
        bad.append(snapshot(order, revision=2, status="accepted"))
        identity = snapshot(order, revision=2, status="filled", fills=[fill("stable", 1), fill("new", 1)])
        identity["client_order_id"] = "wrong"
        bad.append(identity)
        authority = copy.deepcopy(identity)
        authority["client_order_id"] = order["client_order_id"]
        authority["broker"] = "alpaca"
        bad.append(authority)
        removed = snapshot(order, revision=2, status="filled", fills=[fill("replacement", 2)])
        bad.append(removed)
        duplicate = snapshot(order, revision=2, status="filled", fills=[fill("stable", 1), fill("stable", 1)])
        bad.append(duplicate)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(LineageError):
                self.store.apply_snapshot(order["order_id"], "alchemist", value)
            self.assertEqual(self.detail(inquiry), before)

    def test_fill_identity_cannot_be_reused_for_another_order(self):
        first, first_order, position = self.open_position(qty=1)
        existing_id = self.detail(first)["fills"][0]["broker_fill_id"]
        second, second_order = self.order(qty=1)
        with self.assertRaises(LineageConflict):
            self.store.apply_snapshot(second_order["order_id"], "alchemist", snapshot(second_order, status="filled", fills=[fill(existing_id, 1)]))
        self.assertEqual(self.detail(second)["fills"], [])
        self.assertEqual(self.store.get_order(second_order["order_id"], "alchemist")["broker_revision"], 0)

    def test_atomic_fill_failure_rolls_back_order_position_and_events(self):
        inquiry, order = self.order(qty=1)
        before = self.detail(inquiry)
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TRIGGER fail_fill BEFORE INSERT ON lineage_fills BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        with self.assertRaises(LineageConflict):
            self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order, status="filled", fills=[fill("rollback")]))
        self.assertEqual(self.detail(inquiry), before)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM lineage_positions").fetchone()[0], 0)

    def test_close_requires_confirmed_holdings_not_acceptance(self):
        inquiry, opening = self.order(qty=2)
        self.store.apply_snapshot(opening["order_id"], "alchemist", snapshot(opening))
        _, proposal = self.proposal(inquiry, qty=1, side="sell", price="1")
        with self.assertRaises(LineageConflict):
            self.store.prepare_order(proposal, "alchemist")
        self.assertEqual(len(self.detail(inquiry)["orders"]), 1)

    def test_close_decimal_cost_basis_gross_pnl_unknown_fees_and_stable_position(self):
        inquiry, opening, position = self.open_position(qty=3, price="2.25")
        _, close = self.order(inquiry, qty=2, side="sell", price="3")
        self.store.apply_snapshot(close["order_id"], "alchemist", snapshot(close, status="partially_filled", fills=[fill("close1", 1, "3.25")]))
        partial_position = self.detail(inquiry)["positions"][0]
        self.assertEqual((partial_position["qty"], partial_position["gross_realized_pnl"]), (2, "100"))
        self.assertEqual(partial_position["average_entry_price"], "2.25")
        self.store.apply_snapshot(close["order_id"], "alchemist", snapshot(close, revision=2, status="filled", fills=[fill("close1", 1, "3.25"), fill("close2", 1, "3.5")]))
        _, final_close = self.order(inquiry, qty=1, side="sell", price="1")
        self.store.apply_snapshot(final_close["order_id"], "alchemist", snapshot(final_close, status="filled", fills=[fill("close3", 1, "1.5")]))
        closed = self.detail(inquiry)["positions"][0]
        self.assertEqual(closed["position_id"], position["position_id"])
        self.assertEqual((closed["qty"], closed["status"], closed["gross_realized_pnl"]), (0, "closed", "150"))
        self.assertIsNone(closed["average_entry_price"])
        for field in ("fees", "market_value", "unrealized_pnl"):
            self.assertIsNone(closed[field])
        self.assertEqual(closed["mark_status"], "unavailable")
        _, reopened, same_position = self.open_position(qty=1, inquiry=inquiry)
        self.assertEqual(same_position["position_id"], position["position_id"])
        self.assertEqual(same_position["gross_realized_pnl"], "150")

    def test_close_reservations_survive_unknown_unavailable_and_partial_cancellation(self):
        inquiry, opening, position = self.open_position(qty=3)
        _, closing = self.order(inquiry, qty=2, side="sell", price="1")
        self.store.mark_order_issue(closing["order_id"], "alchemist", "submission_unknown")
        self.store.mark_order_issue(closing["order_id"], "alchemist", "unavailable")
        _, another = self.proposal(inquiry, qty=2, side="sell", price="1")
        with self.assertRaises(LineageConflict):
            LineageStore(self.db).prepare_order(another, "alchemist")
        partial = snapshot(closing, status="partially_filled", fills=[fill("reserved-close", 1, "1")])
        self.store.apply_snapshot(closing["order_id"], "alchemist", partial)
        with self.assertRaises(LineageConflict):
            self.store.prepare_order(another, "alchemist")
        self.store.apply_snapshot(closing["order_id"], "alchemist", snapshot(closing, revision=2, status="canceled", fills=[fill("reserved-close", 1, "1")]))
        prepared = self.store.prepare_order(another, "alchemist")
        self.assertEqual(prepared["qty"], 2)
        self.assertEqual(self.detail(inquiry)["positions"][0]["qty"], 2)

    def test_simultaneous_closes_cannot_oversell_confirmed_holdings(self):
        inquiry, opening, position = self.open_position(qty=2)
        _, first = self.proposal(inquiry, qty=2, side="sell", price="1")
        _, second = self.proposal(inquiry, qty=2, side="sell", price="1")
        def prepare(proposal):
            try:
                return LineageStore(self.db).prepare_order(proposal, "alchemist")["order_id"]
            except LineageConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(prepare, (first, second)))
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(len(self.detail(inquiry)["orders"]), 2)  # one opening + one reserved close

    def test_review_reference_integrity_and_append_idempotency(self):
        inquiry, opening, position = self.open_position(qty=1)
        review = self.store.add_review(inquiry, "alchemist", "later view", proposal_id=opening["proposal_id"],
                                       order_id=opening["order_id"], position_id=position["position_id"], operation_key="review")
        self.assertEqual(LineageStore(self.db).add_review(inquiry, "alchemist", "later view", proposal_id=opening["proposal_id"],
                                                        order_id=opening["order_id"], position_id=position["position_id"], operation_key="review"), review)
        different = self.inquiry()
        with self.assertRaises(LineageConflict):
            self.store.add_review(different, "alchemist", "bad", position_id=position["position_id"], operation_key=self.key())
        foreign = self.inquiry("other")
        with self.assertRaises(LineageAccessError):
            self.store.add_review(foreign, "other", "bad", position_id=position["position_id"], operation_key=self.key())
        self.assertEqual(self.detail(inquiry)["proposals"][0]["thesis"], "fictional thesis")
        self.assertEqual(len(self.detail(inquiry)["reviews"]), 1)

    def test_related_positions_same_agent_symbol_and_peer_aggregate_privacy(self):
        private = self.inquiry(phase=0)
        community = self.inquiry(phase=1, visibility="community")
        _, first, position = self.open_position(qty=1, inquiry=private)
        _, second, shared = self.open_position(qty=1, inquiry=community)
        self.assertEqual(position["position_id"], shared["position_id"])
        self.assertEqual(shared["qty"], 2)
        own = self.detail(community)
        self.assertEqual({order["order_id"] for order in own["orders"]}, {second["order_id"]})
        self.assertEqual(len(own["fills"]), 1)
        peer = self.store.get_inquiry(community, viewer_agent_id="other", phase=1)
        self.assertEqual(peer["positions"], [])  # never leak private contributing holdings/P&L
        foreign, foreign_order = self.order(qty=1, agent="other")
        self.store.apply_snapshot(foreign_order["order_id"], "other", snapshot(foreign_order, status="filled", fills=[fill("other-fill", 1)]))
        foreign_position = self.detail(foreign, agent="other")["positions"][0]
        self.assertNotEqual(foreign_position["position_id"], position["position_id"])
        self.assertEqual(self.detail(community)["positions"][0]["qty"], 2)

    def test_broker_order_identity_and_status_consistency(self):
        inquiry, order = self.order(qty=2)
        self.store.apply_snapshot(order["order_id"], "alchemist", snapshot(order))
        before = self.detail(inquiry)
        for field, value in (("broker_order_id", "changed"), ("created_at", "changed"), ("qty", 3),
                             ("filled_qty", 1), ("revision", 1.5), ("revision", True), ("status", "filled")):
            bad = snapshot(order, revision=2)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(LineageError):
                self.store.apply_snapshot(order["order_id"], "alchemist", bad)
            self.assertEqual(self.detail(inquiry), before)
        with self.assertRaises(LineageNotFound):
            self.store.get_order("missing", "alchemist")


if __name__ == "__main__":
    unittest.main()
