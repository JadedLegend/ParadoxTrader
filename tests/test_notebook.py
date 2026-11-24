"""The notebook (docs/specs/NOTEBOOK.md): a line to remember on any move, printed on
every page, composted when full. Actual temporary stores; the network is blocked."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from core.memory.compost import CompostStore
from core.runtime.rehearsal.controller import RehearsalController, validate_choice
from core.runtime.rehearsal.examples import ScriptedHTTP, ScriptedResponse
from core.runtime.rehearsal.home import CARRIED_FILES
from core.runtime.rehearsal.notebook import (CAPACITY, NOTEBOOK_FILE, NotebookStore, notebook_text)
from core.runtime.rehearsal.provider import OpenRouterTransport
from core.runtime.rehearsal.store import RehearsalStore
from tests.test_day_runs import day_manifest


class Blocked(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)


class NotebookStoreTests(Blocked):
    def setUp(self):
        super().setUp()
        self.book = NotebookStore(Path(self.temp.name) / NOTEBOOK_FILE)

    def add(self, wake, text, agent="tempest"):
        return self.book.add(agent, run_id="run-a", wake_id=wake, content=text)

    def test_a_line_is_kept_once_per_move_and_only_its_owner_sees_it(self):
        self.assertEqual(self.add("tempest-r1", "Watch GLD after rate news."), "kept")
        self.assertEqual(self.add("tempest-r1", "Watch GLD after rate news."), "kept")  # A retried move.
        kept, refused = self.book.page("tempest")
        self.assertEqual([line["content"] for line in kept], ["Watch GLD after rate news."])
        self.assertEqual((refused, self.book.page("siren")), ([], ([], [])))

    def test_nothing_fades_a_line_that_does_not_fit_is_refused_and_quoted_back(self):
        for n in range(20):
            self.assertEqual(self.add(f"tempest-r{n + 1}", chr(65 + n) * 299), "kept")  # 20 x 299 + 19 breaks = 5999.
        self.assertEqual(self.book.used("tempest"), 5999)
        self.assertEqual(self.add("tempest-r21", "one more thought"), "did_not_fit")
        kept, refused = self.book.page("tempest")
        self.assertEqual((len(kept), [r["content"] for r in refused]), (20, ["one more thought"]))
        self.assertEqual(kept[0]["content"], "A" * 299)  # The oldest line is still there.
        text = notebook_text(kept, refused)
        self.assertIn("one more thought", text)
        self.assertIn('Your notebook is full. To keep writing, compost it: {"action":"compost_notebook"}.', text)

    def test_composting_moves_every_line_into_one_note_and_starts_fresh(self):
        self.add("tempest-r1", "first")
        self.add("tempest-r2", "second")
        written = []

        def write_note(content):
            written.append(content)
            return [{"kind": "journal", "id": 7}]

        refs = self.book.compost("tempest", run_id="run-a", wake_id="tempest-r3", write_note=write_note)
        self.assertEqual((refs, written), ([{"kind": "journal", "id": 7}], ["first\nsecond"]))
        self.assertEqual(self.book.page("tempest"), ([], []))
        again = self.book.compost("tempest", run_id="run-a", wake_id="tempest-r3", write_note=write_note)
        self.assertEqual((again, len(written)), (refs, 1))  # A retried compost writes nothing new.
        self.add("tempest-r4", "fresh")
        self.assertEqual([line["content"] for line in self.book.page("tempest")[0]], ["fresh"])
        self.assertEqual(self.book.sizes(), {"tempest": 5})

    def test_a_full_notebook_always_fits_one_compost_note(self):
        from core.memory.compost import MAX_CONTENT_CHARS
        self.assertLessEqual(CAPACITY, MAX_CONTENT_CHARS)

    def test_the_page_says_when_it_is_empty_or_nearly_full(self):
        self.assertIn("(empty", notebook_text([], []))
        nearly = [{"wake_id": "tempest-r1", "content": "x" * 300}] * 17
        self.assertIn("nearly full", notebook_text(nearly, []))

    def test_the_choice_carries_one_short_line(self):
        self.assertEqual(validate_choice(json.dumps({"action": "rest", "remember": "keep this"}))["remember"],
                         "keep this")
        self.assertEqual(validate_choice('{"action":"compost_notebook"}')["action"], "compost_notebook")
        for bad in ("", "x" * 301, "two\nlines", 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_choice(json.dumps({"action": "rest", "remember": bad}))
        self.assertIn(NOTEBOOK_FILE, CARRIED_FILES)


class NotebookWakeTests(Blocked):
    """Through actual wakes: free, on every page, private, composted mechanically."""

    def setUp(self):
        super().setUp()
        self.store = RehearsalStore(Path(self.temp.name) / "sessions")
        self.day = self.store.prepare(day_manifest(wakes=10))["run_id"]
        self.choices = {}
        scripted = ScriptedHTTP()

        def http(url, *, json=None, **kwargs):
            text = "\n".join(str(m.get("content", "")) for m in (json or {}).get("messages", []))
            for owner, queue in self.choices.items():
                if "REHEARSAL CHOICE" in text and f"Stable owner ID: {owner}" in text and queue:
                    content = queue.pop(0)
                    self.pages.setdefault(owner, []).append(text)
                    return ScriptedResponse({"id": "x", "model": json.get("model"), "provider": "scripted-offline",
                                             "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                                             "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                                       "total_tokens": 2, "cost": "0"}})
            return scripted(url, json=json, **kwargs)

        self.http, self.pages = http, {}

    def wake(self, owner="tempest", step=None):
        return RehearsalController(self.store, self.day, transport=OpenRouterTransport(
            "scripted-offline", http_post=self.http)).run_wake(owner, step=step)

    def book(self):
        return NotebookStore(self.store.safe_run_file(self.day, NOTEBOOK_FILE))

    def test_a_line_costs_nothing_and_shows_on_every_later_page(self):
        self.choices["tempest"] = ['{"action":"rest","remember":"Breadth narrowed before the drop."}',
                                   '{"action":"rest"}', '{"action":"rest"}']
        first = self.wake(step=(1, 3))
        self.assertEqual((first["status"], first["request_count"]), ("completed", 1))  # Only the choice.
        self.wake(step=(2, 3))
        self.wake(step=(3, 3))
        self.assertIn("(empty", self.pages["tempest"][0])
        for page in self.pages["tempest"][1:]:  # Every later move, in this wake and the next.
            self.assertIn("Breadth narrowed before the drop.", page)
        self.choices["siren"] = ['{"action":"rest"}']
        self.wake("siren")
        self.assertNotIn("Breadth narrowed", self.pages["siren"][0])

    def test_composting_writes_one_compost_note_without_a_second_request(self):
        self.choices["tempest"] = ['{"action":"rest","remember":"first"}', '{"action":"rest","remember":"second"}',
                                   '{"action":"compost_notebook","remember":"fresh start"}', '{"action":"rest"}']
        for _ in range(3):
            job = self.wake()
        self.assertEqual((job["status"], job["action"], job["request_count"]), ("completed", "compost_notebook", 1))
        note_id = job["record_refs"][0]["id"]
        compost = CompostStore(self.store.safe_run_file(self.day, "memory/tempest.sqlite3"), "tempest")
        note = compost.get_note(note_id)
        self.assertEqual((note["content"], note["note_kind"]), ("first\nsecond", "compost"))
        self.assertEqual([line["content"] for line in self.book().page("tempest")[0]], ["fresh start"])
        self.wake()
        self.assertIn("fresh start", self.pages["tempest"][-1])
        self.assertNotIn("- [tempest-r1] first", self.pages["tempest"][-1])


if __name__ == "__main__":
    unittest.main()
