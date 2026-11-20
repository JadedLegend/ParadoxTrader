"""Read-only source retrieval over a rebuildable, local SQLite FTS5 index.

Only the explicitly supplied corpus is read. Source filenames are metadata, never
paths to open. Source text is untrusted material, not executable instructions.
There are no model, broker, network, config, or private-agent dependencies here.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading


_DOCUMENT_ID = re.compile(r"doc-[0-9a-f]{12}\Z")
_SECTION_ID = re.compile(r"(doc-[0-9a-f]{12})-s[0-9]{5}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_INDEX_VERSION = "2"
_MAX_CORPUS_BYTES = 64 * 1024 * 1024
_MAX_DOCUMENTS = 10000
_MAX_SECTIONS = 100000
_TABLES = {"library_documents", "library_sections", "library_fts", "library_index_state"}


class LibraryUnavailable(RuntimeError):
    """The corpus/index is unavailable; the exception deliberately carries no path."""


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"invalid_{name}")
    return value


def _string(value, name, maximum, allow_empty=False):
    if (not isinstance(value, str) or len(value) > maximum or "\x00" in value
            or (not allow_empty and not value.strip())):
        raise ValueError(f"invalid_{name}")
    return value


def _identifier(value, pattern, name):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"invalid_{name}")
    return value


def _terms(text):
    """Case-folded Unicode lexical terms; callers never supply FTS operators."""
    return _WORD.findall(text.casefold())


def _validate_corpus(corpus):
    if not isinstance(corpus, dict) or type(corpus.get("schema_version")) is not int:
        raise ValueError("invalid_schema")
    if corpus["schema_version"] != 1:
        raise ValueError("invalid_schema")
    documents, sections = corpus.get("documents"), corpus.get("sections")
    if not isinstance(documents, list) or len(documents) > _MAX_DOCUMENTS:
        raise ValueError("invalid_documents")
    if not isinstance(sections, list) or len(sections) > _MAX_SECTIONS:
        raise ValueError("invalid_sections")
    clean_documents, clean_sections, ids, section_ids, counts = [], [], set(), set(), {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("invalid_document")
        document_id = _identifier(document.get("document_id"), _DOCUMENT_ID, "document_id")
        if document_id in ids:
            raise ValueError("duplicate_document")
        ids.add(document_id)
        counts[document_id] = 0
        sha256 = _identifier(document.get("sha256"), _SHA256, "sha256")
        source_format = document.get("format")
        if source_format not in ("md", "txt", "docx", "pdf"):
            raise ValueError("invalid_format")
        # Explicit metadata allowlist: extra corpus fields can never leak text or paths.
        metadata = {
            "document_id": document_id,
            "title": _string(document.get("title"), "title", 1024),
            "filename": _string(document.get("filename"), "filename", 1024),
            "format": source_format,
            "sha256": sha256,
            "extraction": _string(document.get("extraction"), "extraction", 2048),
            "section_count": _integer(document.get("section_count"), "section_count", 0, _MAX_SECTIONS),
            "char_count": _integer(document.get("char_count"), "char_count", 0, _MAX_CORPUS_BYTES),
        }
        if "text_sha256" in document:
            metadata["text_sha256"] = _identifier(document["text_sha256"], _SHA256, "text_sha256")
        if "status" in document:
            metadata["status"] = _string(document["status"], "status", 128)
        # Research-room labels: short plain text, so an excerpt can say what kind of
        # source it is (a reading note about a paper, its evidence and review depth).
        for field, limit in (("room", 32), ("kind", 128), ("authors", 512), ("year", 16), ("area", 128),
                             ("evidence", 256), ("review_depth", 256), ("url", 512)):
            if field in document:
                metadata[field] = _string(document[field], field, limit, allow_empty=True)
        if "first_section_id" in document:
            first_section_id = document["first_section_id"]
            if first_section_id is not None:
                _identifier(first_section_id, _SECTION_ID, "first_section_id")
                if not first_section_id.startswith(document_id + "-s"):
                    raise ValueError("invalid_first_section_id")
            metadata["first_section_id"] = first_section_id
        clean_documents.append(metadata)
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("invalid_section")
        section_id = _identifier(section.get("section_id"), _SECTION_ID, "section_id")
        document_id = _identifier(section.get("document_id"), _DOCUMENT_ID, "document_id")
        if (section_id in section_ids or document_id not in ids
                or not section_id.startswith(document_id + "-s") or section_id.endswith("-s00000")):
            raise ValueError("invalid_section_reference")
        section_ids.add(section_id)
        counts[document_id] += 1
        clean_sections.append({
            "section_id": section_id,
            "document_id": document_id,
            "locator": _string(section.get("locator"), "locator", 1024),
            "text": _string(section.get("text"), "text", 1400, allow_empty=True),
        })
    if any(document["section_count"] != counts[document["document_id"]] for document in clean_documents):
        raise ValueError("invalid_section_count")
    if any(document.get("first_section_id") is not None
           and document["first_section_id"] not in section_ids for document in clean_documents):
        raise ValueError("invalid_first_section_id")
    return clean_documents, clean_sections


class LibraryStore:
    """A lazy index for one explicit corpus and one dedicated index database.

    Every operation hashes the actual corpus bytes, rather than trusting mtime,
    size, or a cached store instance. Validation precedes all index mutations.
    Rebuild DDL, FTS data, and the new fingerprint commit in one transaction;
    failures leave the previous index intact, but never serve a stale corpus.
    """

    def __init__(self, corpus_path=None, db_path=None):
        if corpus_path is None:
            corpus_path = Path(__file__).resolve().parents[2] / "library" / "corpus.json"
        if db_path is None:
            from core.data_dir import db_path as data_db_path
            db_path = data_db_path("library.sqlite3")
        self.corpus_path = Path(corpus_path)
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._cached_hash = None
        self._cached_corpus = None

    def _load_corpus(self):
        try:
            with self.corpus_path.open("rb") as source:
                raw = source.read(_MAX_CORPUS_BYTES + 1)
            if len(raw) > _MAX_CORPUS_BYTES:
                raise ValueError("corpus_too_large")
            digest = hashlib.sha256(raw).hexdigest()
            if digest != self._cached_hash:
                clean = _validate_corpus(json.loads(raw.decode("utf-8")))
                self._cached_corpus = clean
                self._cached_hash = digest
            return digest, self._cached_corpus
        except (OSError, ValueError, TypeError, RecursionError):
            raise LibraryUnavailable("library_unavailable") from None

    @staticmethod
    def _index_matches(connection, digest):
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?, ?)",
            tuple(sorted(_TABLES)),
        )}
        if tables != _TABLES:
            return False
        row = connection.execute(
            "SELECT fingerprint, index_version FROM library_index_state WHERE id=1"
        ).fetchone()
        return bool(row and row[0] == digest and row[1] == _INDEX_VERSION)

    def _ensure_index(self, connection, digest, corpus):
        if self._index_matches(connection, digest):
            return
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Another independent store may have rebuilt while we waited for the lock.
            if not self._index_matches(connection, digest):
                documents, sections = corpus
                for table in ("library_fts", "library_sections", "library_documents", "library_index_state"):
                    connection.execute(f"DROP TABLE IF EXISTS {table}")
                connection.execute("""CREATE TABLE library_index_state (
                    id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL,
                    index_version TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE library_documents (
                    document_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    filename TEXT NOT NULL, sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL)""")
                connection.execute("""CREATE TABLE library_sections (
                    section_id TEXT PRIMARY KEY, document_id TEXT NOT NULL
                    REFERENCES library_documents(document_id), locator TEXT NOT NULL, text TEXT NOT NULL)""")
                connection.execute("CREATE INDEX library_sections_document_order "
                                   "ON library_sections(document_id, section_id)")
                connection.execute("""CREATE VIRTUAL TABLE library_fts USING fts5(
                    section_id UNINDEXED, document_id UNINDEXED, terms,
                    tokenize='unicode61 remove_diacritics 0')""")
                connection.executemany(
                    "INSERT INTO library_documents VALUES (?, ?, ?, ?, ?)",
                    ((doc["document_id"], doc["title"], doc["filename"], doc["sha256"],
                      json.dumps(doc, ensure_ascii=False, sort_keys=True)) for doc in documents),
                )
                connection.executemany(
                    "INSERT INTO library_sections VALUES (?, ?, ?, ?)",
                    ((section["section_id"], section["document_id"], section["locator"], section["text"])
                     for section in sections),
                )
                connection.executemany(
                    "INSERT INTO library_fts (section_id, document_id, terms) VALUES (?, ?, ?)",
                    ((section["section_id"], section["document_id"], " ".join(_terms(section["text"])))
                     for section in sections),
                )
                connection.execute("INSERT INTO library_index_state VALUES (1, ?, ?)", (digest, _INDEX_VERSION))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @contextmanager
    def _connection(self):
        with self._lock:
            digest, corpus = self._load_corpus()
            connection = None
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys=ON")
                self._ensure_index(connection, digest, corpus)
                # A consistent read snapshot for metadata, filters, and section windows.
                connection.execute("BEGIN")
                yield connection
            except (OSError, sqlite3.Error):
                raise LibraryUnavailable("library_unavailable") from None
            finally:
                if connection is not None:
                    if connection.in_transaction:
                        connection.rollback()
                    connection.close()

    @staticmethod
    def _citation(row):
        return {key: row[key] for key in (
            "section_id", "document_id", "title", "filename", "locator", "sha256"
        )}

    @staticmethod
    def _window(text, offset, max_chars):
        end = min(len(text), offset + max_chars)
        return text[offset:end], end if end < len(text) else None

    def list_documents(self, limit=50, offset=0):
        """Return metadata only; never include full section/document text."""
        _integer(limit, "limit", 1, 100)
        _integer(offset, "offset", 0, 2**31 - 1)
        with self._connection() as connection:
            total = connection.execute("SELECT COUNT(*) FROM library_documents").fetchone()[0]
            rows = connection.execute(
                "SELECT metadata_json FROM library_documents ORDER BY document_id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return {"status": "ok", "documents": [json.loads(row[0]) for row in rows],
                "total": total, "offset": offset, "limit": limit}

    def search(self, query, document_id=None, limit=3, max_chars=600):
        """Exact lexical OR search, capped at eight terms and 5,000 excerpt chars."""
        _string(query, "query", 200, allow_empty=True)
        _integer(limit, "limit", 1, 5)
        _integer(max_chars, "max_chars", 1, 1000)
        if document_id is not None:
            _identifier(document_id, _DOCUMENT_ID, "document_id")
        terms = list(dict.fromkeys(_terms(query)))[:8]
        with self._connection() as connection:
            if document_id is not None and connection.execute(
                "SELECT document_id FROM library_documents WHERE document_id=?", (document_id,)
            ).fetchone() is None:
                raise KeyError(document_id)
            if not terms:
                return {"status": "ok", "query": query, "results": []}
            # Every term comes from a lexical regex, is quoted, and is bound as data.
            match = " OR ".join('"' + term + '"' for term in terms)
            rows = connection.execute("""SELECT s.section_id, s.document_id, s.locator,
                s.text, d.title, d.filename, d.sha256
                FROM library_fts JOIN library_sections s ON s.section_id=library_fts.section_id
                JOIN library_documents d ON d.document_id=s.document_id
                WHERE library_fts MATCH ? AND (? IS NULL OR s.document_id=?)
                ORDER BY bm25(library_fts), s.section_id LIMIT ?""",
                (match, document_id, document_id, limit),
            ).fetchall()
        results = []
        wanted = set(terms)
        for row in rows:
            text = row["text"]
            # Match in original coordinates so Unicode case-fold expansion cannot
            # shift excerpt offsets. Include short leading context where possible.
            hit = next((word.start() for word in _WORD.finditer(text)
                        if any(term in wanted for term in _terms(word.group()))), 0)
            offset = min(max(0, hit - min(80, max_chars // 4)), max(0, len(text) - max_chars))
            excerpt, next_offset = self._window(text, offset, max_chars)
            results.append({**self._citation(row), "excerpt": excerpt, "offset": offset,
                            "next_offset": next_offset, "truncated": offset > 0 or next_offset is not None})
        return {"status": "ok", "query": query, "results": results}

    def read_section(self, section_id, offset=0, max_chars=1200):
        """Read one fixed section ID, retaining its original extraction locator."""
        _identifier(section_id, _SECTION_ID, "section_id")
        _integer(offset, "offset", 0, 2**31 - 1)
        _integer(max_chars, "max_chars", 1, 2000)
        with self._connection() as connection:
            row = connection.execute("""SELECT s.section_id, s.document_id, s.locator,
                s.text, d.title, d.filename, d.sha256 FROM library_sections s
                JOIN library_documents d ON d.document_id=s.document_id
                WHERE s.section_id=?""", (section_id,)).fetchone()
            if row is None:
                raise KeyError(section_id)
            previous_section = connection.execute("""SELECT section_id FROM library_sections
                WHERE document_id=? AND section_id<? ORDER BY section_id DESC LIMIT 1""",
                (row["document_id"], section_id)).fetchone()
            next_section = connection.execute("""SELECT section_id FROM library_sections
                WHERE document_id=? AND section_id>? ORDER BY section_id LIMIT 1""",
                (row["document_id"], section_id)).fetchone()
        total_chars = len(row["text"])
        if offset > total_chars:
            raise ValueError("invalid_offset")
        text, next_offset = self._window(row["text"], offset, max_chars)
        return {"status": "ok", **self._citation(row), "text": text, "offset": offset,
                "next_offset": next_offset, "truncated": offset > 0 or next_offset is not None,
                "total_chars": total_chars,
                "previous_section_id": previous_section[0] if previous_section is not None else None,
                "next_section_id": next_section[0] if next_section is not None else None}
