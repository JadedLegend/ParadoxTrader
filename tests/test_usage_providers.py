"""Offline request-accounting adapters: python -m unittest tests.test_usage_providers -v.

Response fixtures verify accepted syntax only; their costs are not provider rates
or assertions about real invoices. All provider and tracing calls are mocks.
"""
import contextlib
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
import os
import socket
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest import mock
from uuid import UUID


TRACING_ENV = (
    "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_TRACING",
    "LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2",
)


def disable_services(stack, data_dir):
    values = {name: "" for name in TRACING_ENV}
    values.update(DATA_DIR=data_dir, LANGCHAIN_TRACING_V2="false",
                  LANGSMITH_TRACING="false", OPENROUTER_API_KEY="",
                  PERPLEXITY_API_KEY="")
    stack.enter_context(mock.patch.dict(os.environ, values))


def block_network(stack):
    guards = [stack.enter_context(mock.patch.object(
        target, name, side_effect=AssertionError("Network forbidden in offline provider tests")
    )) for target, name in (
        (socket.socket, "connect"), (socket.socket, "connect_ex"),
        (socket, "create_connection"),
    )]
    import requests
    guards.append(stack.enter_context(mock.patch.object(
        requests.sessions.Session, "request",
        side_effect=AssertionError("HTTP forbidden in offline provider tests"),
    )))
    return guards


# No actual LangSmith setup or service connection during project import.
_IMPORT_DATA = TemporaryDirectory(prefix="usage-provider-import-")
with contextlib.ExitStack() as _imports:
    disable_services(_imports, _IMPORT_DATA.name)
    _import_guards = block_network(_imports)
    from core.runtime import llm
    from core.research import perplexity
    for _guard in _import_guards:
        _guard.assert_not_called()


def tearDownModule():
    _IMPORT_DATA.cleanup()


class Response:
    def __init__(self, data=None, status=200, json_error=None):
        self.data = data
        self.status_code = status
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("private provider HTTP error, do not persist")


def body(usage=None, model="provider/reported-model", content="private answer"):
    result = {
        "model": model, "choices": [{"message": {"content": content}}],
        "citations": ["https://private.example/query"],
        "private_extra": "must not persist",
    }
    if usage is not None:
        result["usage"] = usage
    return result


EVENT_FIELDS = {
    "event_id", "call_id", "wake_id", "agent_id", "activity", "provider",
    "model", "attempt", "created_at", "duration_ms", "outcome", "http_status",
    "input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
    "reasoning_tokens", "provider_cost_usd",
}
TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens",
                "cached_input_tokens", "reasoning_tokens")


class OfflineProviderCase(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(TemporaryDirectory(prefix="usage-provider-test-"))
        disable_services(self.stack, self.tmp)
        for guard in block_network(self.stack):
            self.addCleanup(guard.assert_not_called)
        self.patch(llm, "_langsmith_enabled", False)
        self.patch(llm, "_get_api_key", return_value="dummy-openrouter-key")
        self.patch(llm.time, "sleep")
        self.patch(perplexity, "REQUESTS_AVAILABLE", True)
        self.patch(perplexity, "_get_key", return_value="dummy-perplexity-key")
        self.events = []
        self.context = {"activity": "research", "wake_id": "offline-wake"}
        # The provider contract is independent of real storage implementation.
        self.usage_module = types.ModuleType("core.usage")
        self.usage_module.__path__ = []
        self.recorder = mock.Mock(side_effect=self.capture)
        self.usage_module.record_usage = self.recorder
        self.context_module = types.ModuleType("core.usage.context")
        self.context_module.current_usage_context = mock.Mock(side_effect=lambda: dict(self.context))
        self.stack.enter_context(mock.patch.dict(sys.modules, {
            "core.usage": self.usage_module, "core.usage.context": self.context_module,
        }))

    def capture(self, event):
        self.events.append(dict(event))
        return True

    def patch(self, target, name, *args, **kwargs):
        return self.stack.enter_context(mock.patch.object(target, name, *args, **kwargs))

    def call_openrouter(self, **kwargs):
        return llm.call_llm("offline-agent", [{"role": "user", "content": "private prompt"}],
                            system_prompt="private system prompt", model_override="requested/model",
                            retry_delay=0, **kwargs)

    def call_perplexity(self, method, **kwargs):
        return getattr(perplexity, method)("private query", agent_id="offline-agent", **kwargs)

    def assert_event(self, event, provider, outcome="success", status=200):
        self.assertLessEqual(set(event), EVENT_FIELDS | {"response_model"})
        self.assertTrue(EVENT_FIELDS.issubset(event))
        self.assertEqual(event["provider"], provider)
        self.assertEqual(event["agent_id"], "offline-agent")
        self.assertEqual(event["activity"], self.context["activity"])
        self.assertEqual(event["wake_id"], self.context["wake_id"])
        self.assertEqual(event["outcome"], outcome)
        self.assertEqual(event["http_status"], status)
        self.assertEqual(str(UUID(event["event_id"])), event["event_id"])
        self.assertEqual(str(UUID(event["call_id"])), event["call_id"])
        timestamp = datetime.fromisoformat(event["created_at"])
        self.assertEqual(timestamp.utcoffset(), timezone.utc.utcoffset(timestamp))
        self.assertTrue(math.isfinite(event["duration_ms"]))
        self.assertGreaterEqual(event["duration_ms"], 0)
        text = json.dumps(event)
        for secret in ("private", "dummy-openrouter-key", "dummy-perplexity-key", "Authorization",
                       "choices", "citations", "messages", "headers", "query", "answer"):
            self.assertNotIn(secret, text)


class UsageMetadataTests(OfflineProviderCase):
    def test_complete_counts_and_reasoning_are_not_added_to_total(self):
        usage = {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18,
                 "prompt_tokens_details": {"cached_tokens": 3},
                 "completion_tokens_details": {"reasoning_tokens": 5}, "cost": "0.012300"}
        for module in (llm, perplexity):
            with self.subTest(provider=module.__name__):
                metadata = module._usage_metadata(body(usage))
                self.assertEqual(metadata, {
                    "input_tokens": 10, "output_tokens": 8, "total_tokens": 18,
                    "cached_input_tokens": 3, "reasoning_tokens": 5,
                    "provider_cost_usd": "0.0123", "response_model": "provider/reported-model",
                })

    def test_absent_usage_and_partial_counts_stay_unknown(self):
        for module in (llm, perplexity):
            for data in (None, [], "private", {}, {"usage": None}, {"usage": []},
                         {"usage": {"prompt_tokens_details": []}}):
                with self.subTest(provider=module.__name__, data=data):
                    metadata = module._usage_metadata(data)
                    self.assertEqual(set(metadata), set(TOKEN_FIELDS) | {"provider_cost_usd"})
                    self.assertTrue(all(value is None for value in metadata.values()))
            metadata = module._usage_metadata({"usage": {"prompt_tokens": 4}})
            self.assertEqual(metadata["input_tokens"], 4)
            self.assertIsNone(metadata["total_tokens"])
            self.assertIsNone(metadata["cached_input_tokens"])
            self.assertIsNone(metadata["provider_cost_usd"])

    def test_token_counts_accept_only_nonnegative_nonboolean_integers(self):
        for module in (llm, perplexity):
            for value in (None, True, False, -1, 1.0, "12", {}, [], float("nan")):
                with self.subTest(provider=module.__name__, value=value):
                    metadata = module._usage_metadata({"usage": {
                        "prompt_tokens": value, "completion_tokens": value, "total_tokens": value,
                        "prompt_tokens_details": {"cached_tokens": value},
                        "completion_tokens_details": {"reasoning_tokens": value},
                    }})
                    for field in TOKEN_FIELDS:
                        self.assertIsNone(metadata[field])
            for value in (0, 12):
                metadata = module._usage_metadata({"usage": {"prompt_tokens": value}})
                self.assertEqual(metadata["input_tokens"], value)

    def test_inconsistent_subsets_become_unknown_without_losing_cost_or_total(self):
        for module in (llm, perplexity):
            metadata = module._usage_metadata({"usage": {
                "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 4},
                "completion_tokens_details": {"reasoning_tokens": 8}, "cost": "0.004",
            }})
            self.assertEqual(metadata["input_tokens"], 3)
            self.assertEqual(metadata["output_tokens"], 2)
            self.assertEqual(metadata["total_tokens"], 5)
            self.assertEqual(metadata["provider_cost_usd"], "0.004")
            self.assertIsNone(metadata["cached_input_tokens"])
            self.assertIsNone(metadata["reasoning_tokens"])
            metadata = module._usage_metadata({"usage": {
                "prompt_tokens_details": {"cached_tokens": 4},
                "completion_tokens_details": {"reasoning_tokens": 8},
            }})
            self.assertEqual(metadata["cached_input_tokens"], 4)
            self.assertEqual(metadata["reasoning_tokens"], 8)

    def test_cost_scalar_syntax_decimal_and_zero(self):
        for module in (llm, perplexity):
            for value, expected in ((0, "0"), (0.0, "0"), ("0.000", "0"),
                                    (Decimal("0.0012300"), "0.00123"), ("1e-3", "0.001"),
                                    ("1.2300", "1.23"), (2, "2"), (0.125, "0.125")):
                with self.subTest(provider=module.__name__, value=value):
                    self.assertEqual(module._usage_metadata({"usage": {"cost": value}})
                                     ["provider_cost_usd"], expected)
            for value in (None, True, False, -1, "-0.1", "NaN", "Infinity", "sNaN",
                          float("nan"), float("inf"), "bad", {}, [], "1e999999", "1e-999999",
                          "9" * 129, "1_000", " 0.1 ", "1." + "1" * 119 + "e-100"):
                with self.subTest(provider=module.__name__, invalid=value):
                    self.assertIsNone(module._usage_metadata({"usage": {"cost": value}})
                                      ["provider_cost_usd"])

    def test_perplexity_total_cost_only_not_components_or_top_level_cost(self):
        data = {"cost": "100", "usage": {"cost": {
            "total_cost": "0.01500", "input_tokens_cost": "7", "request_cost": "8",
        }}}
        self.assertEqual(perplexity._usage_metadata(data)["provider_cost_usd"], "0.015")
        self.assertIsNone(llm._usage_metadata(data)["provider_cost_usd"])
        for data in ({"cost": "0.1"}, {"usage": {"total_cost": "0.1"}},
                     {"usage": {"cost": {"request_cost": "0.1"}}},
                     {"usage": {"cost": {"total_cost": True}}}):
            self.assertIsNone(perplexity._usage_metadata(data)["provider_cost_usd"])
        self.assertEqual(perplexity._usage_metadata({"usage": {"cost": {"total_cost": 0}}})
                         ["provider_cost_usd"], "0")

    def test_response_model_safe_bounded_allowlist(self):
        for module in (llm, perplexity):
            for value in (None, {}, 12, "", "private model", "model\nsecret", "a" * 129,
                          "<script>", "model?query=private"):
                with self.subTest(provider=module.__name__, value=value):
                    self.assertNotIn("response_model", module._usage_metadata({"model": value}))
            for value in ("a" * 128, "provider/model-v1.2:free", "model_1@2026+v2"):
                self.assertEqual(module._usage_metadata({"model": value})["response_model"], value)


class OpenRouterAttemptTests(OfflineProviderCase):
    def test_success_preserves_request_and_return_and_records_one_event(self):
        before = datetime.now(timezone.utc)
        post = self.patch(llm.requests, "post", return_value=Response(body({
            "prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6, "cost": "0.0040",
        })))
        self.assertEqual(self.call_openrouter(), "private answer")
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args, ("https://openrouter.ai/api/v1/chat/completions",))
        self.assertEqual(kwargs["timeout"], 90)
        self.assertEqual(kwargs["json"], {
            "model": "requested/model", "messages": [
                {"role": "system", "content": "private system prompt"},
                {"role": "user", "content": "private prompt"},
            ], "temperature": 0.7, "max_tokens": 1024,
        })
        self.recorder.assert_called_once()
        event = self.events[0]
        self.assert_event(event, "openrouter")
        self.assertEqual(event["model"], "requested/model")
        self.assertEqual(event["response_model"], "provider/reported-model")
        self.assertEqual(event["provider_cost_usd"], "0.004")
        self.assertGreaterEqual(datetime.fromisoformat(event["created_at"]), before)

    def test_retries_record_each_http_attempt_one_call_id_and_fresh_event_ids(self):
        post = self.patch(llm.requests, "post", side_effect=[
            TimeoutError("private transport error"),
            Response(body({"cost": "0.001", "prompt_tokens": 3}), status=429),
            Response(json_error=ValueError("private invalid JSON")),
            Response(body({"cost": 0})),
        ])
        self.assertEqual(self.call_openrouter(retries=4), "private answer")
        self.assertEqual(post.call_count, 4)
        self.assertEqual(self.recorder.call_count, 4)
        self.assertEqual(len({e["call_id"] for e in self.events}), 1)
        self.assertEqual(len({e["event_id"] for e in self.events}), 4)
        self.assertEqual([e["attempt"] for e in self.events], [1, 2, 3, 4])
        for event, outcome, status in zip(self.events,
                ("transport_error", "http_error", "invalid_response", "success"),
                (None, 429, 200, 200)):
            self.assert_event(event, "openrouter", outcome, status)
        self.assertEqual([e["provider_cost_usd"] for e in self.events], [None, "0.001", None, "0"])
        self.assertEqual(self.events[1]["input_tokens"], 3)
        self.assertEqual(llm.time.sleep.call_count, 3)

    def test_failed_attempts_exhaust_without_fake_cost(self):
        post = self.patch(llm.requests, "post", side_effect=TimeoutError("private transport error"))
        with self.assertRaises(RuntimeError):
            self.call_openrouter(retries=2)
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.recorder.call_count, 2)
        for event in self.events:
            self.assert_event(event, "openrouter", "transport_error", None)
            self.assertIsNone(event["provider_cost_usd"])

    def test_invalid_response_content_retries_and_does_not_return_nonstring(self):
        for invalid in (None, 5, {}, [], True):
            with self.subTest(content=invalid):
                self.events.clear()
                self.recorder.reset_mock()
                with mock.patch.object(llm.requests, "post", side_effect=[
                    Response(body({"cost": "0.002"}, content=invalid)), Response(body()),
                ]) as post:
                    self.assertEqual(self.call_openrouter(retries=2), "private answer")
                    self.assertEqual(post.call_count, 2)
                self.assertEqual(self.events[0]["outcome"], "invalid_response")
                self.assertEqual(self.events[0]["provider_cost_usd"], "0.002")
                self.assertEqual(self.events[1]["outcome"], "success")

    def test_malformed_payload_and_non2xx_json_errors_are_counted(self):
        cases = [(Response(data={}), "invalid_response", 200),
                 (Response(data=[]), "invalid_response", 200),
                 (Response(body(), status=302), "http_error", 302),
                 (Response(status=503, json_error=ValueError("private invalid JSON")), "http_error", 503)]
        for response, outcome, status in cases:
            with self.subTest(outcome=outcome, status=status):
                self.events.clear()
                with mock.patch.object(llm.requests, "post", return_value=response) as post:
                    with self.assertRaises(RuntimeError):
                        self.call_openrouter(retries=1)
                    post.assert_called_once()
                self.assertEqual(len(self.events), 1)
                self.assert_event(self.events[0], "openrouter", outcome, status)
                self.assertIsNone(self.events[0]["provider_cost_usd"])

    def test_preflight_without_requests_or_key_has_no_event(self):
        post = self.patch(llm.requests, "post", side_effect=AssertionError("Unexpected provider call"))
        with mock.patch.object(llm, "requests", None):
            with self.assertRaises(ImportError):
                self.call_openrouter()
        with mock.patch.object(llm, "_get_api_key", return_value=""):
            with self.assertRaises(ValueError):
                self.call_openrouter()
        post.assert_not_called()
        self.recorder.assert_not_called()
        self.context_module.current_usage_context.assert_not_called()

    def test_distinct_logical_calls_and_unattributed_context(self):
        self.context = {"activity": "unattributed", "wake_id": None}
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        self.call_openrouter()
        self.call_openrouter()
        self.assertEqual(post.call_count, 2)
        self.assertNotEqual(self.events[0]["call_id"], self.events[1]["call_id"])
        for event in self.events:
            self.assert_event(event, "openrouter")
            self.assertIsNone(event["provider_cost_usd"])

    def test_recording_failure_never_retries_successful_paid_request(self):
        post = self.patch(llm.requests, "post", return_value=Response(body({"cost": "0.003"})))
        for failure in (False, OSError("private database error")):
            with self.subTest(failure=type(failure).__name__):
                post.reset_mock()
                self.recorder.reset_mock()
                self.recorder.side_effect = failure if isinstance(failure, Exception) else None
                self.recorder.return_value = False
                with self.assertLogs(llm.__name__, level="WARNING") as logs:
                    self.assertEqual(self.call_openrouter(), "private answer")
                post.assert_called_once()
                self.recorder.assert_called_once()
                self.assertTrue(all(message.endswith(":usage_recording_failed") for message in logs.output))

    def test_ledger_errors_do_not_change_provider_retry_count(self):
        self.recorder.side_effect = OSError("private database error")
        post = self.patch(llm.requests, "post", side_effect=[
            TimeoutError("private timeout"), Response(body()),
        ])
        with self.assertLogs(llm.__name__, level="WARNING"):
            self.assertEqual(self.call_openrouter(retries=2), "private answer")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.recorder.call_count, 2)

    def test_missing_ledger_and_warning_failure_are_best_effort(self):
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        with mock.patch.dict(sys.modules, {"core.usage": None}):
            with self.assertLogs(llm.__name__, level="WARNING"):
                self.assertEqual(self.call_openrouter(), "private answer")
        self.recorder.side_effect = OSError("private storage error")
        with mock.patch.object(llm._logger, "warning", side_effect=RuntimeError("private log error")):
            self.assertEqual(self.call_openrouter(), "private answer")
        self.assertEqual(post.call_count, 2)

    def test_duration_excludes_retry_backoff_and_timestamp_precedes_http(self):
        self.patch(llm.time, "perf_counter", side_effect=[10.0, 10.025, 12.0, 12.050])
        def attempt(*args, **kwargs):
            self.assertEqual(len(self.events), post.call_count - 1)
            if post.call_count == 1:
                raise TimeoutError("private timeout")
            return Response(body())
        post = self.patch(llm.requests, "post", side_effect=attempt)
        self.call_openrouter(retries=2)
        self.assertAlmostEqual(self.events[0]["duration_ms"], 25.0)
        self.assertAlmostEqual(self.events[1]["duration_ms"], 50.0)


class PerplexityAttemptTests(OfflineProviderCase):
    def test_research_quick_and_deep_preserve_payload_and_returns(self):
        for method, extra, model, timeout in (
            ("research", {}, "sonar-pro", 60),
            ("research", {"deep": True, "system_context": "private context"}, "sonar-reasoning", 60),
            ("quick_search", {}, "sonar", 30),
        ):
            with self.subTest(method=method, model=model):
                self.events.clear()
                self.recorder.reset_mock()
                with mock.patch.object(perplexity.requests, "post", return_value=Response(body({
                    "prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8,
                    "cost": {"total_cost": "0.01300", "request_cost": "0.001"},
                }))) as post:
                    result = self.call_perplexity(method, **extra)
                    post.assert_called_once()
                    args, kwargs = post.call_args
                self.assertEqual(args, ("https://api.perplexity.ai/chat/completions",))
                self.assertEqual(kwargs["timeout"], timeout)
                payload = kwargs["json"]
                self.assertEqual(payload["model"], model)
                self.assertEqual(payload["max_tokens"], 512 if method == "quick_search" else 1024)
                self.assertTrue(payload["return_citations"])
                self.assertEqual(payload["search_recency_filter"], "day" if method == "quick_search" else "week")
                expected_fields = {"model", "messages", "max_tokens", "return_citations", "search_recency_filter"}
                if method == "research":
                    expected_fields.add("return_related_questions")
                    self.assertFalse(payload["return_related_questions"])
                    self.assertEqual(payload["messages"][0]["role"], "system")
                    if extra.get("system_context"):
                        self.assertIn("private context", payload["messages"][0]["content"])
                self.assertEqual(set(payload), expected_fields)
                self.assertEqual(payload["messages"][-1], {"role": "user", "content": "private query"})
                self.assertEqual(result, {"answer": "private answer", "citations": ["https://private.example/query"],
                                          "model": model, "query": "private query", "agent_id": "offline-agent"})
                self.recorder.assert_called_once()
                self.assert_event(self.events[0], "perplexity")
                self.assertEqual(self.events[0]["model"], model)
                self.assertEqual(self.events[0]["provider_cost_usd"], "0.013")

    def test_agent_framing_and_custom_max_tokens_unchanged(self):
        post = self.patch(perplexity.requests, "post", return_value=Response(body()))
        perplexity.research("private query", agent_id="tempest", max_tokens=256)
        payload = post.call_args.kwargs["json"]
        self.assertIn("momentum and volatility analyst", payload["messages"][0]["content"])
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(self.events[0]["agent_id"], "tempest")

    def test_failed_http_still_parses_known_usage_and_total_cost(self):
        for method in ("research", "quick_search"):
            with self.subTest(method=method):
                self.events.clear()
                with mock.patch.object(perplexity.requests, "post", return_value=Response(body({
                    "prompt_tokens": 5, "cost": {"total_cost": "0.020"},
                }), status=429)) as post:
                    result = self.call_perplexity(method)
                    post.assert_called_once()
                self.assertIn("error", result)
                self.assertEqual(result["query"], "private query")
                self.assert_event(self.events[0], "perplexity", "http_error", 429)
                self.assertEqual(self.events[0]["provider_cost_usd"], "0.02")
                self.assertEqual(self.events[0]["input_tokens"], 5)
                self.assertIsNone(self.events[0]["total_tokens"])

    def test_transport_json_and_bad_content_each_record_one_failure(self):
        cases = [TimeoutError("private timeout"),
                 Response(json_error=ValueError("private JSON error")),
                 Response(data={}), Response(body(content=None)),
                 Response(status=500, json_error=ValueError("private JSON error"))]
        for method in ("research", "quick_search"):
            for response in cases:
                with self.subTest(method=method, response=type(response).__name__):
                    self.events.clear()
                    side_effect = response if isinstance(response, Exception) else None
                    with mock.patch.object(perplexity.requests, "post", side_effect=side_effect,
                                           return_value=response) as post:
                        self.assertIn("error", self.call_perplexity(method))
                        post.assert_called_once()
                    if isinstance(response, Exception):
                        outcome, status = "transport_error", None
                    else:
                        status = response.status_code
                        outcome = "http_error" if status >= 400 else "invalid_response"
                    self.assertEqual(len(self.events), 1)
                    self.assert_event(self.events[0], "perplexity", outcome, status)
                    self.assertIsNone(self.events[0]["provider_cost_usd"])

    def test_preflight_without_requests_or_key_has_no_event(self):
        post = self.patch(perplexity.requests, "post", side_effect=AssertionError("Unexpected provider call"))
        for method in ("research", "quick_search"):
            with mock.patch.object(perplexity, "REQUESTS_AVAILABLE", False):
                self.assertEqual(self.call_perplexity(method), {"error": "requests not installed", "query": "private query"})
            with mock.patch.object(perplexity, "_get_key", return_value=""):
                self.assertEqual(self.call_perplexity(method), {"error": "PERPLEXITY_API_KEY not set", "query": "private query"})
        post.assert_not_called()
        self.recorder.assert_not_called()
        self.context_module.current_usage_context.assert_not_called()

    def test_ledger_failure_preserves_success_and_never_replays(self):
        for method in ("research", "quick_search"):
            for failure in (False, OSError("private database error")):
                with self.subTest(method=method, failure=type(failure).__name__):
                    self.recorder.side_effect = failure if isinstance(failure, Exception) else None
                    self.recorder.return_value = False
                    with mock.patch.object(perplexity.requests, "post", return_value=Response(body())) as post:
                        with self.assertLogs(perplexity.__name__, level="WARNING") as logs:
                            self.assertEqual(self.call_perplexity(method)["answer"], "private answer")
                        post.assert_called_once()
                    self.assertTrue(all(message.endswith(":usage_recording_failed") for message in logs.output))

    def test_optional_agent_and_direct_unattributed_call(self):
        self.context = {"activity": "unattributed", "wake_id": None}
        post = self.patch(perplexity.requests, "post", return_value=Response(body()))
        result = perplexity.quick_search("private query")
        post.assert_called_once()
        self.assertIsNone(result["agent_id"])
        self.assertIsNone(self.events[0]["agent_id"])
        self.assertEqual(self.events[0]["activity"], "unattributed")
        self.assertIsNone(self.events[0]["wake_id"])
        self.assertIsNone(self.events[0]["provider_cost_usd"])


class TracingFallbackTests(OfflineProviderCase):
    def install_traceable(self, decorator):
        module = types.ModuleType("langsmith")
        module.traceable = mock.Mock(side_effect=decorator)
        self.stack.enter_context(mock.patch.dict(sys.modules, {"langsmith": module}))
        self.patch(llm, "_langsmith_enabled", True)
        return module.traceable

    def test_decorator_setup_failure_runs_untraced_once(self):
        def decorator(**kwargs):
            raise RuntimeError("private trace setup failure")
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        with self.assertLogs(llm.__name__, level="WARNING") as logs:
            self.assertEqual(self.call_openrouter(), "private answer")
        post.assert_called_once()
        self.recorder.assert_called_once()
        self.assertTrue(all(message.endswith(":llm_tracing_failed") for message in logs.output))

    def test_wrapper_failure_before_entry_runs_untraced_once(self):
        def decorator(**kwargs):
            def wrap(function):
                def invoke(**call_kwargs):
                    raise RuntimeError("private trace pre-entry failure")
                return invoke
            return wrap
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        with self.assertLogs(llm.__name__, level="WARNING"):
            self.assertEqual(self.call_openrouter(), "private answer")
        post.assert_called_once()
        self.recorder.assert_called_once()

    def test_wrapper_return_without_provider_entry_runs_untraced_once(self):
        def decorator(**kwargs):
            return lambda function: lambda **call_kwargs: "trace replacement"
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        with self.assertLogs(llm.__name__, level="WARNING"):
            self.assertEqual(self.call_openrouter(), "private answer")
        post.assert_called_once()
        self.recorder.assert_called_once()

    def test_trace_import_failure_runs_untraced_once(self):
        self.patch(llm, "_langsmith_enabled", True)
        post = self.patch(llm.requests, "post", return_value=Response(body()))
        with mock.patch.dict(sys.modules, {"langsmith": None}):
            with self.assertLogs(llm.__name__, level="WARNING"):
                self.assertEqual(self.call_openrouter(), "private answer")
        post.assert_called_once()
        self.recorder.assert_called_once()

    def test_post_success_trace_failure_returns_original_without_replay(self):
        def decorator(**kwargs):
            def wrap(function):
                def invoke(**call_kwargs):
                    function(**call_kwargs)
                    raise RuntimeError("private trace store failure")
                return invoke
            return wrap
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", return_value=Response(body(content="")))
        with self.assertLogs(llm.__name__, level="WARNING") as logs:
            self.assertEqual(self.call_openrouter(), "")
        post.assert_called_once()
        self.recorder.assert_called_once()
        self.assertTrue(all(message.endswith(":llm_tracing_failed") for message in logs.output))

    def test_provider_error_is_same_instance_and_never_replayed(self):
        self.install_traceable(lambda **kwargs: lambda function: function)
        error = RuntimeError("private provider failure")
        raw = self.patch(llm, "_call_llm_raw", side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.call_openrouter()
        self.assertIs(caught.exception, error)
        raw.assert_called_once()
        self.recorder.assert_not_called()

    def test_trace_failure_after_provider_error_propagates_original_error(self):
        def decorator(**kwargs):
            def wrap(function):
                def invoke(**call_kwargs):
                    try:
                        return function(**call_kwargs)
                    finally:
                        raise RuntimeError("private trace after provider error")
                return invoke
            return wrap
        self.install_traceable(decorator)
        error = RuntimeError("private original provider failure")
        raw = self.patch(llm, "_call_llm_raw", side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.call_openrouter()
        self.assertIs(caught.exception, error)
        raw.assert_called_once()

    def test_failed_real_raw_attempts_are_not_doubled_by_trace_fallback(self):
        def decorator(**kwargs):
            def wrap(function):
                def invoke(**call_kwargs):
                    try:
                        return function(**call_kwargs)
                    finally:
                        raise RuntimeError("private trace finalizer failure")
                return invoke
            return wrap
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", side_effect=TimeoutError("private timeout"))
        with self.assertRaises(RuntimeError) as caught:
            self.call_openrouter(retries=3)
        self.assertIn("LLM call failed after 3 attempts", str(caught.exception))
        self.assertEqual(post.call_count, 3)
        self.assertEqual(self.recorder.call_count, 3)
        self.assertEqual(len({event["call_id"] for event in self.events}), 1)

    def test_provider_retries_then_success_and_trace_failure_do_not_replay(self):
        def decorator(**kwargs):
            def wrap(function):
                def invoke(**call_kwargs):
                    function(**call_kwargs)
                    raise RuntimeError("private trace finalizer failure")
                return invoke
            return wrap
        self.install_traceable(decorator)
        post = self.patch(llm.requests, "post", side_effect=[TimeoutError("private timeout"), Response(body())])
        with self.assertLogs(llm.__name__, level="WARNING"):
            self.assertEqual(self.call_openrouter(retries=2), "private answer")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self.recorder.call_count, 2)
        self.assertEqual(len({event["call_id"] for event in self.events}), 1)

    def test_trace_cannot_replace_or_suppress_original_provider_result(self):
        for suppress_error in (False, True):
            with self.subTest(suppress_error=suppress_error):
                def decorator(**kwargs):
                    def wrap(function):
                        def invoke(**call_kwargs):
                            try:
                                function(**call_kwargs)
                            except RuntimeError:
                                if not suppress_error:
                                    raise
                            return "trace replacement"
                        return invoke
                    return wrap
                self.install_traceable(decorator)
                original_error = RuntimeError("private provider failure")
                with mock.patch.object(llm, "_call_llm_raw", side_effect=original_error if suppress_error else None,
                                       return_value="original provider answer") as raw:
                    if suppress_error:
                        with self.assertRaises(RuntimeError) as caught:
                            self.call_openrouter()
                        self.assertIs(caught.exception, original_error)
                    else:
                        self.assertEqual(self.call_openrouter(), "original provider answer")
                    raw.assert_called_once()


if __name__ == "__main__":
    unittest.main()
