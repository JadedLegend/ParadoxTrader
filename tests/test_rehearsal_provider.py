"""No paid calls: every provider test injects HTTP and blocks sockets."""
from copy import deepcopy
from decimal import Decimal
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.runtime.rehearsal.provider import (
    AGENT_IDS, CAPABILITIES, LIMIT_CEILINGS, ManifestError, OpenRouterTransport,
    ProviderError, bounded_input, catalog_snapshot, synthetic_catalog_snapshot,
    validate_manifest,
)
from core.runtime.rehearsal.store import RehearsalStore, RehearsalBudgetExceeded, RehearsalStopped
from core.usage.pricing import PricingTable
from core.usage.store import UsageStore


def manifest(mode="offline", **limits):
    models = {owner: "example/" + owner for owner in AGENT_IDS}
    snapshot = synthetic_catalog_snapshot(models)
    if mode == "real":
        snapshot["source"] = "openrouter"
        for row in snapshot["models"]:
            row["pricing"] = {"prompt": "0.000001", "completion": "0.000002", "request": "0.001"}
    return {"schema_version": 1, "mode": mode, "agent_models": models,
            "limits": dict(LIMIT_CEILINGS, budget_usd="10", **limits),
            "catalog_snapshot": snapshot, "capabilities": list(CAPABILITIES)}


class Response:
    def __init__(self, content='{"action":"rest"}', *, status=200, finish="stop", model="example/tempest", provider="mock-upstream", usage=None):
        self.status_code = status
        self.data = {"model": model, "provider": provider,
                     "choices": [{"message": {"content": content}, "finish_reason": finish}]}
        if usage is not None:
            self.data["usage"] = usage

    def json(self):
        return self.data


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.blocked = patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden"))
        self.blocked.start()
        self.addCleanup(self.blocked.stop)
        self.store = RehearsalStore(self.temp.name)
        self.run_id = self.store.prepare(manifest("real"))["run_id"]
        self.token = self.store.begin(self.run_id)
        self.job = self.store.claim_job(self.run_id, "tempest-r1", self.token)
        self.calls = []

    def call(self, response=None, post=None, **kwargs):
        def http(url, **request):
            self.calls.append((url, request))
            return response or Response()
        transport = OpenRouterTransport("explicit-fake-key", http_post=post or http, is_live=True)
        return transport.generate(store=self.store, run_id=self.run_id, token=self.token,
                                  wake_id=self.job["wake_id"], agent_id="tempest", activity="choice",
                                  messages=[{"role": "user", "content": "bounded private prompt"}], **kwargs)

    def test_one_post_caps_routing_and_unknown_coverage(self):
        self.assertEqual(self.call(), '{"action":"rest"}')
        self.assertEqual(len(self.calls), 1)
        url, kwargs = self.calls[0]
        self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], 60)
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "example/tempest")
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertTrue(payload["provider"]["require_parameters"])
        self.assertFalse(payload["provider"]["allow_fallbacks"])
        self.assertEqual(payload["provider"]["max_price"]["prompt"], 1)
        self.assertEqual(payload["provider"]["max_price"]["completion"], 2)
        for key in ("models", "tools", "plugins", "transforms", "trace", "max_completion_tokens"):
            self.assertNotIn(key, payload)
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertEqual(event["response_model"], "example/tempest")
        self.assertEqual(event["provider"], "mock-upstream")
        self.assertEqual(event["cost_status"], "unknown")
        self.assertIsNone(event["cost_usd"])
        self.assertGreater(Decimal(event["reserved_usd"]), 0)
        self.assertGreater(event["input_bytes"], len("bounded private prompt".encode()))
        ledger = UsageStore(self.store.run_path(self.run_id) / "usage.sqlite3", PricingTable()).list_events()["events"][0]
        self.assertEqual(ledger["cost_status"], "unknown")
        self.assertNotIn("private prompt", str(event) + str(ledger))
        self.assertNotIn("explicit-fake-key", str(event) + str(ledger))

    def test_reservation_exists_before_http(self):
        def http(_url, **kwargs):
            self.assertEqual(self.store.get_run(self.run_id)["request_count"], 1)
            self.assertEqual(self.store.list_requests(self.run_id)["events"][0]["outcome"], "in_flight")
            return Response(usage={"prompt_tokens": 4, "completion_tokens": 2, "cost": "0"})
        self.call(post=http)
        self.assertEqual(self.store.get_run(self.run_id)["unknown_cost_requests"], 0)
        self.assertEqual(self.store.get_run(self.run_id)["known_cost_usd"], "0")

    def test_transport_error_is_uncertain_private_and_not_retried(self):
        def http(_url, **kwargs):
            self.calls.append(kwargs)
            raise TimeoutError("secret provider body and explicit-fake-key")
        with self.assertRaises(ProviderError) as raised:
            self.call(post=http)
        self.assertTrue(raised.exception.uncertain)
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(len(self.calls), 1)
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertEqual(event["outcome"], "uncertain")
        self.assertIsNone(event["cost_usd"])
        self.store.end(self.run_id, self.token)
        self.assertEqual(self.store.list_jobs(self.run_id)[0]["status"], "uncertain")

    def test_length_failure_never_repaired_or_retried(self):
        with self.assertRaisesRegex(ProviderError, "output_truncated"):
            self.call(Response(finish="length", usage={"cost": "0.001"}))
        self.assertEqual(len(self.calls), 1)
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertEqual(event["outcome"], "invalid_response")
        self.assertEqual(event["cost_usd"], "0.001")

    def test_schema_rejected_before_success_checkpoint(self):
        from core.runtime.rehearsal.controller import validate_choice
        with self.assertRaisesRegex(ProviderError, "invalid_activity_output"):
            self.call(Response(content='```json\n{"action":"rest"}\n```'), validator=validate_choice)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.list_requests(self.run_id)["events"][0]["outcome"], "invalid_response")

    def test_missing_returned_metadata_stays_null(self):
        self.call(Response(model=None, provider=None))
        event = self.store.list_requests(self.run_id)["events"][0]
        self.assertIsNone(event["response_model"])
        self.assertIsNone(event["provider"])

    def test_redirect_rejected_no_second_post(self):
        with self.assertRaisesRegex(ProviderError, "http_rejected"):
            self.call(Response(status=302))
        self.assertEqual(len(self.calls), 1)

    def test_no_implicit_key(self):
        for key in (None, "", "\nsecret", "has whitespace"):
            with self.subTest(key=key), self.assertRaises(ProviderError):
                OpenRouterTransport(key)
        with self.assertRaises(ProviderError):
            OpenRouterTransport("fake", is_live=False)

    def test_stop_and_input_bounds_prevent_http(self):
        self.store.request_stop(self.run_id)
        with self.assertRaises(RehearsalStopped):
            self.call()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 0)

    def test_utf8_protocol_bound(self):
        messages = [{"role": "user", "content": "é" * 15000}]
        self.assertGreater(bounded_input(messages), 30000)
        transport = OpenRouterTransport("fake", http_post=lambda *a, **k: self.fail("HTTP forbidden"), is_live=True)
        with self.assertRaisesRegex(ProviderError, "input_bound_exceeded"):
            transport.generate(store=self.store, run_id=self.run_id, token=self.token, wake_id=self.job["wake_id"],
                               agent_id="tempest", activity="choice", messages=messages)
        self.assertEqual(self.store.get_run(self.run_id)["request_count"], 0)

    def test_conservative_budget_rejects_before_http(self):
        store = RehearsalStore(self.temp.name + "/tiny")
        raw = manifest("real")
        raw["limits"]["budget_usd"] = "0.000001"
        run_id = store.prepare(raw)["run_id"]
        token = store.begin(run_id)
        store.claim_job(run_id, "tempest-r1", token)
        transport = OpenRouterTransport("fake", http_post=lambda *a, **k: self.fail("no budget"), is_live=True)
        with self.assertRaises(RehearsalBudgetExceeded):
            transport.generate(store=store, run_id=run_id, token=token, wake_id="tempest-r1", agent_id="tempest",
                               activity="choice", messages=[{"role": "user", "content": "x"}])
        self.assertEqual(store.get_run(run_id)["request_count"], 0)


class ManifestTests(unittest.TestCase):
    def test_pure_selected_seven_map(self):
        raw = manifest("real")
        original = deepcopy(raw)
        clean = validate_manifest(raw)
        self.assertEqual(validate_manifest(clean), clean)
        self.assertEqual(Decimal(clean["limits"]["budget_usd"]), Decimal(raw["limits"]["budget_usd"]))
        self.assertEqual(raw, original)
        catalog = {"data": deepcopy(raw["catalog_snapshot"]["models"]) + [{"id": "unused/model", "secret": "discard"}]}
        snapshot = catalog_snapshot(raw["agent_models"], catalog)
        self.assertEqual(len(snapshot["models"]), 7)
        self.assertNotIn("unused", str(snapshot))
        self.assertNotIn("secret", str(snapshot))

    def test_rejects_absent_model_unsupported_params_caps_context_prices(self):
        raw = manifest("real")
        variants = []
        for key, value in (("supported_parameters", ["temperature"]), ("max_completion_tokens", None),
                           ("max_completion_tokens", 100), ("context_length", 24000),
                           ("context_length", True), ("pricing", {"prompt": "0", "completion": "0"})):
            bad = deepcopy(raw); bad["catalog_snapshot"]["models"][0][key] = value; variants.append(bad)
        for field, value in (("image", "0.01"), ("web_search", "0.01"), ("input_cache_read", "0.000001"),
                             ("completion", "NaN"), ("prompt", "-1"), ("request", True)):
            bad = deepcopy(raw); bad["catalog_snapshot"]["models"][0]["pricing"][field] = value; variants.append(bad)
        bad = deepcopy(raw); bad["catalog_snapshot"]["models"].pop(); variants.append(bad)
        bad = deepcopy(raw); bad["agent_models"]["eighth"] = "example/eighth"; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(ManifestError):
                validate_manifest(bad)

    def test_live_catalog_price_lines_translate_and_stay_strict(self):
        raw = manifest("real")
        catalog = {"data": deepcopy(raw["catalog_snapshot"]["models"])}
        for row in catalog["data"]:  # Shape OpenRouter returns today: no "request", extra lines.
            row["pricing"] = {"prompt": "0.000002", "completion": "0.00001", "image": "0.000002",
                              "audio": "0.000002", "web_search": "0.014", "internal_reasoning": "0.00001",
                              "input_cache_read": "0.0000001", "input_cache_write": "0.0000001875"}
        rows = catalog_snapshot(raw["agent_models"], catalog)["models"]
        self.assertEqual(rows[0]["pricing"], {"prompt": "0.000002", "completion": "0.00001", "request": "0"})
        dearer = deepcopy(catalog)  # Dearer cache writes and reasoning raise the reservation, never slip past it.
        dearer["data"][0]["pricing"].update(input_cache_write="0.0000025", internal_reasoning="0.00002")
        self.assertEqual(catalog_snapshot(raw["agent_models"], dearer)["models"][0]["pricing"],
                         {"prompt": "0.0000025", "completion": "0.00002", "request": "0"})
        for unit, value in (("video", "0.01"), ("image", "NaN")):
            bad = deepcopy(catalog); bad["data"][0]["pricing"][unit] = value
            with self.subTest(unit=unit), self.assertRaises(ManifestError):
                catalog_snapshot(raw["agent_models"], bad)
        bad = deepcopy(catalog); del bad["data"][0]["pricing"]["completion"]
        with self.assertRaisesRegex(ManifestError, "missing_catalog_price"):
            catalog_snapshot(raw["agent_models"], bad)

    def test_time_of_day_and_long_prompt_tiers_reserve_the_dearest_tier(self):
        raw = manifest("real")
        catalog = {"data": deepcopy(raw["catalog_snapshot"]["models"])}
        for row in catalog["data"]:  # The shapes OpenRouter lists on 2026-11-19.
            row["pricing"] = {"prompt": "0.00000015", "completion": "0.0000006", "input_cache_read": "0.000000003",
                              "overrides": [{"utc_days": ["monday"], "utc_start": 100, "utc_end": 400,
                                             "prompt": "0.0000003", "completion": "0.0000012"},
                                            {"min_prompt_tokens": 272000, "prompt": "0.0000004",
                                             "input_cache_write": "0.0000005"}]}
        pricing = catalog_snapshot(raw["agent_models"], catalog)["models"][0]["pricing"]
        self.assertEqual({line: Decimal(value) for line, value in pricing.items()},
                         {"prompt": Decimal("0.0000005"), "completion": Decimal("0.0000012"), "request": Decimal(0)})
        for tiers in ([{"utc_days": ["monday"]}], [{"prompt": "0.1", "video": "0.01"}], "cheap", [{"weird": "x"}]):
            bad = deepcopy(catalog); bad["data"][0]["pricing"]["overrides"] = tiers
            with self.subTest(tiers=tiers), self.assertRaises(ManifestError):
                catalog_snapshot(raw["agent_models"], bad)

    def test_overrides_rejected_during_catalog_normalization(self):
        raw = manifest("real")
        for override in ({"pricing_overrides": {"prompt": "0.1"}},
                         {"top_provider": {"pricing": {"prompt": "0.1"}}}):
            catalog = {"data": deepcopy(raw["catalog_snapshot"]["models"])}
            catalog["data"][0].update(override)
            with self.assertRaisesRegex(ManifestError, "unsupported_pricing_override"):
                catalog_snapshot(raw["agent_models"], catalog)

    def test_api_top_provider_cap_normalizes(self):
        raw = manifest("real")
        catalog = {"data": deepcopy(raw["catalog_snapshot"]["models"])}
        for row in catalog["data"]:
            row["top_provider"] = {"max_completion_tokens": row.pop("max_completion_tokens")}
        self.assertEqual(len(catalog_snapshot(raw["agent_models"], catalog)["models"]), 7)
        catalog["data"].pop()
        with self.assertRaisesRegex(ManifestError, "selected_model_absent"):
            catalog_snapshot(raw["agent_models"], catalog)

    def test_synthetic_explicit_not_real_readiness(self):
        raw = manifest()
        self.assertEqual(validate_manifest(raw)["catalog_snapshot"]["source"], "synthetic")
        raw["mode"] = "real"
        with self.assertRaisesRegex(ManifestError, "real_catalog_required"):
            validate_manifest(raw)
        raw = manifest(); raw["catalog_snapshot"].pop("source")
        with self.assertRaisesRegex(ManifestError, "explicit_synthetic"):
            validate_manifest(raw)

    def test_unknown_fields_and_raised_bounds_rejected(self):
        raw = manifest("real")
        for key, ceiling in LIMIT_CEILINGS.items():
            bad = deepcopy(raw); bad["limits"][key] = ceiling + 1
            with self.subTest(key=key), self.assertRaises(ManifestError):
                validate_manifest(bad)
        raw["capabilities"].append("trade")
        with self.assertRaises(ManifestError):
            validate_manifest(raw)
        raw = manifest("real"); raw["limits"]["budget_usd"] = "0"
        with self.assertRaisesRegex(ManifestError, "positive_real_budget_required"):
            validate_manifest(raw)


if __name__ == "__main__":
    unittest.main()
