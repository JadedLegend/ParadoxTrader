"""Offline read-only usage API tests, with no application/lifespan import.

Run: python -m unittest tests.test_usage_api -v. Only the two handlers are
AST-extracted; a route-registration double and fake ledger own all execution.
"""
import ast
import copy
from pathlib import Path
import sys
from typing import Optional
import unittest
from unittest import mock


API_SOURCE = Path(__file__).resolve().parents[1] / "api/app.py"
API_AST = ast.parse(API_SOURCE.read_text(encoding="utf-8"), filename=str(API_SOURCE))
HANDLERS = ("usage_summary", "usage_events")


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class IsolatedFastAPI:
    """Only registers read decorators; has no lifespan or provider machinery."""
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def register(function):
            self.routes[path] = function
            return function
        return register


def extracted_handlers(accessor):
    app = IsolatedFastAPI()
    nodes = [copy.deepcopy(node) for node in API_AST.body
             if isinstance(node, ast.FunctionDef) and node.name in HANDLERS]
    namespace = {"app": app, "HTTPException": HTTPException,
                 "get_usage_store": accessor, "Optional": Optional}
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(API_SOURCE), "exec"), namespace)
    return {name: namespace[name] for name in HANDLERS}, app


class UsageAPIContracts(unittest.TestCase):
    def setUp(self):
        self.store = mock.Mock(spec=("summary", "list_events"))
        self.summary = {"status": "ok", "currency": "USD", "filters": {"agent_id": None, "since": None, "until": None},
                        "summary": {"requests": 0, "reported_cost_usd": None},
                        "by_agent": [], "by_provider": [], "by_activity": []}
        self.events = {"status": "ok", "events": [], "total": 0, "offset": 0, "limit": 50,
                       "filters": {"agent_id": None, "since": None, "until": None}}
        self.store.summary.return_value = self.summary
        self.store.list_events.return_value = self.events
        self.accessor = mock.Mock(return_value=self.store)
        self.handlers, self.app = extracted_handlers(self.accessor)
        app_before = sys.modules.get("api.app")
        self.addCleanup(lambda: self.assertIs(sys.modules.get("api.app"), app_before))
        for target in ("socket.create_connection", "socket.socket.connect", "urllib.request.urlopen"):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError("network forbidden")))
            self.addCleanup(guard.assert_not_called)

    def assert_http(self, handler, status, detail, **kwargs):
        with self.assertRaises(HTTPException) as raised:
            handler(**kwargs)
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (status, detail))
        self.assertEqual(str(raised.exception), detail)
        self.assertTrue(raised.exception.__suppress_context__)

    def test_defaults_delegate_to_only_read_methods(self):
        self.assertIs(self.handlers["usage_summary"](), self.summary)
        self.assertIs(self.handlers["usage_events"](), self.events)
        self.store.summary.assert_called_once_with(agent_id=None, since=None, until=None)
        self.store.list_events.assert_called_once_with(agent_id=None, limit=50, offset=0, since=None, until=None)

    def test_agent_and_timezone_filters_are_forwarded_without_private_data(self):
        filters = {"agent_id": "tempest", "since": "2026-01-01T00:00:00Z", "until": "2026-01-02T12:00:00+01:00"}
        self.handlers["usage_summary"](**filters)
        self.handlers["usage_events"](**filters, limit="2", offset="1")
        self.store.summary.assert_called_once_with(**filters)
        self.store.list_events.assert_called_once_with(**filters, limit=2, offset=1)

    def test_strict_numeric_query_strings_and_boundary_values(self):
        for limit, offset in (("1", "0"), ("100", "2147483647"), (50, 0), (100, 2**31 - 1)):
            with self.subTest(limit=limit, offset=offset):
                self.handlers["usage_events"](limit=limit, offset=offset)
                self.store.list_events.assert_called_with(agent_id=None, limit=int(limit), offset=int(offset), since=None, until=None)

    def test_numeric_bad_inputs_are_400_without_calling_store(self):
        values = {
            "limit": [0, 101, -1, True, False, None, 1.0, "", "true", "1.0", "+1", " 1", "1 ", "١", "NaN", "1e2", "1" * 1000],
            "offset": [-1, 2**31, True, False, None, 0.0, "-1", "2147483648", "", "NaN", "0.0", "+0", " 0", "1" * 1000],
        }
        for field, invalids in values.items():
            for value in invalids:
                with self.subTest(field=field, value=value):
                    self.assert_http(self.handlers["usage_events"], 400, "invalid_usage_request", **{field: value})
        self.accessor.assert_not_called()

    def test_bad_agent_filters_are_bounded_400(self):
        for name in HANDLERS:
            for value in (True, 1, "", "a" * 81, "../tempest", "/private/key", "tempest\n", "two agents", "tempest&offset=0"):
                with self.subTest(handler=name, agent_id=value):
                    self.assert_http(self.handlers[name], 400, "invalid_usage_request", agent_id=value)
        self.accessor.assert_not_called()

    def test_bad_timestamp_filters_and_reverse_ranges_are_400(self):
        bad_dates = (True, 1, "", "2026-01-01", "2026-01-01T00:00:00", "2026-02-30T00:00:00Z",
                     "2026-13-01T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:00:00+25:00",
                     "2026-01-01T00:00:00+00:99",
                     "2026-01-01T00:00:00Z\n", "x" * 1000)
        for name in HANDLERS:
            for field in ("since", "until"):
                for value in bad_dates:
                    with self.subTest(handler=name, field=field, value=value):
                        self.assert_http(self.handlers[name], 400, "invalid_usage_request", **{field: value})
            self.assert_http(self.handlers[name], 400, "invalid_usage_request",
                             since="2026-01-02T00:00:00Z", until="2026-01-01T00:00:00Z")
        self.accessor.assert_not_called()

    def test_equal_timestamps_are_valid_and_unknown_agents_can_be_empty(self):
        filters = {"agent_id": "no_recorded_events", "since": "2026-01-01T00:00:00.123456Z", "until": "2026-01-01T00:00:00.123456+00:00"}
        self.assertIs(self.handlers["usage_summary"](**filters), self.summary)
        self.assertIs(self.handlers["usage_events"](**filters), self.events)

    def test_store_validation_errors_do_not_leak_raw_messages(self):
        for method, name in (("summary", "usage_summary"), ("list_events", "usage_events")):
            getattr(self.store, method).side_effect = ValueError("private path /secret/prices.json")
            self.assert_http(self.handlers[name], 400, "invalid_usage_request")

    def test_unavailable_and_unexpected_exceptions_are_bounded_503(self):
        for error in (OSError("/private/usage.sqlite3"), RuntimeError("provider-secret-marker"), TypeError("secret")):
            self.accessor.side_effect = error
            for name in HANDLERS:
                with self.subTest(handler=name, error=type(error).__name__):
                    self.assert_http(self.handlers[name], 503, "usage_unavailable")
        self.accessor.side_effect = None
        for method, name in (("summary", "usage_summary"), ("list_events", "usage_events")):
            getattr(self.store, method).side_effect = RuntimeError("raw private database error")
            self.assert_http(self.handlers[name], 503, "usage_unavailable")

    def test_metadata_results_and_truncation_flag_pass_through_unchanged(self):
        result = {**self.summary, "groups_truncated": True}
        self.store.summary.return_value = result
        self.assertIs(self.handlers["usage_summary"](), result)
        self.assertEqual(self.handlers["usage_events"]()["events"], [])

    def test_only_two_fixed_get_routes_and_lazy_import(self):
        self.assertEqual(set(self.app.routes), {"/api/usage/summary", "/api/usage/events"})
        for node in API_AST.body:
            if isinstance(node, ast.FunctionDef) and node.name in HANDLERS:
                self.assertEqual(len(node.decorator_list), 1)
                self.assertEqual(node.decorator_list[0].func.attr, "get")
                names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
                self.assertFalse(names & {"start_scheduler", "agent_wake", "load_config_yaml", "get_agent_memory", "call_llm", "_auto_init"})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("lifespan", "_auto_init"):
                self.assertNotIn("get_usage_store", {child.id for child in ast.walk(node) if isinstance(child, ast.Name)})
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == "core.usage"
                            and any(alias.name == "get_usage_store" for alias in node.names) for node in API_AST.body))


if __name__ == "__main__":
    unittest.main()
