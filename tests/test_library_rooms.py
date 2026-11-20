"""Library rooms: the writings shelf is untouched; the research room is its own shelf.

Actual temporary stores and the checked-in corpora; the network is blocked."""
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

from core.library.store import LibraryStore
from core.runtime.rehearsal.controller import RESEARCH_CORPUS, RehearsalController, validate_choice
from core.runtime.rehearsal.examples import ScriptedHTTP
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_library  # noqa: E402


class LibraryRoomTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_the_research_room_builds_reproducibly_from_checksummed_notes(self):
        corpus = import_library.build_research_corpus()
        rendered = json.dumps(corpus, ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(rendered, (ROOT / "library" / "research-corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(len(corpus["documents"]), 21)
        first = corpus["documents"][0]
        self.assertEqual(first["title"], "Reading note P01: The Pricing of Options and Corporate Liabilities")
        self.assertEqual((first["room"], first["kind"]), ("research", "reading note about the paper, not the paper"))
        self.assertEqual(first["url"], "https://doi.org/10.1086/260062")
        tampered = self.root / "research"
        shutil.copytree(ROOT / "library" / "research", tampered)
        note = tampered / "reading-notes" / "P01.md"
        note.write_bytes(note.read_bytes() + b"\nchanged")
        with self.assertRaisesRegex(ValueError, "MANIFEST"):
            import_library.build_research_corpus(tampered)

    def test_missing_expected_note_is_rejected_before_extraction(self):
        folder = self.root / "research"
        shutil.copytree(ROOT / "library" / "research", folder)
        (folder / "reading-notes" / "P01.md").unlink()
        with self.assertRaisesRegex(ValueError, "missing:.*P01.md"):
            import_library.build_research_corpus(folder)

    def test_the_library_choice_takes_an_optional_room(self):
        self.assertEqual(validate_choice('{"action":"library","query":"options","room":"research"}')["room"], "research")
        validate_choice('{"action":"library","room":"writings"}')
        for bad in ('{"action":"library","room":"attic"}', '{"action":"roam","room":"research"}'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_choice(bad)

    def test_a_wake_reads_either_room_or_both_and_research_says_what_it_is(self):
        store = RehearsalStore(self.root / "sessions")
        run_id = store.prepare(day_manifest())["run_id"]
        controller = RehearsalController(store, run_id, transport=OpenRouterTransport(
            "scripted-offline", http_post=ScriptedHTTP()), repo_root=ROOT)
        controller.prepare_profiles()
        self.assertTrue(store.run_path(run_id).joinpath(RESEARCH_CORPUS).exists())  # Frozen with the run.
        research = controller._library("volatility options", "research")
        self.assertEqual(research["room"], "research")
        self.assertTrue(research["results"])
        row = research["results"][0]
        self.assertEqual((row["room"], row["kind"]), ("research", "reading note about the paper, not the paper"))
        self.assertTrue(row["title"].startswith("Reading note P"))
        self.assertIn("evidence", row)
        writings = controller._library("paradox", "writings")
        self.assertTrue(all(r["room"] == "writings" for r in writings["results"]))
        both = controller._library("paradox options", None)
        self.assertEqual(both["room"], "both")
        self.assertLessEqual(len(both["results"]), 3)
        self.assertEqual({r["room"] for r in both["results"]}, {"writings", "research"})

    def test_the_writings_shelf_is_unchanged_so_old_references_resolve(self):
        corpus = json.loads((ROOT / "library" / "corpus.json").read_text(encoding="utf-8"))
        self.assertTrue(all("room" not in doc for doc in corpus["documents"]))
        library = LibraryStore(ROOT / "library" / "corpus.json", self.root / "writings.sqlite3")
        first = corpus["sections"][0]["section_id"]
        self.assertEqual(library.read_section(first)["section_id"], first)


if __name__ == "__main__":
    unittest.main()
