"""Offline context contract: no stores, files, network or provider calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
from uuid import uuid4

from core.usage.context import current_usage_context, usage_scope


class UsageContextTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(current_usage_context(), {"activity": "unattributed", "wake_id": None})

    def test_default_snapshot_is_a_copy(self):
        snapshot = current_usage_context()
        snapshot["activity"] = "changed"
        self.assertEqual(current_usage_context()["activity"], "unattributed")

    def test_nested_activity_preserves_wake(self):
        wake = str(uuid4())
        with usage_scope("wake", wake):
            with usage_scope("choose_action"):
                self.assertEqual(current_usage_context(), {"activity": "choose_action", "wake_id": wake})
            self.assertEqual(current_usage_context(), {"activity": "wake", "wake_id": wake})

    def test_nested_wake_is_restored_on_error(self):
        with usage_scope("outer", "wake-1"):
            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                with usage_scope("inner", "wake-2"):
                    raise RuntimeError("operation failed")
            self.assertEqual(current_usage_context(), {"activity": "outer", "wake_id": "wake-1"})

    def test_valid_boundary_labels(self):
        with usage_scope("a" * 80, "x" * 128):
            self.assertEqual(current_usage_context()["activity"], "a" * 80)
        with usage_scope("research.deep:one-two_3"):
            self.assertEqual(current_usage_context()["wake_id"], None)

    def test_invalid_activity_and_wake_do_not_change_context(self):
        with usage_scope("outer", "wake"):
            for activity in (None, True, 123, "", "a" * 81, "two words", "secret\n", "../../bad", "a/b"):
                with self.subTest(activity=activity), self.assertRaises(ValueError):
                    with usage_scope(activity):
                        self.fail("invalid scope entered")
            for wake in (True, 123, "", "x" * 129, "a/b", "a b", "\n"):
                with self.subTest(wake=wake), self.assertRaises(ValueError):
                    with usage_scope("inner", wake):
                        self.fail("invalid scope entered")
            self.assertEqual(current_usage_context(), {"activity": "outer", "wake_id": "wake"})

    def test_scope_performs_no_file_or_network_io(self):
        with mock.patch("builtins.open", side_effect=AssertionError("file IO")), \
             mock.patch("pathlib.Path.mkdir", side_effect=AssertionError("directory IO")), \
             mock.patch("socket.socket", side_effect=AssertionError("network IO")), \
             mock.patch("sqlite3.connect", side_effect=AssertionError("DB IO")):
            with usage_scope("research", "wake-123"):
                self.assertEqual(current_usage_context()["activity"], "research")

    def test_threads_are_isolated(self):
        def worker(number):
            initial = current_usage_context()
            with usage_scope(f"thread-{number}", f"wake-{number}"):
                inner = current_usage_context()
            return initial, inner, current_usage_context()
        with usage_scope("parent", "parent-wake"):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(worker, range(12)))
            self.assertEqual(current_usage_context()["activity"], "parent")
        for index, (initial, inner, final) in enumerate(results):
            self.assertEqual(initial, {"activity": "unattributed", "wake_id": None})
            self.assertEqual(inner, {"activity": f"thread-{index}", "wake_id": f"wake-{index}"})
            self.assertEqual(final, initial)

    def test_async_tasks_inherit_but_do_not_cross_contaminate(self):
        async def worker(number):
            inherited = current_usage_context()
            with usage_scope(f"task-{number}"):
                await asyncio.sleep(0)
                inner = current_usage_context()
            return inherited, inner, current_usage_context()
        async def run():
            with usage_scope("parent", "wake"):
                result = await asyncio.gather(*(worker(number) for number in range(20)))
                self.assertEqual(current_usage_context(), {"activity": "parent", "wake_id": "wake"})
                return result
        for index, (initial, inner, final) in enumerate(asyncio.run(run())):
            self.assertEqual(initial, {"activity": "parent", "wake_id": "wake"})
            self.assertEqual(inner, {"activity": f"task-{index}", "wake_id": "wake"})
            self.assertEqual(final, initial)

    def test_import_context_does_not_import_store_or_data_dir(self):
        script = """
import os, socket, sqlite3
from unittest import mock
with mock.patch('os.mkdir', side_effect=AssertionError('directory IO')), mock.patch('sqlite3.connect', side_effect=AssertionError('database IO')), mock.patch('socket.socket', side_effect=AssertionError('network IO')):
    from core.usage.context import usage_scope, current_usage_context
    with usage_scope('test'):
        assert current_usage_context()['activity'] == 'test'
import sys
assert 'core.data_dir' not in sys.modules
assert 'core.usage.store' not in sys.modules
"""
        result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
