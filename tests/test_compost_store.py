"""CompostStore contract tests. Every database is owned by a TemporaryDirectory.

Run: python -m unittest tests.test_compost_store -v
No engine bootstrap, real configuration, transport, credentials or user DBs.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from unittest import mock

from core.memory.compost import CompostConflict, CompostError, CompostStore


# The actual older journal schema (including its old defaults), not a new store
# passed off as legacy. Other legacy private tables must never be projected.
LEGACY_SCHEMA = """
CREATE TABLE journal (
 id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL,
 mood TEXT DEFAULT 'neutral', hrv_at_writing REAL, phase TEXT DEFAULT 'symmetry',
 is_private INTEGER DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE innermost (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE glyphs (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
"""


class CompostStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="compost-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "memory" / "siren.sqlite3"
        self.store = CompostStore(self.path, "siren")

    def compost(self, key, content="literal compost", **kwargs):
        return self.store.append_note(key, content, note_kind="compost", source_mode="offline", **kwargs)["id"]

    def reopened(self):
        return CompostStore(self.path, "siren")

    def sql(self, query, parameters=()):
        with sqlite3.connect(self.path) as conn:
            return conn.execute(query, parameters).fetchall()

    def tree_snapshot(self):
        result = {}
        for path in self.root.rglob("*"):
            if path.is_file():
                st = path.stat()
                result[str(path.relative_to(self.root))] = (
                    hashlib.sha256(path.read_bytes()).hexdigest(), st.st_mtime_ns,
                    stat.S_IMODE(st.st_mode), st.st_size)
            else:
                result[str(path.relative_to(self.root))] = "directory"
        return result

    def make_legacy(self):
        self.path.parent.mkdir()
        with sqlite3.connect(self.path) as conn:
            conn.executescript(LEGACY_SCHEMA)
            conn.execute("INSERT INTO journal(id,content,mood,hrv_at_writing,phase,is_private,created_at) "
                         "VALUES (41,?,'ambivalent',72.3,'tension',1,'2024-01-02T03:04:05+00:00')",
                         ("Old words: trading, idea, orientation. Do not classify me.\n雪 🌀",))
            conn.execute("INSERT INTO innermost(content,created_at) VALUES ('INNERMOST_SECRET','old')")
            conn.execute("INSERT INTO glyphs(title,content,created_at) VALUES ('glyph','GLYPH_SECRET','old')")
        return self.sql("SELECT * FROM journal WHERE id=41")[0]

    def test_read_only_missing_does_not_create_files_or_directories(self):
        self.assertEqual(self.tree_snapshot(), {})
        with mock.patch("core.memory.compost.ensure_private_db_file", side_effect=AssertionError("write")), \
             mock.patch("core.memory.compost.sqlite3.connect", side_effect=AssertionError("missing connect")):
            self.assertEqual(self.store.list_notes(), {"status": "missing", "notes": [], "total": 0})
            self.assertIsNone(self.store.get_note(1))
            self.assertEqual(self.store.active_catalog(), [])
            self.assertIs(self.store.is_released(1), False)
        self.assertEqual(self.tree_snapshot(), {})

    def test_actual_legacy_reads_unclassified_without_migration_or_private_projection(self):
        original = self.make_legacy()
        before = self.tree_snapshot()
        with mock.patch("core.memory.compost.ensure_private_db_file", side_effect=AssertionError("write")):
            notes = self.reopened().list_notes()
            self.assertEqual(notes["status"], "ok")
            self.assertEqual(notes["total"], 1)
            note = notes["notes"][0]
            self.assertEqual(note["id"], 41)
            self.assertEqual(note["content"], original[1])
            self.assertEqual(note["channels"], ["unclassified"])
            self.assertEqual(note["note_kind"], "note")
            self.assertEqual(note["state"], "active")
            self.assertEqual(note["author"], "siren")
            self.assertIsNone(note["source_mode"])  # Never invent a legacy transport.
            self.assertEqual(note["source_ids"], [])
            self.assertEqual(note["source_links"], [])
            for channel in ("idea", "trading", "orientation"):
                self.assertEqual(self.store.list_notes(channel=channel)["notes"], [])
            self.assertEqual(self.store.list_notes(state="released")["notes"], [])
            self.assertEqual(self.store.get_note(41), note)
            self.assertIsNone(self.store.get_note(42))
            self.assertEqual(self.store.active_catalog(), [])
            self.assertIs(self.store.is_released(41), False)
        self.assertNotIn("INNERMOST_SECRET", str(notes))
        self.assertNotIn("GLYPH_SECRET", str(notes))
        self.assertEqual(self.tree_snapshot(), before)
        self.assertEqual(self.sql("SELECT * FROM journal WHERE id=41")[0], original)

    def test_existing_database_without_journal_stays_missing_without_ddl(self):
        self.path.parent.mkdir()
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")
        before = self.tree_snapshot()
        self.assertEqual(self.store.list_notes(), {"status": "missing", "notes": [], "total": 0})
        self.assertIsNone(self.store.get_note(1))
        self.assertEqual(self.store.active_catalog(), [])
        self.assertIs(self.store.is_released(1), False)
        self.assertEqual(self.tree_snapshot(), before)

    def test_source_ids_are_local_not_commands_or_peer_journal_references(self):
        peer = CompostStore(self.path.parent / "tempest.sqlite3", "tempest")
        peer.append_note("peer-one", "PEER_SECRET_ONE", note_kind="compost")
        peer_id = peer.append_note("peer-two", "PEER_SECRET_TWO", note_kind="compost")["id"]
        own = self.compost("own", "OWN_LITERAL")
        self.assertEqual(own, 1)
        with self.assertRaises(CompostError):
            self.store.prepare_distillation("foreign-id", [peer_id])
        snapshot = self.store.prepare_distillation("own-only", [own])
        self.assertEqual(snapshot["notes"][0]["content"], "OWN_LITERAL")
        self.assertNotIn("PEER_SECRET", str(snapshot))
        for channels in ([], ()):
            note_id = self.store.append_note("empty-" + str(type(channels)), "unclassified", channels=channels)["id"]
            self.assertEqual(self.store.get_note(note_id)["channels"], ["unclassified"])

    def test_reads_use_ro_connections_and_cannot_execute_mutations(self):
        note_id = self.compost("first")
        before = self.tree_snapshot()
        connect = sqlite3.connect
        connections = []

        def guarded(*args, **kwargs):
            self.assertTrue(args[0].endswith("?mode=ro"))
            self.assertIs(kwargs["uri"], True)
            self.assertEqual(kwargs["timeout"], 30)
            conn = connect(*args, **kwargs)
            forbidden = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                         sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_ALTER_TABLE}
            conn.set_authorizer(lambda action, *unused: sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK)
            connections.append(True)
            return conn

        with mock.patch("core.memory.compost.sqlite3.connect", side_effect=guarded):
            self.store.list_notes()
            self.store.get_note(note_id)
            self.store.active_catalog()
            self.store.is_released(note_id)
        self.assertEqual(len(connections), 4)
        self.assertEqual(self.tree_snapshot(), before)

    def test_explicit_write_extends_legacy_without_copying_or_rewriting(self):
        original = self.make_legacy()
        new_id = self.compost("new", "A new literal", channels=["idea"])
        self.assertGreater(new_id, 41)
        self.assertEqual(self.sql("SELECT * FROM journal WHERE id=41")[0], original)
        self.assertEqual(self.store.get_note(41)["channels"], ["unclassified"])
        self.assertEqual(self.store.list_notes(channel="idea")["total"], 1)
        self.assertEqual(self.store.list_notes()["total"], 1)
        with self.assertRaises(CompostError):
            self.store.prepare_distillation("not-compost", [41])

    def test_literal_unicode_exact_refs_authorship_and_multi_classification(self):
        text = "  雪 🌀 e\u0301\nUnresolved: <script>not a command</script>\n  "
        result = self.store.append_note("note-exact", text, channels=["idea", "orientation"],
                                        source_wake_id="wake:offline-1", source_mode="offline")
        self.assertEqual(result, {"status": "applied", "refs": [{"kind": "journal", "id": 1}], "id": 1})
        note = self.reopened().get_note(result["id"])
        self.assertEqual(note["content"], text)
        self.assertEqual(note["author"], "siren")
        self.assertEqual(note["source_mode"], "offline")
        self.assertEqual(note["source_wake_id"], "wake:offline-1")
        self.assertEqual(note["channels"], ["idea", "orientation"])
        self.assertEqual(note["state"], "active")
        self.assertEqual(note["note_kind"], "note")
        self.assertEqual(self.store.list_notes(channel="idea")["notes"][0], note)
        self.assertEqual(self.store.list_notes(channel="orientation")["total"], 1)
        self.assertEqual(self.store.list_notes()["total"], 0)
        self.assertEqual(self.store.active_catalog(), [])
        real = self.store.append_note("real-label", "Mode label only")
        self.assertEqual(self.store.get_note(real["id"])["source_mode"], "real")
        tables = {r[0] for r in self.sql("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(tables, {"journal", "sqlite_sequence", "compost_note_metadata", "compost_operations", "compost_source_links"})
        self.assertFalse({"score", "joy", "glyph", "verified_personality"} & note.keys())

    def test_content_character_and_byte_caps_preserve_literal_prefixes(self):
        for key, text in (("chars", "a" * 6000), ("bytes", "雪" * 4000)):
            result = self.store.append_note(key, text)
            self.assertEqual(self.store.get_note(result["id"])["content"], text)
            preview = next(n for n in self.store.list_notes()["notes"] if n["id"] == result["id"])
            self.assertLessEqual(len(preview["content"]), 4000)
            self.assertLessEqual(len(preview["content"].encode("utf-8")), 12000)
            self.assertEqual(text[:len(preview["content"])], preview["content"])
            self.assertEqual(preview["truncated"], preview["content"] != text)
        for text in ("a" * 6001, "雪" * 4001, "🌀" * 3001):
            with self.assertRaises(CompostError):
                self.store.append_note("too-long", text)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 2)

    def test_no_minimum_no_automatic_trigger_and_default_ten_not_a_quota(self):
        ids = [self.compost("one", "one")]
        self.assertEqual(self.store.prepare_distillation("single", ids)["source_ids"], ids)
        for index in range(1, 12):
            ids.append(self.compost("source-" + str(index), "source " + str(index)))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 12)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_source_links")[0][0], 0)
        self.assertTrue(all(not self.store.is_released(note_id) for note_id in ids))
        selected = self.store.prepare_distillation("twelve", ids)
        self.assertEqual(selected["source_ids"], ids)
        self.assertEqual(len(selected["notes"]), 12)
        self.assertEqual(self.store.prepare_distillation("default")["source_ids"], list(reversed(ids))[:10])
        single = self.store.apply_distillation("single", "One source is permitted")
        self.assertEqual(self.store.get_note(single["id"])["source_ids"], ids[:1])
        twelve = self.store.apply_distillation("twelve", "Twelve sources are permitted")
        self.assertEqual(self.store.get_note(twelve["id"])["source_ids"], ids)

    def test_explicit_selection_twenty_max_unique_owned_compost_ids(self):
        ids = [self.compost("n" + str(index)) for index in range(21)]
        self.assertEqual(len(self.store.prepare_distillation("twenty", ids[:20])["notes"]), 20)
        ordinary = self.store.append_note("ordinary", "not compost")["id"]
        for bad in (ids, [ids[0], ids[0]], [True], ["1"], [0], [-1], [2**63], [ordinary], [999999], "1"):
            with self.subTest(bad=bad), self.assertRaises(CompostError):
                self.store.prepare_distillation("invalid", bad)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_operations WHERE operation_key='invalid'")[0][0], 0)

    def test_snapshot_total_bounded_literal_and_immutable_after_new_notes(self):
        first = self.compost("long-one", "é" * 3500, channels=["orientation", "idea"])
        second = self.compost("long-two", "雪" * 2000)
        prepared = self.store.prepare_distillation("frozen", [first, second])
        self.assertEqual(prepared["notes"][0]["content"], "é" * 3500)
        self.assertEqual(prepared["notes"][1]["content"], "雪" * 500)
        self.assertFalse(prepared["notes"][0]["truncated"])
        self.assertTrue(prepared["notes"][1]["truncated"])
        self.assertTrue(prepared["truncated"])
        self.assertEqual(sum(len(n["content"]) for n in prepared["notes"]), 4000)
        self.assertEqual(set(prepared), {"status", "source_ids", "notes", "truncated"})
        self.assertEqual(set(prepared["notes"][0]), {"id", "content", "channels", "source_mode", "truncated"})
        self.compost("later", "Not part of the frozen selection")
        self.assertEqual(self.reopened().prepare_distillation("frozen", [first, second]), prepared)
        with self.assertRaises(CompostConflict):
            self.store.prepare_distillation("frozen", [second, first])
        with self.assertRaises(CompostConflict):
            self.store.prepare_distillation("frozen", [first, second], max_chars=2000)
        emoji = self.compost("emoji", "🌀" * 3000)
        snap = self.store.prepare_distillation("byte-bound", [emoji, first])
        self.assertLessEqual(sum(len(n["content"].encode("utf-8")) for n in snap["notes"]), 12000)
        self.assertEqual(snap["notes"][0]["content"], "🌀" * 3000)
        self.assertEqual(snap["notes"][1]["content"], "")
        self.assertTrue(snap["notes"][1]["truncated"])
        for bound in (0, -1, 4001, True, "4000"):
            with self.assertRaises(CompostError):
                self.store.prepare_distillation("bad-bound", [first], max_chars=bound)

    def test_default_snapshot_is_frozen_not_reselected_on_retry(self):
        first = self.compost("first")
        prepared = self.store.prepare_distillation("default-freeze")
        self.compost("second")
        self.assertEqual(self.reopened().prepare_distillation("default-freeze"), prepared)
        self.assertEqual(prepared["source_ids"], [first])
        with self.assertRaises(CompostConflict):
            self.store.prepare_distillation("default-freeze", [first])

    def test_empty_and_whitespace_are_durable_no_change_and_never_release(self):
        no_change = {"status": "no_change", "refs": [], "id": None}
        self.assertEqual(self.store.append_note("empty-note", "\n \t"), no_change)
        self.assertEqual(self.reopened().append_note("empty-note", "\n \t"), no_change)
        with self.assertRaises(CompostConflict):
            self.store.append_note("empty-note", "changed")
        prepared = self.store.prepare_distillation("empty-default")
        self.assertEqual(prepared, {"status": "empty", "source_ids": [], "notes": [], "truncated": False})
        note_id = self.compost("later")
        self.assertEqual(self.reopened().prepare_distillation("empty-default"), prepared)
        self.assertEqual(self.store.apply_distillation("empty-default", "No frozen sources", release=True), no_change)
        self.store.prepare_distillation("empty-output", [note_id])
        self.assertEqual(self.store.apply_distillation("empty-output", " \n", release=True), no_change)
        self.assertEqual(self.reopened().apply_distillation("empty-output", " \n", release=True), no_change)
        self.assertIs(self.store.is_released(note_id), False)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 1)
        with self.assertRaises(CompostConflict):
            self.store.apply_distillation("empty-output", "Now a different result", release=True)
        self.assertEqual(self.store.prepare_distillation("explicit-empty", [])["status"], "empty")

    def test_atomic_digest_release_full_originals_and_provenance_links(self):
        texts = ["a" * 6000, "雪" * 3000]
        ids = [self.compost("src" + str(i), text, channels=["idea"], source_wake_id="source-wake")
               for i, text in enumerate(texts)]
        before = self.sql("SELECT * FROM journal ORDER BY id")
        prepared = self.store.prepare_distillation("digest", ids)
        result = self.store.apply_distillation("digest", "  Literal digest: still unresolved. 雪\n", channels=["idea", "orientation"],
                                               release=True, source_wake_id="digest-wake", source_mode="offline")
        self.assertEqual(result["refs"], [{"kind": "journal", "id": result["id"]}])
        digest = self.reopened().get_note(result["id"])
        self.assertEqual(digest["content"], "  Literal digest: still unresolved. 雪\n")
        self.assertEqual(digest["note_kind"], "distillation")
        self.assertEqual(digest["source_ids"], ids)
        self.assertEqual([link["id"] for link in digest["source_links"]], ids)
        for link, note_id, text in zip(digest["source_links"], ids, texts):
            self.assertEqual(link["kind"], "journal")
            self.assertEqual(link["author"], "siren")
            self.assertEqual(link["source_mode"], "offline")
            self.assertEqual(link["source_wake_id"], "source-wake")
            self.assertEqual(link["channels"], ["idea"])
            self.assertEqual(link["state"], "released")
            original = self.store.get_note(note_id)
            self.assertEqual(original["content"], text)
            self.assertFalse(original["truncated"])
            self.assertIs(self.store.is_released(note_id), True)
        self.assertEqual(self.sql("SELECT * FROM journal WHERE id IN (?,?) ORDER BY id", ids), before)
        self.assertEqual(self.store.list_notes(channel="idea", state="active")["total"], 1)
        self.assertEqual(self.store.list_notes(channel="idea", state="released")["total"], 2)
        self.assertEqual(self.store.list_notes(channel="idea", state="all")["total"], 3)
        self.assertEqual(self.store.active_catalog(), [])
        self.assertEqual(self.store.prepare_distillation("digest", ids), prepared)
        # Explicit archive links remain readable/selectable, not automatically active.
        self.assertEqual(self.store.prepare_distillation("archive-selected", ids)["source_ids"], ids)
        self.assertEqual(self.store.prepare_distillation("active-after-release")["status"], "empty")

    def test_no_release_keeps_compost_active_and_catalog_compact(self):
        note_id = self.compost("active", "A body that must not enter the catalog", channels=["trading", "idea"])
        self.store.prepare_distillation("keep", [note_id])
        self.store.apply_distillation("keep", "Separate agent distillation", release=False)
        self.assertIs(self.store.is_released(note_id), False)
        self.assertEqual(self.store.active_catalog(), [{"id": note_id, "channels": ["trading", "idea"]}])
        self.assertEqual(self.store.list_notes(channel="idea", state="active")["total"], 1)

    def test_note_receipt_conflicts_guard_all_metadata_and_operation_type(self):
        kwargs = dict(channels=["idea"], note_kind="compost", source_wake_id="wake", source_mode="offline")
        original = self.store.append_note("immutable", "literal", **kwargs)
        self.assertEqual(self.reopened().append_note("immutable", "literal", **kwargs), original)
        changes = [dict(content="different"), dict(channels=["orientation"]), dict(note_kind="note"),
                   dict(source_wake_id="other"), dict(source_mode="real")]
        for change in changes:
            call = dict(kwargs, content="literal")
            call.update(change)
            with self.subTest(change=change), self.assertRaises(CompostConflict):
                self.store.append_note("immutable", **call)
        with self.assertRaises(CompostConflict):
            self.store.prepare_distillation("immutable", [original["id"]])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 1)

    def test_distillation_retries_conflict_on_different_content_release_channels_or_attribution(self):
        source_id = self.compost("source")
        self.store.prepare_distillation("chosen", [source_id])
        kwargs = dict(channels=["orientation"], release=True, source_wake_id="wake", source_mode="offline")
        result = self.store.apply_distillation("chosen", "literal digest", **kwargs)
        self.assertEqual(self.reopened().apply_distillation("chosen", "literal digest", **kwargs), result)
        for change in (dict(content="different"), dict(release=False), dict(channels=["idea"]),
                       dict(source_wake_id="other"), dict(source_mode="real")):
            call = dict(kwargs, content="literal digest")
            call.update(change)
            with self.subTest(change=change), self.assertRaises(CompostConflict):
                self.store.apply_distillation("chosen", **call)
        with self.assertRaises(CompostConflict):
            self.store.append_note("chosen", "literal digest")
        with self.assertRaises(CompostError):
            self.store.apply_distillation("not-prepared", "output", release=True)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 2)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_source_links")[0][0], 1)

    def test_failure_rolls_back_digest_links_release_and_receipt_then_recovers(self):
        ids = [self.compost("one"), self.compost("two")]
        snapshot = self.store.prepare_distillation("atomic", ids)
        self.sql("CREATE TRIGGER test_release_failure BEFORE UPDATE OF state ON compost_note_metadata "
                 "WHEN NEW.journal_id=" + str(ids[1]) + " BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.apply_distillation("atomic", "literal output", release=True)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 2)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_source_links")[0][0], 0)
        self.assertEqual(self.sql("SELECT apply_payload,result_json FROM compost_operations WHERE operation_key='atomic'"), [(None, None)])
        self.assertTrue(all(not self.store.is_released(note_id) for note_id in ids))
        self.assertEqual(self.reopened().prepare_distillation("atomic", ids), snapshot)
        self.sql("DROP TRIGGER test_release_failure")
        result = self.reopened().apply_distillation("atomic", "literal output", release=True)
        self.assertEqual(self.store.get_note(result["id"])["source_ids"], ids)
        self.assertTrue(all(self.store.is_released(note_id) for note_id in ids))
        self.assertEqual(self.store.apply_distillation("atomic", "literal output", release=True), result)

    def test_append_failure_rolls_back_original_metadata_and_receipt(self):
        self.compost("initial")
        self.sql("CREATE TRIGGER test_receipt_failure BEFORE INSERT ON compost_operations "
                 "WHEN NEW.operation_key='fail' BEGIN SELECT RAISE(ABORT,'injected receipt failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.compost("fail", "must roll back")
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_note_metadata")[0][0], 1)
        self.sql("DROP TRIGGER test_receipt_failure")
        result = self.compost("fail", "must roll back")
        self.assertEqual(self.store.get_note(result)["content"], "must roll back")

    def test_original_and_receipt_protection_against_direct_rewrite_or_delete(self):
        note_id = self.compost("protected")
        self.store.prepare_distillation("frozen", [note_id])
        result = self.store.apply_distillation("frozen", "digest")
        for query in (
            "UPDATE journal SET content='rewritten' WHERE id=" + str(note_id),
            "DELETE FROM journal WHERE id=" + str(note_id),
            "UPDATE journal SET content='rewritten' WHERE id=" + str(result["id"]),
            "DELETE FROM compost_note_metadata",
            "UPDATE compost_note_metadata SET channels='[]'",
            "UPDATE compost_operations SET snapshot_json='{}' WHERE operation_key='frozen'",
            "UPDATE compost_operations SET result_json='{}' WHERE operation_key='frozen'",
            "DELETE FROM compost_operations", "DELETE FROM compost_source_links",
            "UPDATE compost_source_links SET source_id=999",
        ):
            with self.subTest(query=query), self.assertRaises(sqlite3.IntegrityError):
                self.sql(query)
        self.assertEqual(self.store.get_note(note_id)["content"], "literal compost")

    def test_concurrent_identical_operations_single_effect_and_single_release(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda unused: self.reopened().append_note(
                "race-note", "literal", note_kind="compost", source_mode="offline"), range(12)))
        self.assertTrue(all(result == results[0] for result in results))
        note_id = results[0]["id"]
        with ThreadPoolExecutor(max_workers=6) as pool:
            snapshots = list(pool.map(lambda unused: self.reopened().prepare_distillation("race-digest", [note_id]), range(12)))
        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))
        with ThreadPoolExecutor(max_workers=6) as pool:
            digests = list(pool.map(lambda unused: self.reopened().apply_distillation(
                "race-digest", "same chosen output", release=True, source_mode="offline"), range(12)))
        self.assertTrue(all(digest == digests[0] for digest in digests))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM journal")[0][0], 2)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM compost_source_links")[0][0], 1)
        self.assertIs(self.store.is_released(note_id), True)

    def test_write_waits_for_sqlite_lock_instead_of_splitting_transactions(self):
        self.compost("setup")
        lock = sqlite3.connect(self.path, timeout=30)
        self.addCleanup(lock.close)
        lock.execute("BEGIN IMMEDIATE")
        started = threading.Event()

        def write():
            started.set()
            return self.reopened().append_note("locked", "after lock")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(write)
            self.assertTrue(started.wait(timeout=2))
            time.sleep(0.1)
            self.assertFalse(future.done())
            lock.commit()
            result = future.result(timeout=5)
        self.assertEqual(self.store.get_note(result["id"])["content"], "after lock")

    def test_owner_binding_traversal_and_sidecar_symlinks_rejected_before_io(self):
        for owner, path in (("foreign", self.path), ("siren", self.root / "tempest.sqlite3"),
                            ("tempest", self.path), ("../siren", self.path),
                            ("siren", self.root / "memory" / ".." / "siren.sqlite3")):
            with self.subTest(owner=owner, path=path), self.assertRaises(CompostError):
                CompostStore(path, owner)
        self.assertEqual(self.tree_snapshot(), {})
        with self.assertRaises(AttributeError):
            self.store.owner = "tempest"
        with self.assertRaises(AttributeError):
            self.store.db_path = str(self.root / "tempest.sqlite3")
        target = self.root / "foreign.sqlite3"
        target.write_text("FOREIGN_SENTINEL", encoding="utf-8")
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        with self.assertRaises(CompostError):
            CompostStore(self.path, "siren")
        with self.assertRaises(CompostError):
            self.store.list_notes()
        self.path.unlink()
        self.compost("safe")
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            sidecar.symlink_to(target)
            with self.subTest(suffix=suffix), self.assertRaises(CompostError):
                self.store.get_note(1)
            with self.assertRaises(CompostError):
                self.store.append_note("unsafe", "no")
            sidecar.unlink()
        self.assertEqual(target.read_text(), "FOREIGN_SENTINEL")
        foreign_dir = self.root / "outside"
        foreign_dir.mkdir()
        directory_link = self.root / "linked"
        directory_link.symlink_to(foreign_dir, target_is_directory=True)
        with self.assertRaises(CompostError):
            CompostStore(directory_link / "siren.sqlite3", "siren")

    def test_private_new_file_directories_and_wal_sidecars(self):
        self.compost("private")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("SELECT id FROM journal").fetchall()
            self.compost("wal-private")
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.path) + suffix)
                self.assertTrue(sidecar.is_file())
                self.assertEqual(stat.S_IMODE(sidecar.stat().st_mode), 0o600)
        finally:
            conn.close()

    def test_pagination_and_strict_input_validation(self):
        ids = [self.store.append_note("page" + str(index), str(index))["id"] for index in range(4)]
        page = self.store.list_notes(limit=2, offset=1)
        self.assertEqual(page["total"], 4)
        self.assertEqual([n["id"] for n in page["notes"]], list(reversed(ids))[1:3])
        self.assertEqual(self.store.list_notes(offset=10)["notes"], [])
        for filters in (dict(channel="all"), dict(channel="innermost"), dict(state="archive"),
                        dict(limit=21), dict(limit=0), dict(limit=True), dict(offset=-1), dict(offset="0")):
            with self.subTest(filters=filters), self.assertRaises(CompostError):
                self.store.list_notes(**filters)
        for fields in (dict(channels=["idea", "idea"]), dict(channels=["unclassified"]),
                       dict(channels="idea"), dict(channels=["score"]), dict(note_kind="digest"),
                       dict(source_mode="verified"), dict(source_wake_id={"command": "read peer"})):
            with self.subTest(fields=fields), self.assertRaises(CompostError):
                self.store.append_note("bad-input", "literal", **fields)
        with self.assertRaises(TypeError):
            self.store.append_note("peer", "literal", source_peer_ref="tempest")
        with self.assertRaises(CompostError):
            self.store.append_note("", "literal")
        with self.assertRaises(CompostError):
            self.store.apply_distillation("release", "literal", release=1)
        for invalid in (True, "1", -1, 0):
            with self.assertRaises(CompostError):
                self.store.get_note(invalid)
            with self.assertRaises(CompostError):
                self.store.is_released(invalid)
        self.assertIs(self.store.is_released(9999), False)


if __name__ == "__main__":
    unittest.main()
