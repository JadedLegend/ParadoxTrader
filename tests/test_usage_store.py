"""Temporary private SQLite databases and synthetic metadata; no live calls."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from uuid import uuid4
import warnings

from core.usage.context import usage_scope
from core.usage.pricing import PricingTable
from core.usage import store as usage_store
from core.usage.store import UsageStore, get_usage_store, record_usage
from tests.test_usage_pricing import synthetic_table


SUMMARY_FIELDS = {"requests", "successful_requests", "failed_requests", "reported_cost_usd",
                  "estimated_cost_usd", "reported_cost_requests", "estimated_cost_requests",
                  "unknown_cost_requests", "input_tokens", "output_tokens", "cached_input_tokens",
                  "reasoning_tokens", "usage_known_requests", "usage_unknown_requests"}


def event(**overrides):
    data = {"call_id": str(uuid4()), "provider": "openrouter", "model": "synthetic/model",
            "attempt": 1, "created_at": "2026-01-01T00:00:00Z", "duration_ms": 12.5,
            "outcome": "success", "http_status": 200, "agent_id": "tempest", "activity": "research"}
    data.update(overrides)
    return data


class UsageStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "private" / "usage.sqlite3"
        self.store = UsageStore(self.path, PricingTable())
        self.network = mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def read(self):
        return self.store.list_events()["events"][0]

    def test_constructor_is_lazy_and_first_use_creates_private_db(self):
        self.assertFalse(self.path.exists())
        self.store.record(event())
        self.assertTrue(self.path.exists())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_import_all_usage_modules_never_opens_db_or_data_dir(self):
        script = """
from unittest import mock
with mock.patch('os.mkdir', side_effect=AssertionError('directory IO')), mock.patch('sqlite3.connect', side_effect=AssertionError('database IO')), mock.patch('socket.socket', side_effect=AssertionError('network IO')):
    import core.usage
    import core.usage.context
    import core.usage.store
    import core.usage.pricing
import sys
assert 'core.data_dir' not in sys.modules
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generated_event_uuid_and_allowlisted_metadata(self):
        data = event(response_model="synthetic/returned-model", prompt="SECRET_PROMPT", messages=["SECRET_ANSWER"],
                     headers={"Authorization": "SECRET_KEY"}, usage={"raw": "SECRET_RAW"},
                     raw_error="SECRET_ERROR", cost_usd="999", cost_status="reported")
        recorded = self.store.record(data)
        self.assertEqual(str(__import__("uuid").UUID(recorded)), recorded)
        saved = self.read()
        self.assertEqual(saved["response_model"], "synthetic/returned-model")
        self.assertEqual(saved["created_at"], "2026-01-01T00:00:00.000000+00:00")
        self.assertEqual(saved["cost_status"], "unknown")
        self.assertIsNone(saved["cost_usd"])
        serialized = json.dumps(saved)
        for marker in ("SECRET_PROMPT", "SECRET_ANSWER", "SECRET_KEY", "SECRET_RAW", "SECRET_ERROR"):
            self.assertNotIn(marker, serialized)
            self.assertNotIn(marker.encode(), self.path.read_bytes())

    def test_record_inherits_context_only_for_omitted_fields(self):
        data = event()
        data.pop("activity")
        with usage_scope("choose_action", "wake-1"):
            self.store.record(data)
        self.assertEqual(self.read()["activity"], "choose_action")
        self.assertEqual(self.read()["wake_id"], "wake-1")
        with usage_scope("outer", "wake-2"):
            self.store.record(event(activity="explicit", wake_id=None, created_at="2026-01-02T00:00:00Z"))
        self.assertEqual(self.read()["activity"], "explicit")
        self.assertIsNone(self.read()["wake_id"])

    def test_deduplicate_event_id_never_overwrite(self):
        identity = str(uuid4())
        self.store.record(event(event_id=identity, provider_cost_usd="0.1"))
        returned = self.store.record(event(event_id=identity, provider_cost_usd="999", model="changed/model", outcome="http_error"))
        self.assertEqual(returned, identity)
        self.assertEqual(self.store.list_events()["total"], 1)
        self.assertEqual(self.read()["cost_usd"], "0.1")
        self.assertEqual(self.read()["outcome"], "success")

    def test_deduplicate_attempt_returns_original_id_but_retry_is_new(self):
        data = event(call_id="call-1", outcome="http_error", http_status=429)
        identity = self.store.record(data)
        self.assertEqual(self.store.record({**data, "provider_cost_usd": "999"}), identity)
        self.store.record({**data, "attempt": 2, "outcome": "success", "http_status": 200})
        self.store.record({**data, "provider": "perplexity"})
        self.assertEqual(self.store.list_events()["total"], 3)
        self.assertEqual(self.store.summary()["summary"]["failed_requests"], 2)

    def test_events_are_immutable_even_via_sql(self):
        self.store.record(event())
        with sqlite3.connect(self.path) as conn:
            for query in ("UPDATE usage_events SET model='changed'", "DELETE FROM usage_events"):
                with self.subTest(query=query), self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(query)

    def test_strict_schema_bad_types_and_bounds(self):
        invalid = {
            "event_id": [True, 123, "not-a-uuid", "x" * 129, None],
            "call_id": [None, True, 123, "", "x" * 129, "../call", "secret\n"],
            "wake_id": [True, 123, "x" * 129, "a/b"],
            "agent_id": [True, 123, "", "x" * 81, "a/b"],
            "activity": [None, True, "", "x" * 81, "a b"],
            "provider": [True, "unknown", "OPENROUTER", "openrouter\n"],
            "model": [None, True, "a b", "x" * 129],
            "response_model": [True, "a b", "x" * 129],
            "attempt": [None, True, 0, 101, 1.0, "1"],
            "created_at": [None, True, "2026-01-01", "2026-01-01T00:00:00", "2026-02-30T00:00:00Z"],
            "duration_ms": [None, True, -1, 86_400_001, "1", float("nan"), float("inf")],
            "outcome": [None, True, "other", "success\n"],
            "http_status": [True, "200", 200.0, 99, 600],
            "provider_cost_usd": [True, -1, "-1", "NaN", "Infinity", float("nan"), [], {},
                                  "1e10000000", "1e-10000000", "1" * 65, "0" * 257],
        }
        for field in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens"):
            invalid[field] = [True, "1", 1.0, -1, 10_000_000_001]
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.store.record(event(**{field: value}))
        self.assertFalse(self.path.exists(), "invalid events must not initialize DB")

    def test_non_dict_event_is_value_error(self):
        for data in (None, [], "bad", 12):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.store.record(data)

    def test_token_subsets_validated_but_partial_counts_retained(self):
        for data in (event(input_tokens=1, cached_input_tokens=2), event(output_tokens=1, reasoning_tokens=2)):
            with self.assertRaises(ValueError):
                self.store.record(data)
        self.store.record(event(input_tokens=None, output_tokens=10, cached_input_tokens=7, reasoning_tokens=2,
                                outcome="invalid_response"))
        saved = self.read()
        self.assertEqual(saved["output_tokens"], 10)
        self.assertEqual(saved["cached_input_tokens"], 7)
        self.assertEqual(saved["reasoning_tokens"], 2)
        self.assertEqual(saved["cost_reason"], "missing_usage")

    def test_token_and_duration_valid_maximum_boundaries(self):
        self.store.record(event(input_tokens=10_000_000_000, output_tokens=0, cached_input_tokens=0,
                                reasoning_tokens=0, total_tokens=10_000_000_000, duration_ms=86_400_000,
                                attempt=100, http_status=599))
        self.assertEqual(self.read()["input_tokens"], 10_000_000_000)

    def test_nullable_usage_and_cost_do_not_become_zero(self):
        self.store.record(event(input_tokens=None, output_tokens=None, provider_cost_usd=None))
        summary = self.store.summary()["summary"]
        self.assertIsNone(summary["reported_cost_usd"])
        self.assertIsNone(summary["estimated_cost_usd"])
        self.assertIsNone(summary["input_tokens"])
        self.assertEqual(summary["usage_unknown_requests"], 1)
        self.assertEqual(summary["unknown_cost_requests"], 1)

    def test_empty_reads_initialize_only_on_explicit_use_and_keep_unknown_subtotals_null(self):
        result = self.store.summary()
        summary = result["summary"]
        self.assertEqual(set(summary), SUMMARY_FIELDS)
        for field in SUMMARY_FIELDS:
            if field.endswith("_usd") or field.endswith("_tokens"):
                self.assertIsNone(summary[field])
            else:
                self.assertEqual(summary[field], 0)
        self.assertEqual(result["by_agent"], [])
        self.assertEqual(self.store.list_events()["total"], 0)

    def test_known_reported_zero_is_distinct_from_unknown(self):
        self.store.record(event(provider_cost_usd=0))
        summary = self.store.summary()["summary"]
        self.assertEqual(summary["reported_cost_usd"], "0")
        self.assertEqual(summary["reported_cost_requests"], 1)
        self.assertEqual(summary["unknown_cost_requests"], 0)
        self.assertEqual(summary["usage_unknown_requests"], 1)

    def test_exact_partial_summary_and_all_group_contracts(self):
        self.store.pricing_table = PricingTable(synthetic_table())
        self.store.record(event(input_tokens=1000, output_tokens=100, cached_input_tokens=200, reasoning_tokens=50))
        self.store.record(event(agent_id="shadow", provider_cost_usd="0.123456789012345678901", output_tokens=7,
                                outcome="http_error", http_status=500, activity="choose_action"))
        self.store.record(event(agent_id=None, provider="perplexity", input_tokens=5, activity="choose_action",
                                outcome="transport_error", http_status=None))
        result = self.store.summary()
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["summary"], {
            "requests": 3, "successful_requests": 1, "failed_requests": 2,
            "reported_cost_usd": "0.123456789012345678901", "estimated_cost_usd": "0.0021",
            "reported_cost_requests": 1, "estimated_cost_requests": 1, "unknown_cost_requests": 1,
            "input_tokens": 1005, "output_tokens": 107, "cached_input_tokens": 200,
            "reasoning_tokens": 50, "usage_known_requests": 1, "usage_unknown_requests": 2})
        self.assertEqual(len(result["by_agent"]), 3)
        self.assertIn(None, [row["agent_id"] for row in result["by_agent"]])
        for key, dimension in (("by_agent", "agent_id"), ("by_provider", "provider"), ("by_activity", "activity")):
            for row in result[key]:
                self.assertEqual(set(row), SUMMARY_FIELDS | {dimension})
            self.assertEqual(sum(row["requests"] for row in result[key]), 3)
        self.assertIs(result["groups_truncated"], False)

    def test_sql_decimal_aggregate_never_accumulates_binary_floats_or_rounds(self):
        for amount in ("0.1", "0.2", "0.000000000000000000000000000000000000001"):
            self.store.record(event(provider_cost_usd=amount))
        with localcontext() as ctx:
            ctx.prec = 6
            result = self.store.summary()["summary"]["reported_cost_usd"]
        self.assertEqual(Decimal(result), Decimal("0.300000000000000000000000000000000000001"))

    def test_pricing_is_snapshotted_at_write_and_never_repriced(self):
        self.store.pricing_table = PricingTable(synthetic_table())
        self.store.record(event(input_tokens=1000, output_tokens=100, cached_input_tokens=200))
        self.store.pricing_table = PricingTable(synthetic_table(input_usd_per_million="999", source="later-test", as_of="2026-02-01"))
        saved = self.read()
        self.assertEqual(saved["cost_usd"], "0.0021")
        self.assertEqual(saved["pricing_snapshot"]["source"], "offline-test-only")
        self.assertEqual(saved["pricing_snapshot"]["as_of"], "2026-01-01")
        self.assertEqual(saved["pricing_snapshot"]["input_usd_per_million"], "2")
        self.assertEqual(self.store.summary()["summary"]["estimated_cost_usd"], "0.0021")

    def test_invalid_optional_pricing_preserves_event_with_coverage_reason(self):
        self.store.pricing_table = PricingTable.invalid_table()
        self.store.record(event(input_tokens=1, output_tokens=2, cached_input_tokens=0))
        self.assertEqual(self.read()["cost_reason"], "invalid_pricing")
        self.assertEqual(self.store.list_events()["total"], 1)

    def test_default_pricing_is_loaded_per_write_not_on_reads(self):
        self.store.pricing_table = None
        with mock.patch.object(usage_store, "get_default_pricing", return_value=PricingTable(synthetic_table())) as loader:
            self.store.record(event(input_tokens=1000, output_tokens=100, cached_input_tokens=200))
            self.store.summary()
            self.store.list_events()
            loader.assert_called_once_with()

    def test_utc_filters_since_inclusive_until_exclusive_and_agent(self):
        self.store.record(event(created_at="2026-01-01T01:00:00+01:00"))
        self.store.record(event(created_at="2026-01-01T01:00:00Z", agent_id="shadow"))
        self.store.record(event(created_at="2026-01-01T02:00:00Z"))
        page = self.store.list_events(since="2025-12-31T19:00:00-05:00", until="2026-01-01T02:00:00Z")
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["filters"], {"agent_id": None, "since": "2026-01-01T00:00:00.000000+00:00",
                                           "until": "2026-01-01T02:00:00.000000+00:00"})
        self.assertEqual(self.store.summary(agent_id="tempest", since="2026-01-01T00:00:00Z",
                                             until="2026-01-01T02:00:00Z")["summary"]["requests"], 1)
        self.assertEqual(self.store.list_events(since="2026-01-01T00:00:00Z", until="2026-01-01T00:00:00Z")["total"], 0)

    def test_pagination_newest_then_event_id_and_limits(self):
        ids = ["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000003",
               "00000000-0000-0000-0000-000000000002"]
        for identity in ids:
            self.store.record(event(event_id=identity))
        page = self.store.list_events(limit=1, offset=1)
        self.assertEqual(page["events"][0]["event_id"], ids[2])
        self.assertEqual(page["total"], 3)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["offset"], 1)
        self.assertEqual(self.store.list_events(offset=2_147_483_647)["events"], [])

    def test_invalid_filter_and_pagination_rejected_before_io(self):
        invalid = [{"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": "50"}, {"limit": 1.0},
                   {"offset": -1}, {"offset": True}, {"offset": 2_147_483_648}, {"agent_id": "../../file"},
                   {"agent_id": "a" * 81}, {"since": "2026-01-01T00:00:00"}, {"until": "not ISO"},
                   {"since": "2026-01-02T00:00:00Z", "until": "2026-01-01T00:00:00Z"}]
        for filters in invalid:
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.store.list_events(**filters)
        for filters in ({"agent_id": "bad agent"}, {"since": "2026-01-01T00:00:00"}, {"until": True}):
            with self.subTest(filters=filters), self.assertRaises(ValueError):
                self.store.summary(**filters)
        self.assertFalse(self.path.exists())

    def test_each_group_list_is_bounded_without_losing_overall_totals(self):
        for index in range(105):
            self.store.record(event(agent_id=f"agent-{index}", activity=f"activity-{index}"))
        result = self.store.summary()
        self.assertEqual(result["summary"]["requests"], 105)
        self.assertEqual(len(result["by_agent"]), 100)
        self.assertEqual(len(result["by_activity"]), 100)
        self.assertIs(result["groups_truncated"], True)
        self.assertEqual(len(self.store.list_events(limit=100)["events"]), 100)

    def test_concurrent_records_and_duplicate_attempts(self):
        duplicated = event(call_id="one-attempt", provider_cost_usd="0.01")
        def record(index):
            return self.store.record(duplicated if index % 2 == 0 else event(call_id=f"call-{index}", provider_cost_usd="0.01"))
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(record, range(64)))
        self.assertEqual(len(set(ids[::2])), 1)
        summary = self.store.summary()["summary"]
        self.assertEqual(summary["requests"], 33)
        self.assertEqual(summary["reported_cost_usd"], "0.33")

    def test_independent_store_instances_can_write_concurrently(self):
        stores = [UsageStore(self.path, PricingTable()) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(lambda index: stores[index % 8].record(event()), range(40)))
        self.assertEqual(len(set(ids)), 40)
        self.assertEqual(self.store.summary()["summary"]["requests"], 40)

    def test_lazy_default_factory_uses_only_dedicated_usage_db(self):
        data = types.ModuleType("core.data_dir")
        data.db_path = mock.Mock(return_value=str(self.path))
        with mock.patch.object(usage_store, "_default_store", None), mock.patch.dict(sys.modules, {"core.data_dir": data}):
            first = get_usage_store()
            second = get_usage_store()
            self.assertIs(first, second)
            self.assertFalse(self.path.exists())
            data.db_path.assert_called_once_with("usage.sqlite3")

    def test_best_effort_helper_returns_boolean_and_warns_without_raw_exception(self):
        with mock.patch.object(usage_store, "get_usage_store", return_value=self.store):
            self.assertIs(record_usage(event()), True)
        for exception in (sqlite3.OperationalError("readonly database SECRET_KEY"), RuntimeError("RAW_PROVIDER_BODY")):
            with mock.patch.object(usage_store, "get_usage_store", side_effect=exception) as factory, \
                 warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.assertIs(record_usage(event()), False)
                factory.assert_called_once_with()
            self.assertEqual(len(caught), 1)
            self.assertIs(caught[0].category, RuntimeWarning)
            self.assertEqual(str(caught[0].message), "usage_recording_failed")

    def test_readonly_write_fails_once_and_never_replays_provider(self):
        self.store.record(event())
        self.store._initialized = True
        connect = sqlite3.connect
        def readonly_connection(*args, **kwargs):
            return connect(f"file:{self.path}?mode=ro", uri=True, timeout=10)
        with mock.patch.object(usage_store, "get_usage_store", return_value=self.store) as factory, \
             mock.patch.object(usage_store.sqlite3, "connect", side_effect=readonly_connection) as connection, \
             warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertIs(record_usage(event()), False)
            factory.assert_called_once_with()
            connection.assert_called_once()
        self.assertEqual(str(caught[0].message), "usage_recording_failed")
        self.assertEqual(self.store.list_events()["total"], 1)

    def test_bad_duration_warning_policy_never_promotes_recording_error(self):
        with mock.patch.object(usage_store, "get_usage_store", return_value=self.store), warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            self.assertIs(record_usage(event(duration_ms=float("nan"))), False)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
