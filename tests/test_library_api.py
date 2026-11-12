"""Offline library API contracts: python -m unittest tests.test_library_api -v.

Compile only the three undecorated library handlers, never api.app or its
lifespan. HTTP exceptions and the library accessor are self-contained doubles.
"""
import ast
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Optional
import unittest
from unittest import mock

import core.library as library_module
from core.library import LibraryStore, LibraryUnavailable
from tests.test_library_store import corpus_fixture


REPO_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = REPO_ROOT / "api/app.py"
API_AST = ast.parse(API_SOURCE.read_text(encoding="utf-8"), filename=str(API_SOURCE))
HANDLERS = ("library_documents", "library_search", "library_section")


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def extracted_handler(name, accessor):
    node = copy.deepcopy(next(node for node in API_AST.body
                              if isinstance(node, ast.FunctionDef) and node.name == name))
    node.decorator_list = []
    namespace = {"HTTPException": HTTPException, "get_library": accessor, "Optional": Optional}
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, str(API_SOURCE), "exec"), namespace)
    return namespace[name]


class LibraryAPIContracts(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory(prefix="paradox-library-api-")))
        self.corpus_path = self.root / "corpus.json"
        self.db_path = self.root / "library.sqlite3"
        self.corpus = corpus_fixture()
        self.corpus_path.write_text(json.dumps(self.corpus, ensure_ascii=False), encoding="utf-8")
        self.store = LibraryStore(self.corpus_path, self.db_path)
        self.accessor = mock.Mock(return_value=self.store)
        self.handlers = {name: extracted_handler(name, self.accessor) for name in HANDLERS}
        self.api_before = sys.modules.get("api.app")
        self.addCleanup(lambda: self.assertIs(sys.modules.get("api.app"), self.api_before))
        for target in ("socket.create_connection", "socket.socket.connect", "urllib.request.urlopen"):
            guard = self.enterContext(mock.patch(target, side_effect=AssertionError("network forbidden")))
            self.addCleanup(guard.assert_not_called)

    def assert_http(self, status, detail, handler, *args, **kwargs):
        with self.assertRaises(HTTPException) as raised:
            handler(*args, **kwargs)
        self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(raised.exception.detail, detail)
        self.assertNotIn(str(self.root), str(raised.exception))

    def test_documents_default_and_pagination_metadata_contract(self):
        result = self.handlers["library_documents"]()
        self.assertEqual(result, self.store.list_documents())
        self.assertEqual(result["total"], 6)
        self.assertTrue(all("text" not in document for document in result["documents"]))
        self.assertEqual(result["documents"][0]["first_section_id"], "doc-000000000001-s00001")
        result = self.handlers["library_documents"](limit=2, offset=2)
        self.assertEqual(result["documents"], self.corpus["documents"][2:4])

    def test_search_default_and_filtered_response_passes_through(self):
        handler = self.handlers["library_search"]
        self.assertEqual(handler("shared"), self.store.search("shared"))
        self.assertEqual(handler("shared", document_id="doc-000000000002", limit=1, max_chars=10),
                         self.store.search("shared", document_id="doc-000000000002", limit=1, max_chars=10))
        self.assertEqual(handler("")["results"], [])
        self.assertEqual(handler("absentlexeme")["results"], [])

    def test_section_default_and_continuation_response_passes_through(self):
        handler = self.handlers["library_section"]
        section_id = "doc-000000000001-s00001"
        self.assertEqual(handler(section_id), self.store.read_section(section_id))
        result = handler(section_id, offset=100, max_chars=30)
        self.assertEqual(result, self.store.read_section(section_id, offset=100, max_chars=30))
        self.assertEqual(result["next_offset"], 130)
        self.assertEqual(result["locator"], self.corpus["sections"][0]["locator"])
        self.assertIsNone(result["previous_section_id"])
        self.assertEqual(result["next_section_id"], "doc-000000000001-s00002")

    def test_numeric_http_query_strings_are_normalized_in_handler(self):
        self.assertEqual(self.handlers["library_documents"](limit="2", offset="1"),
                         self.store.list_documents(limit=2, offset=1))
        self.assertEqual(self.handlers["library_search"]("alpha", limit="1", max_chars="100"),
                         self.store.search("alpha", limit=1, max_chars=100))
        self.assertEqual(self.handlers["library_section"]("doc-000000000001-s00001", offset="4", max_chars="20"),
                         self.store.read_section("doc-000000000001-s00001", offset=4, max_chars=20))

    def test_unknown_document_and_section_are_not_found(self):
        self.assert_http(404, "library_document_not_found", self.handlers["library_search"],
                         "shared", document_id="doc-ffffffffffff")
        self.assert_http(404, "library_document_not_found", self.handlers["library_search"],
                         "", document_id="doc-ffffffffffff")
        self.assert_http(404, "library_section_not_found", self.handlers["library_section"],
                         "doc-ffffffffffff-s00001")

    def test_invalid_inputs_are_bounded_bad_requests(self):
        invalid = [
            ("library_documents", (), {"limit": 101}),
            ("library_documents", (), {"offset": -1}),
            ("library_documents", (), {"limit": True}),
            ("library_documents", (), {"offset": "NaN"}),
            ("library_search", ("alpha",), {"limit": 6}),
            ("library_search", ("alpha",), {"max_chars": 1001}),
            ("library_search", ("alpha",), {"max_chars": "1.0"}),
            ("library_search", ("a" * 201,), {}),
            ("library_search", (None,), {}),
            ("library_search", ("alpha",), {"document_id": "../agents/tempest/private.json"}),
            ("library_section", ("/etc/passwd",), {}),
            ("library_section", ("doc-000000000001-s00001",), {"offset": 999999}),
            ("library_section", ("doc-000000000001-s00001",), {"max_chars": 2001}),
            ("library_section", ("doc-000000000001-s00001",), {"max_chars": "1" * 1000}),
        ]
        for name, args, kwargs in invalid:
            with self.subTest(name=name, kwargs=kwargs):
                self.assert_http(400, "invalid_library_request", self.handlers[name], *args, **kwargs)

    def test_missing_corpus_is_unavailable_for_all_handlers(self):
        self.corpus_path.unlink()
        for name, args in (("library_documents", ()), ("library_search", ("shared",)),
                           ("library_section", ("doc-000000000001-s00001",))):
            with self.subTest(name=name):
                self.assert_http(503, "library_unavailable", self.handlers[name], *args)
        self.assertFalse(self.db_path.exists())

    def test_invalid_corpus_is_unavailable_not_bad_user_request(self):
        self.corpus_path.write_text('{"schema_version":999}', encoding="utf-8")
        self.assert_http(503, "library_unavailable", self.handlers["library_documents"])
        self.assert_http(503, "library_unavailable", self.handlers["library_search"], "alpha")

    def test_index_errors_and_unexpected_failures_never_leak_paths_or_messages(self):
        for error in (LibraryUnavailable("/private/credentials"), OSError(str(self.root)),
                      RuntimeError("private-secret-marker")):
            self.accessor.side_effect = error
            for name, args in (("library_documents", ()), ("library_search", ("shared",)),
                               ("library_section", ("doc-000000000001-s00001",))):
                with self.subTest(name=name, error=type(error).__name__):
                    self.assert_http(503, "library_unavailable", self.handlers[name], *args)

    def test_handlers_delegate_to_only_the_library_accessor(self):
        fake_store = mock.Mock(spec=("list_documents", "search", "read_section"))
        self.accessor.return_value = fake_store
        sentinel = {"status": "ok", "fixture": "source only"}
        fake_store.list_documents.return_value = sentinel
        fake_store.search.return_value = sentinel
        fake_store.read_section.return_value = sentinel
        self.assertIs(self.handlers["library_documents"](), sentinel)
        self.assertIs(self.handlers["library_search"]("alpha"), sentinel)
        self.assertIs(self.handlers["library_section"]("doc-000000000001-s00001"), sentinel)
        fake_store.list_documents.assert_called_once_with(limit=50, offset=0)
        fake_store.search.assert_called_once_with("alpha", document_id=None, limit=3, max_chars=600)
        fake_store.read_section.assert_called_once_with("doc-000000000001-s00001", offset=0, max_chars=1200)
        for node in API_AST.body:
            if isinstance(node, ast.FunctionDef) and node.name in HANDLERS:
                names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
                self.assertFalse(names & {"FileResponse", "load_soul", "load_config_yaml", "get_agent_memory",
                                          "agent_wake", "start_scheduler", "call_llm"})

    def test_only_three_fixed_read_routes_and_no_library_startup_calls(self):
        routes = {}
        for node in API_AST.body:
            if isinstance(node, ast.FunctionDef) and node.name in HANDLERS:
                self.assertEqual(len(node.decorator_list), 1)
                decorator = node.decorator_list[0]
                self.assertEqual(decorator.func.attr, "get")
                routes[node.name] = ast.literal_eval(decorator.args[0])
        self.assertEqual(routes, {
            "library_documents": "/api/library/documents",
            "library_search": "/api/library/search",
            "library_section": "/api/library/sections/{section_id}",
        })
        for node in API_AST.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "lifespan":
                self.assertNotIn("get_library", {child.id for child in ast.walk(node) if isinstance(child, ast.Name)})
        self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == "core.library"
                            and any(alias.name == "get_library" for alias in node.names)
                            for node in API_AST.body))

    def test_default_accessor_is_lazy_and_cached_without_touching_real_data(self):
        fake_data_dir = mock.Mock()
        fake_data_dir.db_path.return_value = str(self.db_path)
        with mock.patch.object(library_module, "_store", None), \
                mock.patch.object(library_module, "LibraryStore", return_value=self.store) as constructor, \
                mock.patch.dict(sys.modules, {"core.data_dir": fake_data_dir}):
            self.assertIs(library_module.get_library(), self.store)
            self.assertIs(library_module.get_library(), self.store)
            constructor.assert_called_once_with(REPO_ROOT / "library/corpus.json", str(self.db_path))
            fake_data_dir.db_path.assert_called_once_with("library.sqlite3")
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
