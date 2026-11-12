"""Offline lineage read API tests. No api.app import or application startup."""
import ast
import copy
import inspect
import os
from pathlib import Path
import sys
from typing import Optional
import unittest
from unittest import mock

API_SOURCE = Path(__file__).resolve().parents[1] / "api/app.py"
API_AST = ast.parse(API_SOURCE.read_text(encoding="utf-8"), filename=str(API_SOURCE))
NAMES = ("_require_lineage_operator", "_lineage_pilot", "_lineage_integer", "lineage_inquiries", "lineage_inquiry")
ID = "12345678-1234-4234-8234-123456789abc"
AUTH = "Bearer test-operator-credential"
AGENTS = ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter")


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


class LineageAccessError(Exception):
    pass


class LineageNotFound(Exception):
    pass


class IsolatedFastAPI:
    def __init__(self):
        self.routes = {}

    def get(self, path):
        def register(function):
            self.routes[path] = function
            return function
        return register


def extracted_handlers(accessor):
    app = IsolatedFastAPI()
    header = mock.Mock(return_value=None)
    namespace = {"app": app, "HTTPException": HTTPException, "Header": header,
                 "get_lineage_store": accessor, "Optional": Optional, "os": os,
                 "LineageAccessError": LineageAccessError, "LineageNotFound": LineageNotFound, "AGENTS": AGENTS}
    nodes = [copy.deepcopy(node) for node in API_AST.body
             if isinstance(node, ast.FunctionDef) and node.name in NAMES]
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(API_SOURCE), "exec"), namespace)
    return namespace, app, header


class LineageReadAPI(unittest.TestCase):
    def setUp(self):
        self.store = mock.Mock(spec=("list_inquiries", "get_inquiry"))
        self.list_result = {"status": "ok", "inquiries": [], "total": 0, "limit": 50, "offset": 0}
        self.detail_result = {"status": "ok", "inquiry": {"inquiry_id": ID, "agent_id": "alchemist", "phase": 0, "visibility": "owner"},
                              "entries": [], "proposals": [], "orders": [], "fills": [], "positions": [], "reviews": [], "events": [], "truncated": True}
        self.store.list_inquiries.return_value = self.list_result
        self.store.get_inquiry.return_value = self.detail_result
        self.accessor = mock.Mock(return_value=self.store)
        self.handlers, self.app, self.header = extracted_handlers(self.accessor)
        self.enterContext(mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": "test-operator-credential"}))
        before = sys.modules.get("api.app")
        self.addCleanup(lambda: self.assertIs(sys.modules.get("api.app"), before))
        for target in ("socket.create_connection", "socket.socket.connect", "urllib.request.urlopen"):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError("network forbidden")))
            self.addCleanup(guard.assert_not_called)

    def call(self, name, **kwargs):
        if name == "lineage_inquiry":
            kwargs.setdefault("inquiry_id", ID)
        kwargs.setdefault("authorization", AUTH)
        return self.handlers[name](**kwargs)

    def assert_http(self, name, status, category, **kwargs):
        with self.assertRaises(HTTPException) as raised:
            self.call(name, **kwargs)
        self.assertEqual((raised.exception.status_code, raised.exception.detail), (status, category))
        self.assertTrue(raised.exception.__suppress_context__)

    def test_defaults_authorize_then_delegate_only_reads(self):
        self.assertIs(self.call("lineage_inquiries"), self.list_result)
        self.assertIs(self.call("lineage_inquiry"), self.detail_result)
        self.store.list_inquiries.assert_called_once_with("alchemist", operator=True, limit=50, offset=0)
        self.store.get_inquiry.assert_called_once_with(ID, operator=True)
        self.assertEqual(self.header.call_args_list, [mock.call(None), mock.call(None)])

    def test_unconfigured_operator_is_503_even_for_bad_request(self):
        for value in ("", "   "):
            with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": value}):
                for name in ("lineage_inquiries", "lineage_inquiry"):
                    self.assert_http(name, 503, "lineage_operator_unavailable", agent_id="siren", authorization=None)
        with mock.patch.dict(os.environ, clear=True):
            self.assert_http("lineage_inquiries", 503, "lineage_operator_unavailable")
        self.accessor.assert_not_called()

    def test_wrong_missing_or_caller_role_credentials_are_403_before_store(self):
        for value in (None, "", "test-operator-credential", "Bearer wrong", "bearer test-operator-credential", "Bearer test-operator-credential ", "Bearer opérator", True):
            for name in ("lineage_inquiries", "lineage_inquiry"):
                self.assert_http(name, 403, "lineage_operator_required", authorization=value)
        self.accessor.assert_not_called()

    def test_utf8_credentials_use_constant_time_comparison(self):
        import hmac
        with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": "opérator-密钥"}), mock.patch("hmac.compare_digest", wraps=hmac.compare_digest) as compare:
            self.call("lineage_inquiries", authorization="Bearer opérator-密钥")
            compare.assert_called_once_with("Bearer opérator-密钥".encode("utf-8"), "Bearer opérator-密钥".encode("utf-8"))

    def test_fixed_owner_allowlist_and_validation_never_constructs_store(self):
        for value in ("outsider", "system", "alchemist ", "", "../alchemist", True, None, "alchemist&operator=true"):
            for name in ("lineage_inquiries", "lineage_inquiry"):
                self.assert_http(name, 404, "lineage_agent_not_found", agent_id=value)
        self.accessor.assert_not_called()

    def test_all_seven_operator_reads_match_the_selected_owner(self):
        for aid in AGENTS:
            self.call("lineage_inquiries", agent_id=aid)
            self.store.list_inquiries.assert_called_with(aid, operator=True, limit=50, offset=0)
            detail = {**self.detail_result, "inquiry": {**self.detail_result["inquiry"], "agent_id": aid}}
            self.store.get_inquiry.return_value = detail
            self.assertIs(self.call("lineage_inquiry", agent_id=aid), detail)
            other = next(owner for owner in AGENTS if owner != aid)
            self.assert_http("lineage_inquiry", 404, "lineage_inquiry_not_found", agent_id=other)

    def test_pagination_strict_and_bounded(self):
        for limit, offset in (("1", "0"), ("50", "2147483647"), (50, 0)):
            self.call("lineage_inquiries", limit=limit, offset=offset)
            self.store.list_inquiries.assert_called_with("alchemist", operator=True, limit=int(limit), offset=int(offset))
        self.accessor.reset_mock()
        bad = {"limit": (0, 51, -1, True, None, 1.0, "1.0", "+1", " 1", "١", "1" * 1000),
               "offset": (-1, 2**31, True, None, 0.0, "-1", "0.0", "+0", "", "0 ", "1" * 1000)}
        for field, values in bad.items():
            for value in values:
                self.assert_http("lineage_inquiries", 400, "invalid_lineage_request", **{field: value})
        self.accessor.assert_not_called()

    def test_malformed_uuid_is_bounded_400_before_store(self):
        for value in (None, 1, "", "not-a-uuid", ID + "\n", ID.replace("-", ""), "../private", "x" * 1000, ID + "?operator=true"):
            self.assert_http("lineage_inquiry", 400, "invalid_lineage_request", inquiry_id=value)
        self.accessor.assert_not_called()

    def test_owner_phase_zero_result_is_unchanged_and_no_peer_detail_passes(self):
        self.assertIs(self.call("lineage_inquiry"), self.detail_result)
        self.store.get_inquiry.return_value = {**self.detail_result, "inquiry": {"agent_id": "siren", "phase": 2, "visibility": "community"}}
        self.assert_http("lineage_inquiry", 404, "lineage_inquiry_not_found")
        self.store.get_inquiry.assert_called_with(ID, operator=True)

    def test_store_access_denied_and_not_found_are_safe_categories(self):
        for method, name in (("list_inquiries", "lineage_inquiries"), ("get_inquiry", "lineage_inquiry")):
            for error, status, category in ((LineageAccessError("private memory"), 403, "lineage_access_denied"),
                                            (LineageNotFound("secret ID"), 404, "lineage_inquiry_not_found"),
                                            (ValueError("private DB path"), 400, "invalid_lineage_request")):
                getattr(self.store, method).side_effect = error
                self.assert_http(name, status, category)

    def test_store_and_factory_failures_are_unavailable_not_empty(self):
        for error in (OSError("/secret/store.db"), RuntimeError("provider-token"), TypeError("private")):
            self.accessor.side_effect = error
            for name in ("lineage_inquiries", "lineage_inquiry"):
                self.assert_http(name, 503, "lineage_unavailable")
        self.accessor.side_effect = None
        self.store.get_inquiry.side_effect = RuntimeError("private read error")
        self.assert_http("lineage_inquiry", 503, "lineage_unavailable")
        self.store.list_inquiries.side_effect = RuntimeError("private read error")
        self.assert_http("lineage_inquiries", 503, "lineage_unavailable")

    def test_only_get_routes_header_dependency_and_no_impersonation_parameters(self):
        self.assertEqual(set(self.app.routes), {"/api/lineage/inquiries", "/api/lineage/inquiries/{inquiry_id}"})
        for name in ("lineage_inquiries", "lineage_inquiry"):
            params = set(inspect.signature(self.handlers[name]).parameters)
            self.assertFalse(params & {"operator", "viewer_agent_id", "phase"})
            for field in ("operator", "viewer_agent_id", "phase"):
                with self.assertRaises(TypeError):
                    self.call(name, **{field: "siren"})
        forbidden = {"start_scheduler", "agent_wake", "get_agent_memory", "get_trade_queue", "load_config_yaml", "get_market_snapshot", "_auto_init"}
        for node in API_AST.body:
            if isinstance(node, ast.FunctionDef) and node.name in NAMES:
                self.assertFalse({child.id for child in ast.walk(node) if isinstance(child, ast.Name)} & forbidden)
                if node.name.startswith("lineage_"):
                    self.assertEqual(len(node.decorator_list), 1)
                    self.assertEqual(node.decorator_list[0].func.attr, "get")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("lifespan", "_auto_init"):
                self.assertNotIn("get_lineage_store", {child.id for child in ast.walk(node) if isinstance(child, ast.Name)})
        getter = next(node for node in API_AST.body if isinstance(node, ast.FunctionDef) and node.name == "get_lineage_store")
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == "core.trading.lineage" for node in ast.walk(getter)))
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "get_lineage_store"
                             for node in API_AST.body))


if __name__ == "__main__":
    unittest.main()
