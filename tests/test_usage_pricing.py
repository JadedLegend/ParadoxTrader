"""Explicit synthetic rates only; these tests never request market prices."""

from copy import deepcopy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import socket
import tempfile
import types
import unittest
from unittest import mock

from core.usage import pricing
from core.usage.pricing import PricingTable, decimal_add, decimal_value, get_default_pricing


def synthetic_table(**overrides):
    rate = {"provider": "openrouter", "model": "synthetic/model",
            "input_usd_per_million": "2", "output_usd_per_million": "4",
            "cached_input_usd_per_million": "0.5", "source": "offline-test-only",
            "as_of": "2026-01-01"}
    rate.update(overrides)
    return {"schema_version": 1, "rates": [rate]}


def priced_event(**overrides):
    event = {"provider": "openrouter", "model": "synthetic/model", "input_tokens": 1000,
             "output_tokens": 100, "cached_input_tokens": 200, "reasoning_tokens": 50,
             "total_tokens": 1100, "provider_cost_usd": None}
    event.update(overrides)
    return event


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.network = mock.patch.object(socket, "socket", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def test_empty_example_has_no_current_rates(self):
        path = Path(__file__).resolve().parents[1] / "config" / "usage_pricing.example.json"
        self.assertEqual(json.loads(path.read_text()), {"schema_version": 1, "rates": []})
        self.assertEqual(PricingTable.from_file(path).resolve(priced_event())["cost_reason"], "missing_rates")

    def test_provider_total_precedes_rates_and_usage_even_zero(self):
        table = PricingTable.invalid_table()
        for amount, expected in ((0, "0"), ("0.00", "0"), ("0.12345678901234567890123456789", "0.12345678901234567890123456789")):
            with self.subTest(amount=amount):
                result = table.resolve(priced_event(provider_cost_usd=amount, input_tokens=None, output_tokens=None))
                self.assertEqual(result, {"cost_usd": expected, "cost_status": "reported",
                                          "cost_scope": "provider_reported", "cost_reason": None,
                                          "pricing_snapshot": None})

    def test_cached_formula_reasoning_and_total_are_not_added(self):
        table = PricingTable(synthetic_table())
        result = table.resolve(priced_event())
        self.assertEqual(result["cost_usd"], "0.0021")
        self.assertEqual(result["cost_status"], "estimated")
        self.assertEqual(result["cost_scope"], "token_only")
        self.assertEqual(result["pricing_snapshot"]["cached_input_usd_per_million"], "0.5")
        self.assertEqual(table.resolve(priced_event(reasoning_tokens=0, total_tokens=999999))["cost_usd"], "0.0021")

    def test_zero_cached_usage_allows_no_cache_rate(self):
        table = PricingTable(synthetic_table(cached_input_usd_per_million=None))
        result = table.resolve(priced_event(cached_input_tokens=0))
        self.assertEqual(result["cost_usd"], "0.0024")
        self.assertEqual(result["cost_scope"], "token_only")

    def test_missing_cache_count_is_unknown_with_or_without_cache_rate(self):
        for cache_rate in (None, "0.5"):
            with self.subTest(cache_rate=cache_rate):
                result = PricingTable(synthetic_table(cached_input_usd_per_million=cache_rate)).resolve(priced_event(cached_input_tokens=None))
                self.assertEqual(result["cost_reason"], "unknown_cache_usage")
                self.assertIsNone(result["cost_usd"])

    def test_positive_cached_tokens_need_explicit_cache_rate(self):
        result = PricingTable(synthetic_table(cached_input_usd_per_million=None)).resolve(priced_event())
        self.assertEqual(result["cost_reason"], "unknown_cache_usage")

    def test_partial_input_or_output_usage_is_unknown(self):
        for overrides in ({"input_tokens": None}, {"output_tokens": None}, {"input_tokens": None, "output_tokens": None}):
            with self.subTest(overrides=overrides):
                result = PricingTable(synthetic_table()).resolve(priced_event(**overrides))
                self.assertEqual(result["cost_reason"], "missing_usage")

    def test_missing_model_rates_never_invent_a_price(self):
        result = PricingTable(synthetic_table()).resolve(priced_event(model="other/model"))
        self.assertEqual(result["cost_reason"], "missing_rates")
        self.assertEqual(result["cost_status"], "unknown")

    def test_different_returned_model_never_uses_requested_rate(self):
        result = PricingTable(synthetic_table()).resolve(priced_event(response_model="returned/model"))
        self.assertEqual(result["cost_reason"], "missing_rates")
        self.assertIsNone(result["cost_usd"])

    def test_returned_model_matching_rate_has_explicit_provenance(self):
        table = PricingTable(synthetic_table(model="returned/model", input_usd_per_million="3"))
        result = table.resolve(priced_event(response_model="returned/model"))
        self.assertEqual(result["cost_usd"], "0.0029")
        self.assertEqual(result["pricing_snapshot"]["model"], "returned/model")

    def test_reported_cost_precedes_returned_model_mismatch(self):
        result = PricingTable(synthetic_table()).resolve(priced_event(response_model="returned/model", provider_cost_usd="0"))
        self.assertEqual(result["cost_usd"], "0")
        self.assertEqual(result["cost_status"], "reported")

    def test_decimal_magnitude_precision_and_text_are_bounded(self):
        for value in ("1e10000000", "1e-10000000", "1e101", "1e-101", "1" * 65, "0" * 257):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decimal_value(value)
        for value in ("1e100", "1e-100", "1" * 64, "1" + "0" * 100):
            with self.subTest(value=value):
                self.assertTrue(decimal_value(value).is_finite())

    def test_explicit_zero_rates_produce_known_zero(self):
        table = PricingTable(synthetic_table(input_usd_per_million="0", output_usd_per_million="0", cached_input_usd_per_million="0"))
        result = table.resolve(priced_event())
        self.assertEqual(result["cost_usd"], "0")
        self.assertEqual(result["cost_status"], "estimated")

    def test_long_decimal_rates_remain_exact_with_low_global_precision(self):
        digits = "0.123456789012345678901234567890123456789"
        table = PricingTable(synthetic_table(input_usd_per_million=digits, output_usd_per_million="0", cached_input_usd_per_million=None))
        with localcontext() as ctx:
            ctx.prec = 6
            result = table.resolve(priced_event(input_tokens=1_000_000, output_tokens=0, cached_input_tokens=0))
        self.assertEqual(Decimal(result["cost_usd"]), Decimal(digits))

    def test_decimal_sum_is_exact_independent_of_global_context(self):
        with localcontext() as ctx:
            ctx.prec = 4
            result = decimal_add(Decimal("0.123456789012345678901"), Decimal("0.000000000000000000001"))
        self.assertEqual(result, Decimal("0.123456789012345678902"))

    def test_decimal_accepts_only_nonnegative_finite_numbers(self):
        for value in (True, False, None, [], {}, "NaN", "Infinity", float("nan"), float("inf"), -1, "-1", " 1", "1 ", "1_000", "1,000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                decimal_value(value)
        for value in ("0", 0, 1, 0.25, "1e-9", Decimal("0.1")):
            with self.subTest(value=value):
                self.assertTrue(decimal_value(value).is_finite())

    def test_pricing_source_cannot_store_url_credentials_or_free_text(self):
        for source in ("https://host/prices", "operator@example.com", "Bearer secret", "sk-123456secret", "key=secret", "source\nsecret", "a" * 161, None):
            with self.subTest(source=source), self.assertRaises(ValueError):
                PricingTable(synthetic_table(source=source))

    def test_invalid_pricing_fields_rejected(self):
        cases = [({"provider": "unknown"}), ({"model": "model secret"}), ({"as_of": "2026-02-30"}),
                 ({"as_of": "2026-1-1"}), ({"as_of": "2026-01-01T00:00:00Z"}),
                 ({"input_usd_per_million": True}), ({"output_usd_per_million": "-1"}),
                 ({"cached_input_usd_per_million": float("nan")}), ({"input_usd_per_million": None})]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                PricingTable(synthetic_table(**overrides))
        for data in ([], {"schema_version": True, "rates": []}, {"schema_version": 2, "rates": []},
                     {"schema_version": 1, "rates": {}}, {"schema_version": 1, "rates": [None]}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                PricingTable(data)

    def test_duplicate_rates_rejected_and_unknown_rate_fields_dropped(self):
        data = synthetic_table(api_key="DO_NOT_STORE", prompt="DO_NOT_STORE")
        table = PricingTable(data)
        snapshot = table.resolve(priced_event())["pricing_snapshot"]
        self.assertNotIn("api_key", snapshot)
        self.assertNotIn("prompt", snapshot)
        data["rates"].append(deepcopy(data["rates"][0]))
        with self.assertRaises(ValueError):
            PricingTable(data)

    def test_snapshot_is_not_mutated_by_operator_or_caller(self):
        data = synthetic_table()
        table = PricingTable(data)
        data["rates"][0]["input_usd_per_million"] = "999"
        snapshot = table.resolve(priced_event())["pricing_snapshot"]
        snapshot["input_usd_per_million"] = "555"
        self.assertEqual(table.resolve(priced_event())["pricing_snapshot"]["input_usd_per_million"], "2")

    def test_json_numeric_rates_keep_original_decimal_digits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rates.json"
            text = json.dumps(synthetic_table()).replace('"2"', '0.123456789012345678901234567890123456789')
            path.write_text(text)
            table = PricingTable.from_file(path)
            self.assertEqual(table.resolve(priced_event())["pricing_snapshot"]["input_usd_per_million"], "0.123456789012345678901234567890123456789")

    def test_default_only_reads_optional_local_json_not_system_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "data").mkdir()
            (root / "config" / "system.yaml").write_text("api_key: DO_NOT_READ")
            data = types.ModuleType("core.data_dir")
            data.DATA_DIR = root / "data"
            with mock.patch.object(pricing, "__file__", str(root / "core" / "usage" / "pricing.py")), \
                 mock.patch.dict("sys.modules", {"core.data_dir": data}):
                self.assertEqual(get_default_pricing().resolve(priced_event())["cost_reason"], "missing_rates")
                (root / "data" / "usage_pricing.json").write_text(json.dumps(synthetic_table(source="data-test")))
                self.assertEqual(get_default_pricing().resolve(priced_event())["pricing_snapshot"]["source"], "data-test")
                (root / "config" / "usage_pricing.json").write_text(json.dumps(synthetic_table(source="root-test")))
                self.assertEqual(get_default_pricing().resolve(priced_event())["pricing_snapshot"]["source"], "root-test")
                (root / "config" / "usage_pricing.json").write_text("malformed")
                result = get_default_pricing().resolve(priced_event())
                self.assertEqual(result["cost_reason"], "invalid_pricing")
                self.assertIsNone(result["cost_usd"])

    def test_pricing_file_size_and_invalid_json_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rates.json"
            for content in ("{" * 1_048_577, "not JSON", '\ufeff{"schema_version":1,"rates":[]}'):
                path.write_text(content)
                with self.subTest(length=len(content)), self.assertRaises(ValueError):
                    PricingTable.from_file(path)


if __name__ == "__main__":
    unittest.main()
