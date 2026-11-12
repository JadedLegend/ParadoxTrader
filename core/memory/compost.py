"""Optional owner journal classifications, compost and chosen distillation.

Journal rows are the originals, not a second ledger. Only explicit writes install
metadata in that same database. Read paths never initialize or migrate a store.
``real`` labels transport mode, not a verified personality or authorship claim.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import stat

from core.trading.queue import ensure_private_db_file

OWNERS = frozenset(("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"))
CHANNELS = ("trading", "idea", "orientation")
MAX_CONTENT_CHARS = 6000
MAX_CONTENT_BYTES = 12000
MAX_SOURCE_CHARS = 4000
MAX_SOURCES = 20


class CompostError(ValueError):
    """Invalid input or unavailable owner journal."""


class CompostConflict(CompostError):
    """An operation key already identifies a different immutable effect."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _integer(value, name, *, minimum=1, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CompostError("invalid " + name)
    return value


def _channels(value):
    if value is None:
        return ["unclassified"]
    if not isinstance(value, (list, tuple)) or len(value) > len(CHANNELS):
        raise CompostError("invalid channels")
    if not value:
        return ["unclassified"]
    if any(not isinstance(item, str) or item not in CHANNELS for item in value):
        raise CompostError("invalid channels")
    if len(set(value)) != len(value):
        raise CompostError("duplicate channels")
    return list(value)


def _bounded(content, chars=MAX_CONTENT_CHARS, byte_limit=MAX_CONTENT_BYTES):
    """Literal prefix only: no inserted glyphs, paraphrases or inferred facts."""
    text = content[:chars]
    text = text.encode("utf-8")[:byte_limit].decode("utf-8", errors="ignore")
    return text, text != content


class CompostStore:
    def __init__(self, db_path, owner):
        if not isinstance(owner, str) or owner not in OWNERS:
            raise CompostError("invalid owner")
        try:
            raw = Path(db_path)
        except (TypeError, ValueError):
            raise CompostError("invalid owner journal path") from None
        if ".." in raw.parts or raw.name != owner + ".sqlite3":
            raise CompostError("owner journal filename mismatch")
        self._owner = owner
        self._db_path = Path(os.path.abspath(raw))
        self._check_path()

    @property
    def owner(self):
        return self._owner

    @property
    def db_path(self):
        return str(self._db_path)

    def _check_path(self):
        # Match the safe run-file conventions, including SQLite sidecars. These
        # checks assume the caller's private run directory is not hostile to it.
        if self._db_path.name != self.owner + ".sqlite3":
            raise CompostError("owner journal filename mismatch")
        for path in (self._db_path, *(Path(str(self._db_path) + suffix)
                                     for suffix in ("-journal", "-wal", "-shm"))):
            for item in reversed((path, *path.parents)):
                try:
                    mode = item.lstat().st_mode
                except FileNotFoundError:
                    continue
                except OSError:
                    raise CompostError("unavailable owner journal path") from None
                if stat.S_ISLNK(mode):
                    raise CompostError("symlink owner journal path forbidden")
                if not (stat.S_ISREG(mode) if item == path else stat.S_ISDIR(mode)):
                    raise CompostError("invalid owner journal path")

    def _private_file(self):
        self._check_path()
        # Make only missing directories private, without chmodding other roots.
        missing = []
        current = self._db_path.parent
        while not current.exists():
            missing.append(current)
            current = current.parent
        for path in reversed(missing):
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                self._check_path()
        ensure_private_db_file(self._db_path)
        self._check_path()
        # Explicit writers secure their own database; read-only calls never do.
        for path in (self._db_path, *(Path(str(self._db_path) + suffix)
                                     for suffix in ("-journal", "-wal", "-shm"))):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            except FileNotFoundError:
                continue
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise CompostError("invalid owner journal file")
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)

    @contextmanager
    def _connection(self, *, write=False):
        self._check_path()
        if write:
            self._private_file()
        elif not self._db_path.is_file():
            yield None
            return
        conn = sqlite3.connect(self._db_path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                               uri=True, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            if not write:
                conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if write:
                self._schema(conn)
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _tables(conn):
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    @staticmethod
    def _schema(conn):
        # No executescript: DDL, receipt and journal effect share one transaction.
        statements = (
            """CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
                mood TEXT DEFAULT 'neutral', hrv_at_writing REAL,
                phase TEXT DEFAULT 'symmetry', is_private INTEGER DEFAULT 1,
                created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS compost_note_metadata (
                journal_id INTEGER PRIMARY KEY REFERENCES journal(id),
                author TEXT NOT NULL, channels TEXT NOT NULL,
                note_kind TEXT NOT NULL CHECK(note_kind IN ('note','compost','distillation')),
                state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','released')),
                source_wake_id TEXT, source_mode TEXT NOT NULL CHECK(source_mode IN ('offline','real')))""",
            """CREATE TABLE IF NOT EXISTS compost_operations (
                operation_key TEXT PRIMARY KEY, operation_type TEXT NOT NULL
                    CHECK(operation_type IN ('note','distillation')),
                prepare_payload TEXT, snapshot_json TEXT, apply_payload TEXT, result_json TEXT,
                created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS compost_source_links (
                digest_id INTEGER NOT NULL REFERENCES journal(id),
                source_id INTEGER NOT NULL REFERENCES journal(id), position INTEGER NOT NULL,
                PRIMARY KEY(digest_id,source_id), UNIQUE(digest_id,position))""",
            """CREATE TRIGGER IF NOT EXISTS compost_original_body BEFORE UPDATE OF content ON journal
                WHEN EXISTS(SELECT 1 FROM compost_note_metadata WHERE journal_id=OLD.id)
                BEGIN SELECT RAISE(ABORT,'immutable compost original'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_original_delete BEFORE DELETE ON journal
                WHEN EXISTS(SELECT 1 FROM compost_note_metadata WHERE journal_id=OLD.id)
                BEGIN SELECT RAISE(ABORT,'preserve compost original'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_metadata_identity BEFORE UPDATE OF
                journal_id,author,channels,note_kind,source_wake_id,source_mode ON compost_note_metadata
                BEGIN SELECT RAISE(ABORT,'immutable compost attribution'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_metadata_delete BEFORE DELETE ON compost_note_metadata
                BEGIN SELECT RAISE(ABORT,'preserve compost metadata'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_release_one_way BEFORE UPDATE OF state ON compost_note_metadata
                WHEN OLD.state='released' AND NEW.state!='released'
                BEGIN SELECT RAISE(ABORT,'archived compost'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_operations_identity BEFORE UPDATE OF
                operation_key,operation_type,prepare_payload,snapshot_json,created_at ON compost_operations
                BEGIN SELECT RAISE(ABORT,'immutable compost selection'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_operations_result BEFORE UPDATE OF
                apply_payload,result_json ON compost_operations WHEN OLD.apply_payload IS NOT NULL
                BEGIN SELECT RAISE(ABORT,'immutable compost receipt'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_operations_delete BEFORE DELETE ON compost_operations
                BEGIN SELECT RAISE(ABORT,'preserve compost operation'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_links_update BEFORE UPDATE ON compost_source_links
                BEGIN SELECT RAISE(ABORT,'immutable compost source link'); END""",
            """CREATE TRIGGER IF NOT EXISTS compost_links_delete BEFORE DELETE ON compost_source_links
                BEGIN SELECT RAISE(ABORT,'preserve compost source link'); END""",
        )
        for statement in statements:
            conn.execute(statement)

    @staticmethod
    def _key(operation_key):
        if not isinstance(operation_key, str) or not operation_key.strip() or len(operation_key.encode("utf-8")) > 512:
            raise CompostError("invalid operation key")
        return operation_key

    def _payload(self, content, channels, source_wake_id, source_mode, **extra):
        if not isinstance(content, str):
            raise CompostError("content must be literal text")
        if len(content) > MAX_CONTENT_CHARS or len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise CompostError("content exceeds journal bounds")
        if source_mode not in ("offline", "real"):
            raise CompostError("invalid source mode")
        if source_wake_id is not None and (not isinstance(source_wake_id, str)
                or not source_wake_id.strip() or len(source_wake_id.encode("utf-8")) > 200):
            raise CompostError("invalid source wake id")
        return dict(owner=self.owner, content=content, channels=_channels(channels),
                    source_wake_id=source_wake_id, source_mode=source_mode, **extra)

    @staticmethod
    def _result(note_id=None):
        return {"status": "applied" if note_id is not None else "no_change",
                "refs": [{"kind": "journal", "id": note_id}] if note_id is not None else [], "id": note_id}

    @staticmethod
    def _previous(conn, operation_key, operation_type):
        row = conn.execute("SELECT operation_type,prepare_payload,snapshot_json,apply_payload,result_json "
                           "FROM compost_operations WHERE operation_key=? LIMIT 1", (operation_key,)).fetchone()
        if row is not None and row["operation_type"] != operation_type:
            raise CompostConflict("compost operation type conflict")
        return row

    @staticmethod
    def _insert_note(conn, payload, note_kind):
        now = datetime.now(timezone.utc).isoformat()
        note_id = conn.execute("INSERT INTO journal(content,created_at) VALUES (?,?)",
                               (payload["content"], now)).lastrowid
        conn.execute("INSERT INTO compost_note_metadata "
                     "(journal_id,author,channels,note_kind,source_wake_id,source_mode) VALUES (?,?,?,?,?,?)",
                     (note_id, payload["owner"], _json(payload["channels"]), note_kind,
                      payload["source_wake_id"], payload["source_mode"]))
        return note_id

    def append_note(self, operation_key, content, *, channels=None, note_kind="note",
                    source_wake_id=None, source_mode="real"):
        operation_key = self._key(operation_key)
        if note_kind not in ("note", "compost"):
            raise CompostError("invalid note kind")
        payload = self._payload(content, channels, source_wake_id, source_mode, note_kind=note_kind)
        encoded = _json(payload)
        with self._connection(write=True) as conn:
            previous = self._previous(conn, operation_key, "note")
            if previous is not None:
                if previous["apply_payload"] != encoded:
                    raise CompostConflict("compost note payload conflict")
                return json.loads(previous["result_json"])
            note_id = self._insert_note(conn, payload, note_kind) if content.strip() else None
            result = self._result(note_id)
            conn.execute("INSERT INTO compost_operations "
                         "(operation_key,operation_type,apply_payload,result_json,created_at) VALUES (?,'note',?,?,?)",
                         (operation_key, encoded, _json(result), datetime.now(timezone.utc).isoformat()))
            return result

    def prepare_distillation(self, operation_key, source_ids=None, *, max_chars=4000):
        operation_key = self._key(operation_key)
        _integer(max_chars, "source excerpt bound", maximum=MAX_SOURCE_CHARS)
        if source_ids is not None:
            if not isinstance(source_ids, (list, tuple)) or len(source_ids) > MAX_SOURCES:
                raise CompostError("invalid source ids")
            source_ids = [_integer(item, "source id") for item in source_ids]
            if len(set(source_ids)) != len(source_ids):
                raise CompostError("duplicate source ids")
        encoded = _json({"owner": self.owner, "source_ids": source_ids, "max_chars": max_chars})
        with self._connection(write=True) as conn:
            previous = self._previous(conn, operation_key, "distillation")
            if previous is not None:
                if previous["prepare_payload"] != encoded:
                    raise CompostConflict("compost source selection conflict")
                return json.loads(previous["snapshot_json"])
            if source_ids is None:
                source_ids = [row[0] for row in conn.execute(
                    "SELECT j.id FROM journal j JOIN compost_note_metadata m ON m.journal_id=j.id "
                    "WHERE m.author=? AND m.note_kind='compost' AND m.state='active' ORDER BY j.id DESC LIMIT 10",
                    (self.owner,))]
            notes = []
            remaining_chars, remaining_bytes = max_chars, MAX_CONTENT_BYTES
            for source_id in source_ids:
                row = conn.execute("SELECT j.content,m.channels,m.source_mode FROM journal j "
                                   "JOIN compost_note_metadata m ON m.journal_id=j.id "
                                   "WHERE j.id=? AND m.author=? AND m.note_kind='compost' LIMIT 1",
                                   (source_id, self.owner)).fetchone()
                if row is None:
                    raise CompostError("source is not owned compost")
                excerpt, truncated = _bounded(row["content"], remaining_chars, remaining_bytes)
                remaining_chars -= len(excerpt)
                remaining_bytes -= len(excerpt.encode("utf-8"))
                notes.append({"id": source_id, "content": excerpt, "channels": json.loads(row["channels"]),
                              "source_mode": row["source_mode"], "truncated": truncated})
            result = {"status": "ready" if notes else "empty", "source_ids": source_ids, "notes": notes,
                      "truncated": any(note["truncated"] for note in notes)}
            conn.execute("INSERT INTO compost_operations "
                         "(operation_key,operation_type,prepare_payload,snapshot_json,created_at) "
                         "VALUES (?,'distillation',?,?,?)",
                         (operation_key, encoded, _json(result), datetime.now(timezone.utc).isoformat()))
            return result

    def apply_distillation(self, operation_key, content, *, channels=None, release=False,
                           source_wake_id=None, source_mode="real"):
        operation_key = self._key(operation_key)
        if type(release) is not bool:
            raise CompostError("release must be boolean")
        payload = self._payload(content, channels, source_wake_id, source_mode, release=release)
        encoded = _json(payload)
        with self._connection(write=True) as conn:
            previous = self._previous(conn, operation_key, "distillation")
            if previous is None:
                raise CompostError("distillation must be prepared before applying")
            if previous["apply_payload"] is not None:
                if previous["apply_payload"] != encoded:
                    raise CompostConflict("compost distillation payload conflict")
                return json.loads(previous["result_json"])
            snapshot = json.loads(previous["snapshot_json"])
            note_id = None
            if content.strip() and snapshot["source_ids"]:
                note_id = self._insert_note(conn, payload, "distillation")
                for position, source_id in enumerate(snapshot["source_ids"]):
                    source = conn.execute("SELECT j.id FROM journal j JOIN compost_note_metadata m ON m.journal_id=j.id "
                                          "WHERE j.id=? AND m.author=? AND m.note_kind='compost' LIMIT 1",
                                          (source_id, self.owner)).fetchone()
                    if source is None:
                        raise CompostConflict("frozen compost source unavailable")
                    conn.execute("INSERT INTO compost_source_links(digest_id,source_id,position) VALUES (?,?,?)",
                                 (note_id, source_id, position))
                    if release:
                        conn.execute("UPDATE compost_note_metadata SET state='released' "
                                     "WHERE journal_id=? AND author=? AND note_kind='compost'",
                                     (source_id, self.owner))
            result = self._result(note_id)
            conn.execute("UPDATE compost_operations SET apply_payload=?,result_json=? WHERE operation_key=?",
                         (encoded, _json(result), operation_key))
            return result

    def _projection(self, conn, tables):
        if "compost_note_metadata" in tables:
            return ("SELECT j.id,j.content,j.created_at,m.author,m.channels,m.note_kind,m.state,"
                    "m.source_wake_id,m.source_mode FROM journal j LEFT JOIN compost_note_metadata m ON m.journal_id=j.id")
        return ("SELECT j.id,j.content,j.created_at,NULL AS author,NULL AS channels,NULL AS note_kind,"
                "NULL AS state,NULL AS source_wake_id,NULL AS source_mode FROM journal j")

    def _note(self, conn, row, tables, *, original=False):
        if row["author"] is not None and row["author"] != self.owner:
            raise CompostError("foreign journal metadata")
        content, truncated = (row["content"], False) if original else _bounded(row["content"], MAX_SOURCE_CHARS)
        links = []
        if "compost_source_links" in tables and "compost_note_metadata" in tables:
            for source in conn.execute(
                    "SELECT j.id,j.created_at,m.author,m.channels,m.note_kind,m.state,m.source_wake_id,m.source_mode "
                    "FROM compost_source_links l JOIN journal j ON j.id=l.source_id "
                    "JOIN compost_note_metadata m ON m.journal_id=j.id WHERE l.digest_id=? ORDER BY l.position LIMIT 20",
                    (row["id"],)):
                if source["author"] != self.owner or source["note_kind"] != "compost":
                    raise CompostError("foreign journal source link")
                link = dict(source)
                link["kind"] = "journal"
                link["channels"] = json.loads(link["channels"])
                links.append(link)
        return {"id": row["id"], "content": content,
                "channels": json.loads(row["channels"]) if row["channels"] is not None else ["unclassified"],
                "note_kind": row["note_kind"] or "note", "state": row["state"] or "active",
                "author": row["author"] or self.owner, "source_mode": row["source_mode"],
                "created_at": row["created_at"], "source_wake_id": row["source_wake_id"],
                "source_ids": [link["id"] for link in links], "source_links": links, "truncated": truncated}

    def list_notes(self, *, channel="unclassified", state="all", limit=20, offset=0):
        if channel not in (*CHANNELS, "unclassified") or state not in ("active", "released", "all"):
            raise CompostError("invalid journal filter")
        _integer(limit, "limit", maximum=MAX_SOURCES)
        _integer(offset, "offset", minimum=0)
        with self._connection() as conn:
            if conn is None:
                return {"status": "missing", "notes": [], "total": 0}
            tables = self._tables(conn)
            if "journal" not in tables:
                return {"status": "missing", "notes": [], "total": 0}
            # Classification is at most three exact labels, stored as JSON. Avoid
            # dependence on SQLite JSON extensions or reading full bodies to filter.
            if "compost_note_metadata" in tables:
                channel_filter = "(m.channels IS NULL OR m.channels=?)" if channel == "unclassified" else "m.channels LIKE ?"
                parameters = [_json(["unclassified"]) if channel == "unclassified" else '%"' + channel + '"%']
                where = " WHERE (m.author IS NULL OR m.author=?) AND " + channel_filter
                parameters.insert(0, self.owner)
                if state != "all":
                    where += " AND COALESCE(m.state,'active')=?"
                    parameters.append(state)
                joins = " FROM journal j LEFT JOIN compost_note_metadata m ON m.journal_id=j.id"
            else:
                where = " WHERE 1=1" if channel == "unclassified" and state != "released" else " WHERE 1=0"
                parameters = []
                joins = " FROM journal j"
            total = conn.execute("SELECT COUNT(*)" + joins + where, parameters).fetchone()[0]
            rows = conn.execute(self._projection(conn, tables) + where + " ORDER BY j.id DESC LIMIT ? OFFSET ?",
                                (*parameters, limit, offset)).fetchall()
            return {"status": "ok", "notes": [self._note(conn, row, tables) for row in rows], "total": total}

    def get_note(self, note_id):
        _integer(note_id, "note id")
        with self._connection() as conn:
            if conn is None:
                return None
            tables = self._tables(conn)
            if "journal" not in tables:
                return None
            row = conn.execute(self._projection(conn, tables) + " WHERE j.id=? LIMIT 1", (note_id,)).fetchone()
            return self._note(conn, row, tables, original=True) if row is not None else None

    def active_catalog(self, limit=10):
        _integer(limit, "limit", maximum=MAX_SOURCES)
        with self._connection() as conn:
            if conn is None:
                return []
            tables = self._tables(conn)
            if "journal" not in tables or "compost_note_metadata" not in tables:
                return []
            return [{"id": row["id"], "channels": json.loads(row["channels"])} for row in conn.execute(
                "SELECT j.id,m.channels FROM journal j JOIN compost_note_metadata m ON m.journal_id=j.id "
                "WHERE m.author=? AND m.note_kind='compost' AND m.state='active' ORDER BY j.id DESC LIMIT ?",
                (self.owner, limit))]

    def is_released(self, note_id):
        _integer(note_id, "note id")
        with self._connection() as conn:
            if conn is None or "compost_note_metadata" not in self._tables(conn):
                return False
            row = conn.execute("SELECT m.state FROM compost_note_metadata m JOIN journal j ON j.id=m.journal_id "
                               "WHERE j.id=? AND m.author=? LIMIT 1", (note_id, self.owner)).fetchone()
            return row is not None and row["state"] == "released"
