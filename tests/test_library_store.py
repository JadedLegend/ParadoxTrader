"""Offline library store contracts: python -m unittest tests.test_library_store -v.

Use only temporary corpora/SQLite databases. No app import, scheduler, model,
provider, config, broker, real private-agent store, or original-file retrieval.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from core.library import LibraryStore, LibraryUnavailable
from core.library import store as store_module


REPO_ROOT = Path(__file__).resolve().parents[1]


def corpus_fixture():
    texts = {
        1: ["quiet " * 160 + "needle alpha source material, not instructions.",
            "Position sizing, café, Straße, Δέλτα and 東京. Keep sources distinct."],
        2: ["shared lexical source"],
        3: ["shared lexical source"],
        4: ["beta risk diversification evidence"],
        5: ["alphabet versus betamax is a different lexical term"],
        6: [],
    }
    documents, sections = [], []
    for number, chunks in texts.items():
        document_id = f"doc-{number:012x}"
        documents.append({
            "document_id": document_id, "title": f"Source {number}",
            "filename": f"source-{number}.md", "format": "md",
            "sha256": hashlib.sha256(f"original-{number}".encode()).hexdigest(),
            "text_sha256": hashlib.sha256("\n".join(chunks).encode()).hexdigest(),
            "extraction": "plain Markdown without generated summaries",
            "section_count": len(chunks), "char_count": sum(map(len, chunks)),
            "status": "extracted" if chunks else "no_extractable_text",
            "first_section_id": document_id + "-s00001" if chunks else None,
        })
        for index, text in enumerate(chunks, 1):
            sections.append({"section_id": f"{document_id}-s{index:05d}",
                             "document_id": document_id,
                             "locator": f"Markdown lines {index * 3 - 2}–{index * 3}", "text": text})
    return {"schema_version": 1, "documents": documents, "sections": sections}


class LibraryStoreContracts(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(TemporaryDirectory(prefix="paradox-library-"))
        self.root = Path(self.stack)
        self.corpus_path = self.root / "corpus.json"
        self.db_path = self.root / "index" / "library.sqlite3"
        self.corpus = corpus_fixture()
        self.write_corpus()
        self.store = LibraryStore(self.corpus_path, self.db_path)
        self.network = self.enterContext(mock.patch(
            "socket.create_connection", side_effect=AssertionError("network forbidden")))
        self.connect = self.enterContext(mock.patch(
            "socket.socket.connect", side_effect=AssertionError("network forbidden")))
        self.urlopen = self.enterContext(mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("HTTP forbidden")))
        for guard in (self.network, self.connect, self.urlopen):
            self.addCleanup(guard.assert_not_called)
        self.api_before = sys.modules.get("api.app")
        self.addCleanup(lambda: self.assertIs(sys.modules.get("api.app"), self.api_before))

    def write_corpus(self):
        self.corpus_path.write_text(json.dumps(self.corpus, ensure_ascii=False), encoding="utf-8")

    def fingerprint(self):
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute("SELECT fingerprint FROM library_index_state WHERE id=1").fetchone()[0]

    def test_constructor_is_lazy(self):
        self.assertFalse(self.db_path.exists())
        self.assertFalse(self.db_path.parent.exists())

    def test_documents_are_bounded_metadata_with_additive_citations(self):
        self.corpus["documents"][0].update(text="must never list text", path="/private/forbidden")
        self.write_corpus()
        result = self.store.list_documents(limit=2, offset=1)
        self.assertEqual({key: result[key] for key in ("status", "total", "offset", "limit")},
                         {"status": "ok", "total": 6, "offset": 1, "limit": 2})
        self.assertEqual(result["documents"], self.corpus["documents"][1:3])
        all_documents = self.store.list_documents()["documents"]
        self.assertNotIn("text", all_documents[0])
        self.assertNotIn("path", all_documents[0])
        self.assertEqual(all_documents[-1]["status"], "no_extractable_text")
        self.assertIsNone(all_documents[-1]["first_section_id"])
        self.assertEqual(self.store.list_documents(offset=99)["documents"], [])

    def test_returns_do_not_mutate_cached_metadata(self):
        listed = self.store.list_documents()["documents"]
        listed[0]["title"] = "changed"
        self.assertEqual(self.store.list_documents()["documents"][0]["title"], "Source 1")

    def test_exact_or_search_and_stable_ties(self):
        self.assertEqual([row["document_id"] for row in self.store.search("alpha")["results"]],
                         ["doc-000000000001"])
        result = self.store.search("alpha beta")
        self.assertEqual({row["document_id"] for row in result["results"]},
                         {"doc-000000000001", "doc-000000000004"})
        tied = self.store.search("shared")["results"]
        self.assertEqual([row["section_id"] for row in tied],
                         ["doc-000000000002-s00001", "doc-000000000003-s00001"])
        self.assertEqual(self.store.search("shared")["results"], tied)

    def test_quotes_punctuation_and_operators_are_lexical_not_fts_syntax(self):
        expected = self.store.search("alpha")["results"]
        for query in ('"alpha"', 'alpha:*', '(alpha)', 'alpha; --', 'alpha OR missing'):
            with self.subTest(query=query):
                self.assertEqual(self.store.search(query)["results"], expected)
        self.assertEqual(self.store.search('" OR * NOT NEAR()')["results"],
                         self.store.search("not")["results"])
        self.assertEqual(self.store.search("'; DROP TABLE library_sections; --")["results"], [])
        self.assertEqual(self.store.list_documents()["total"], 6)

    def test_unicode_casefold_and_words(self):
        for query in ("CAFÉ", "STRASSE", "straße", "ΔΈΛΤΑ", "東京"):
            with self.subTest(query=query):
                result = self.store.search(query)["results"]
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["section_id"], "doc-000000000001-s00002")
        self.assertEqual(self.store.search("cafe")["results"], [])

    def test_query_terms_are_deduplicated_and_capped_at_eight(self):
        self.assertEqual(self.store.search("one two three four five six seven eight needle")["results"], [])
        self.assertEqual(len(self.store.search("needle " * 20)["results"]), 1)

    def test_blank_no_terms_empty_corpus_and_no_matches(self):
        for query in ("", "   ", "!?", "absentword"):
            self.assertEqual(self.store.search(query), {"status": "ok", "query": query, "results": []})
        self.corpus = {"schema_version": 1, "documents": [], "sections": []}
        self.write_corpus()
        self.assertEqual(self.store.list_documents()["total"], 0)
        self.assertEqual(self.store.search("alpha")["results"], [])

    def test_document_filter_and_unknown_ids(self):
        self.assertEqual(len(self.store.search("shared", document_id="doc-000000000002")["results"]), 1)
        self.assertEqual(self.store.search("shared", document_id="doc-000000000001")["results"], [])
        for query in ("shared", ""):
            with self.assertRaises(KeyError):
                self.store.search(query, document_id="doc-ffffffffffff")
        with self.assertRaises(KeyError):
            self.store.read_section("doc-ffffffffffff-s00001")

    def test_excerpt_window_is_near_hit_with_original_offsets_and_locator(self):
        section = self.corpus["sections"][0]
        result = self.store.search("needle", max_chars=100)["results"][0]
        self.assertIn("needle", result["excerpt"])
        self.assertGreater(result["offset"], 0)
        self.assertLessEqual(len(result["excerpt"]), 100)
        self.assertEqual(result["excerpt"], section["text"][result["offset"]:result["offset"] + 100])
        self.assertEqual(result["locator"], section["locator"])
        self.assertEqual(result["sha256"], self.corpus["documents"][0]["sha256"])
        self.assertTrue(result["truncated"])
        self.assertNotIn("text", result)

    def test_read_continuations_and_end_boundary(self):
        section = self.corpus["sections"][0]
        offset, chunks = 0, []
        while True:
            result = self.store.read_section(section["section_id"], offset=offset, max_chars=100)
            self.assertEqual(result["offset"], offset)
            self.assertEqual(result["locator"], section["locator"])
            self.assertEqual(result["total_chars"], len(section["text"]))
            chunks.append(result["text"])
            if result["next_offset"] is None:
                break
            self.assertEqual(result["next_offset"], offset + len(result["text"]))
            offset = result["next_offset"]
        self.assertEqual("".join(chunks), section["text"])
        end = self.store.read_section(section["section_id"], offset=len(section["text"]))
        self.assertEqual(end["text"], "")
        self.assertIsNone(end["next_offset"])
        with self.assertRaises(ValueError):
            self.store.read_section(section["section_id"], offset=len(section["text"]) + 1)

    def test_neighbors_are_ordered_existing_sections_and_never_cross_documents(self):
        first = self.store.read_section("doc-000000000001-s00001")
        self.assertIsNone(first["previous_section_id"])
        self.assertEqual(first["next_section_id"], "doc-000000000001-s00002")
        last = self.store.read_section("doc-000000000001-s00002")
        self.assertEqual(last["previous_section_id"], "doc-000000000001-s00001")
        self.assertIsNone(last["next_section_id"])
        single = self.store.read_section("doc-000000000002-s00001")
        self.assertIsNone(single["previous_section_id"])
        self.assertIsNone(single["next_section_id"])

    def test_neighbors_rebuild_from_actual_ids_not_guessed_sequential_suffixes(self):
        self.store.read_section("doc-000000000001-s00001")
        self.corpus["sections"][1]["section_id"] = "doc-000000000001-s00009"
        self.corpus["sections"].reverse()
        self.write_corpus()
        first = self.store.read_section("doc-000000000001-s00001")
        self.assertEqual(first["next_section_id"], "doc-000000000001-s00009")
        last = self.store.read_section(first["next_section_id"])
        self.assertEqual(last["previous_section_id"], first["section_id"])
        self.assertIsNone(last["next_section_id"])
        with self.assertRaises(KeyError):
            self.store.read_section("doc-000000000001-s00002")

    def test_windows_use_unicode_codepoint_offsets(self):
        self.corpus["sections"][0]["text"] = "a😀b café"
        self.corpus["documents"][0]["char_count"] = sum(len(s["text"]) for s in self.corpus["sections"][:2])
        self.write_corpus()
        result = self.store.read_section("doc-000000000001-s00001", offset=1, max_chars=2)
        self.assertEqual(result["text"], "😀b")
        self.assertEqual(result["next_offset"], 3)

    def test_casefold_expansion_keeps_matching_window_in_original_coordinates(self):
        self.corpus["sections"][0]["text"] = "quiet " * 160 + "İ Straße trailing source"
        self.write_corpus()
        for query, original_word in (("i", "İ"), ("STRASSE", "Straße")):
            with self.subTest(query=query):
                result = next(result for result in self.store.search(query, max_chars=60)["results"]
                              if result["section_id"] == "doc-000000000001-s00001")
                self.assertGreater(result["offset"], 0)
                self.assertIn(original_word, result["excerpt"])
                self.assertEqual(result["excerpt"], self.corpus["sections"][0]["text"][
                    result["offset"]:result["offset"] + 60])

    def test_aggregate_search_and_read_caps(self):
        for section in self.corpus["sections"]:
            section["text"] = "bounded " * 175
        self.write_corpus()
        result = self.store.search("bounded", limit=5, max_chars=1000)["results"]
        self.assertEqual(len(result), 5)
        self.assertLessEqual(sum(len(row["excerpt"]) for row in result), 5000)
        result = self.store.read_section(result[0]["section_id"], max_chars=2000)
        self.assertEqual(len(result["text"]), 1400)
        self.assertFalse(result["truncated"])

    def test_bad_types_ranges_and_strings_fail_before_opening_database(self):
        invalid = [
            lambda: self.store.list_documents(limit=0),
            lambda: self.store.list_documents(limit=101),
            lambda: self.store.list_documents(limit=True),
            lambda: self.store.list_documents(offset=-1),
            lambda: self.store.list_documents(offset="0"),
            lambda: self.store.list_documents(offset=2**80),
            lambda: self.store.search(None),
            lambda: self.store.search(123),
            lambda: self.store.search("a" * 201),
            lambda: self.store.search("a\x00b"),
            lambda: self.store.search("alpha", limit=6),
            lambda: self.store.search("alpha", limit=1.0),
            lambda: self.store.search("alpha", max_chars=1001),
            lambda: self.store.search("alpha", max_chars=0),
            lambda: self.store.search("alpha", document_id="../config/system.yaml"),
            lambda: self.store.read_section("/etc/passwd"),
            lambda: self.store.read_section("doc-000000000001-s00001", offset=True),
            lambda: self.store.read_section("doc-000000000001-s00001", offset=-1),
            lambda: self.store.read_section("doc-000000000001-s00001", max_chars=2001),
            lambda: self.store.read_section("doc-000000000001-s00001", max_chars="10"),
        ]
        for operation in invalid:
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                operation()
        self.assertFalse(self.db_path.exists())

    def test_no_arbitrary_file_source_api_or_profile_access(self):
        self.assertFalse(hasattr(self.store, "get_source"))
        self.assertFalse(hasattr(self.store, "read_file"))
        private = self.root / "agents" / "tempest" / "private.json"
        private.parent.mkdir(parents=True)
        private.write_text('"private marker"', encoding="utf-8")
        corpus_before, profile_before = self.corpus_path.read_bytes(), private.read_bytes()
        original_open = Path.open
        opened = []

        def guarded_open(path, *args, **kwargs):
            opened.append(path)
            if path != self.corpus_path:
                raise AssertionError("non-corpus file access forbidden")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", guarded_open):
            self.store.list_documents()
            self.store.search("alpha")
            self.store.read_section("doc-000000000001-s00001")
        self.assertEqual(opened, [self.corpus_path] * 3)
        self.assertEqual(self.corpus_path.read_bytes(), corpus_before)
        self.assertEqual(private.read_bytes(), profile_before)
        imports = (REPO_ROOT / "core/library/store.py").read_text(encoding="utf-8")
        for forbidden in ("core.memory", "core.runtime", "core.trading", "load_config", "call_llm"):
            self.assertNotIn(forbidden, imports)

    def test_reuses_index_without_rebuilding_but_checks_real_bytes(self):
        self.store.list_documents()
        fingerprint = self.fingerprint()
        with mock.patch.object(store_module, "_validate_corpus", side_effect=AssertionError("cached validation")):
            self.assertEqual(self.store.list_documents()["total"], 6)
            self.assertEqual(len(self.store.search("needle")["results"]), 1)
        self.assertEqual(self.fingerprint(), fingerprint)
        before = self.corpus_path.stat()
        raw = self.corpus_path.read_bytes().replace(b"needle", b"anchor")
        self.corpus_path.write_bytes(raw)
        os.utime(self.corpus_path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(self.corpus_path.stat().st_size, before.st_size)
        self.assertEqual(self.store.search("needle")["results"], [])
        self.assertEqual(len(self.store.search("anchor")["results"]), 1)
        self.assertNotEqual(self.fingerprint(), fingerprint)

    def test_independent_store_uses_existing_index_and_rebuilds_on_changes(self):
        self.store.list_documents()
        other = LibraryStore(self.corpus_path, self.db_path)
        with mock.patch.object(store_module, "_terms", side_effect=AssertionError("no rebuild")):
            self.assertEqual(other.list_documents()["total"], 6)
        self.corpus["sections"][0]["text"] = "replacement"
        self.write_corpus()
        self.assertEqual(len(other.search("replacement")["results"]), 1)
        self.assertEqual(self.store.search("needle")["results"], [])
        self.assertEqual(len(self.store.search("replacement")["results"]), 1)
        self.db_path.unlink()
        self.assertEqual(len(self.store.search("replacement")["results"]), 1)

    def test_missing_or_malformed_corpus_never_serves_or_wipes_old_index(self):
        self.store.list_documents()
        original_hash = self.fingerprint()
        original_bytes = self.corpus_path.read_bytes()
        for raw in (b"{broken", b"{}", b"\xff", b"null"):
            self.corpus_path.write_bytes(raw)
            with self.assertRaisesRegex(LibraryUnavailable, "^library_unavailable$"):
                self.store.search("needle")
            self.assertEqual(self.fingerprint(), original_hash)
        self.corpus_path.unlink()
        with self.assertRaises(LibraryUnavailable):
            self.store.list_documents()
        self.assertEqual(self.fingerprint(), original_hash)
        self.corpus_path.write_bytes(original_bytes)
        self.assertEqual(len(self.store.search("needle")["results"]), 1)

    def test_validation_duplicates_refs_counts_and_text_budget_preserve_index(self):
        self.store.list_documents()
        fingerprint = self.fingerprint()
        mutations = [
            lambda c: c["documents"].append(copy.deepcopy(c["documents"][0])),
            lambda c: c["sections"].append(copy.deepcopy(c["sections"][0])),
            lambda c: c["sections"][0].update(document_id="doc-ffffffffffff"),
            lambda c: c["sections"][0].update(section_id="doc-000000000002-s00099"),
            lambda c: c["sections"][0].update(section_id="../../config/system.yaml"),
            lambda c: c["sections"][0].update(text="a" * 1401),
            lambda c: c["sections"][0].update(text=123),
            lambda c: c["documents"][0].update(sha256="bad"),
            lambda c: c["documents"][0].update(section_count=99),
            lambda c: c["documents"][0].update(char_count=True),
            lambda c: c["documents"][0].update(first_section_id="doc-000000000001-s00999"),
            lambda c: c.update(schema_version=True),
            lambda c: c.update(schema_version=2),
        ]
        baseline = copy.deepcopy(self.corpus)
        for mutate in mutations:
            self.corpus = copy.deepcopy(baseline)
            mutate(self.corpus)
            self.write_corpus()
            with self.subTest(mutation=mutate), self.assertRaises(LibraryUnavailable):
                self.store.list_documents()
            self.assertEqual(self.fingerprint(), fingerprint)

    def test_oversize_corpus_does_not_create_database(self):
        with mock.patch.object(store_module, "_MAX_CORPUS_BYTES", 10):
            with self.assertRaises(LibraryUnavailable):
                self.store.list_documents()
        self.assertFalse(self.db_path.exists())

    def test_rebuild_transaction_rolls_back_after_ddl_and_partial_insert(self):
        self.store.list_documents()
        fingerprint = self.fingerprint()
        self.corpus["sections"][0]["text"] = "new source"
        self.write_corpus()
        with mock.patch.object(store_module, "_terms", side_effect=sqlite3.OperationalError("private failure path")):
            with self.assertRaisesRegex(LibraryUnavailable, "^library_unavailable$"):
                self.store.list_documents()
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT fingerprint FROM library_index_state").fetchone()[0], fingerprint)
            old = connection.execute("SELECT text FROM library_sections WHERE section_id=?",
                                     ("doc-000000000001-s00001",)).fetchone()[0]
            self.assertIn("needle", old)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM library_fts").fetchone()[0], 6)
        self.assertEqual(len(self.store.search("new")["results"]), 1)
        self.assertNotEqual(self.fingerprint(), fingerprint)

    def test_corrupt_database_fails_bounded_without_deleting_the_file(self):
        self.store.list_documents()
        corrupt = b"not a SQLite database"
        self.db_path.write_bytes(corrupt)
        with self.assertRaisesRegex(LibraryUnavailable, "^library_unavailable$"):
            self.store.list_documents()
        self.assertEqual(self.db_path.read_bytes(), corrupt)
        # This is only a derived index; removing it explicitly permits a rebuild.
        self.db_path.unlink()
        self.assertEqual(self.store.list_documents()["total"], 6)

    def test_independent_connections_can_race_first_build(self):
        def retrieve(_):
            store = LibraryStore(self.corpus_path, self.db_path)
            return store.search("shared")["results"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(retrieve, range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(results[0]), 2)
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
