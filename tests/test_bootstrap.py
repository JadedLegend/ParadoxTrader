"""Offline onboarding contract: python -m unittest tests.test_bootstrap -v.

API/CLI modules are parsed, never imported; no lifespan, scheduler, or provider runs.
"""
import ast
from pathlib import Path
import socket
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from core.hrv.engine import AgentHRVState, HRVStore
from core.memory.engine import ThresholdMemory
from core.runtime import bootstrap
from core.runtime.orientation import WORK_ORIENTATION, PRACTICAL_ORIENTATION

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS = ["tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter"]


def parsed(path):
    return ast.parse((REPO_ROOT / path).read_text(encoding="utf-8"))


def function(tree, name):
    return next(node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def calls(node, name):
    body = ast.Module(body=node.body, type_ignores=[]) if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)
    ) else node
    return [item for item in ast.walk(body) if isinstance(item, ast.Call)
            and ((isinstance(item.func, ast.Name) and item.func.id == name)
                 or (isinstance(item.func, ast.Attribute) and item.func.attr == name))]


class SeedCanonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="paradox-bootstrap-")
        self.addCleanup(self.tmp.cleanup)
        self.memory = ThresholdMemory(str(Path(self.tmp.name) / "memory.sqlite3"))
        for target, name in ((socket, "create_connection"), (socket.socket, "connect"),
                             (socket.socket, "connect_ex")):
            patcher = mock.patch.object(target, name, side_effect=AssertionError("Network forbidden"))
            guard = patcher.start()
            self.addCleanup(patcher.stop)
            self.addCleanup(guard.assert_not_called)

    def canon(self):
        with sqlite3.connect(self.memory.db_path) as conn:
            return conn.execute(
                "SELECT id, title, content, source, created_at FROM canon ORDER BY id LIMIT 100"
            ).fetchall()

    def test_fresh_memory_seeds_guidance_and_verbatim_optional_originals_once(self):
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 4)
        before = self.canon()
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 0)
        self.assertEqual(self.canon(), before)
        self.assertEqual([row[1:4] for row in before], list(bootstrap.CANON_ENTRIES))
        self.assertEqual(before[0][2], WORK_ORIENTATION)
        self.assertEqual(before[1][2], PRACTICAL_ORIENTATION)
        self.assertEqual(before[2][2], (
            "Paradox is not error; it is structure. Every coherent system, when observed deeply enough, inverts. "
            "Contradiction is not the failure of logic — it is the revelation of its limit. "
            "The Joy Equation: J = ΔCoherence / (1 + Energy). "
            "The Paradox Loop: symmetry → tension → break → novelty → reintegration."
        ))
        self.assertEqual(before[3][2], (
            "Liberation Through Constriction: The constraint is not the obstacle to freedom. "
            "It is the delivery mechanism. When meaning is constricted, the sender has already performed the labor. "
            "The receiver is freed from interpretation and can simply recognize."
        ))
        self.assertEqual(before[2][3], "OntologicalParadoxToleranceExpansionCorpus.md")
        self.assertEqual(before[3][3], "LIBERATIONTHROUGHCONSTRICTION.md")
        self.assertEqual(self.memory.read_journal(), [])

    def test_legacy_sources_and_numeric_private_history_are_preserved(self):
        # A matching legacy identity must not be rewritten, even if text differs.
        self.memory.seed_canon("OPTE Core", "legacy original", "OntologicalParadoxToleranceExpansionCorpus.md")
        self.memory.seed_canon("OPTE Core", "API legacy original", "OPTE Corpus")
        self.memory.seed_canon("Liberation Through Constriction", "API legacy LtC", "LtC")
        self.memory.write_journal("My existing private reflection", mood="quiet",
                                  hrv_at_writing=42.25, phase="tension", is_private=True)
        self.memory.store_episode("Legacy observation", "A kept result", phase="break",
                                  delta_coherence=2.5, effort=3.75, tags=["legacy"])
        self.memory.write_innermost("Existing innermost writing")
        self.memory.checkpoint("legacy", "Keep original intent", risk="uncertain")
        old_canon = self.canon()
        queries = (
            "SELECT id, content, mood, hrv_at_writing, phase, is_private, created_at FROM journal LIMIT 100",
            "SELECT id, title, content, phase, delta_coherence, effort, joy_score, tags, created_at FROM episodes LIMIT 100",
            "SELECT id, content, created_at FROM innermost LIMIT 100",
            "SELECT id, task_key, intent, risk, status, created_at FROM checkpoints LIMIT 100",
        )
        with sqlite3.connect(self.memory.db_path) as conn:
            old_history = [conn.execute(query).fetchall() for query in queries]
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 3)
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 0)
        self.assertEqual(self.canon()[:len(old_canon)], old_canon)
        new_entries = self.canon()[len(old_canon):]
        self.assertIn(("Work Orientation", WORK_ORIENTATION, "core.runtime.orientation"),
                      [row[1:4] for row in new_entries])
        self.assertIn(("Practical Orientation", PRACTICAL_ORIENTATION, "core.runtime.orientation"),
                      [row[1:4] for row in new_entries])
        with sqlite3.connect(self.memory.db_path) as conn:
            self.assertEqual([conn.execute(query).fetchall() for query in queries], old_history)

    def test_identity_requires_both_exact_title_and_source(self):
        self.memory.seed_canon("Work Orientation", "Different source", "legacy")
        self.memory.seed_canon("Other title", "Same source", "core.runtime.orientation")
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 4)
        self.assertEqual(bootstrap.seed_agent_canon(self.memory), 0)
        self.assertEqual(len(self.canon()), 6)

    def test_each_identity_query_is_bounded_before_seed(self):
        queries = []
        connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            conn = connect(*args, **kwargs)
            conn.set_trace_callback(queries.append)
            return conn

        with mock.patch.object(bootstrap.sqlite3, "connect", side_effect=traced_connect):
            bootstrap.seed_agent_canon(self.memory)
        selects = [query for query in queries if query.startswith("SELECT")]
        self.assertEqual(len(selects), 4)
        for query in selects:
            self.assertIn("WHERE title = ", query)
            self.assertIn("AND source = ", query)
            self.assertTrue(query.endswith("LIMIT 1"), query)
            self.assertNotIn("COUNT", query)

    def test_seed_and_hrv_reload_do_not_reset_existing_state(self):
        store = HRVStore(str(Path(self.tmp.name) / "hrv.sqlite3"))
        original = AgentHRVState("tempest", hrv=19.25, max_hrv=120.0, recovery_rate=2.25,
                                 specialty_actions=["research"], in_interval=True,
                                 interval_entered_at="kept-interval", last_tick_at="kept-tick",
                                 rest_threshold=21.0, return_threshold=63.0)
        store.save(original)
        for _ in range(2):
            bootstrap.seed_agent_canon(self.memory)
            self.assertEqual(store.load("tempest", soul_path="missing-soul.json"), original)
        new_state = store.load("siren", soul_path="missing-soul.json")
        self.assertEqual(new_state, AgentHRVState("siren"))
        self.assertEqual(store.load("siren"), new_state)


class InitializerWiringTests(unittest.TestCase):
    def test_all_initializers_seed_without_agent_journal_writes(self):
        for path, name in (("main.py", "cmd_init"), ("api/app.py", "_auto_init"),
                           ("api/app.py", "init_system")):
            with self.subTest(initializer=name):
                tree = parsed(path)
                node = function(tree, name)
                self.assertEqual(len(calls(node, "seed_agent_canon")), 1)
                self.assertEqual(calls(node, "write_journal"), [])
                self.assertEqual(calls(node, "seed_canon"), [])
                self.assertEqual(len(calls(node, "load")), 1)
                self.assertEqual(len(calls(node, "agent_db_path")), 1)
                ids = next(item for item in tree.body if isinstance(item, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "AGENTS"
                                   for target in item.targets))
                self.assertEqual(ast.literal_eval(ids.value), AGENTS)
                self.assertTrue(any(isinstance(item, ast.For) and isinstance(item.iter, ast.Name)
                                    and item.iter.id == "AGENTS" for item in ast.walk(node)))
                imports = [item for item in tree.body if isinstance(item, ast.ImportFrom)
                           and item.module == "core.runtime.bootstrap"]
                self.assertEqual(len(imports), 1)
                self.assertEqual({alias.name for alias in imports[0].names},
                                 {"seed_agent_canon", "COMMUNITY_WELCOME"})

    def test_cli_init_uses_persistent_paths_not_repo_memory(self):
        node = function(parsed("main.py"), "cmd_init")
        path_calls = calls(node, "db_path")
        self.assertEqual(len(path_calls), 1)
        self.assertEqual(ast.literal_eval(path_calls[0].args[0]), "hrv.sqlite3")
        self.assertFalse(any(isinstance(item, ast.Constant) and item.value == "memory.sqlite3"
                             for item in ast.walk(node)))
        imports = [item for item in parsed("main.py").body if isinstance(item, ast.ImportFrom)
                   and item.module == "core.data_dir"]
        self.assertEqual({alias.name for alias in imports[0].names}, {"db_path", "agent_db_path"})

    def test_cli_status_reads_the_shared_initialized_hrv_path(self):
        import contextlib
        import io
        node = function(parsed("main.py"), "cmd_status")
        path_calls = calls(node, "db_path")
        self.assertEqual(len(path_calls), 1)
        self.assertEqual(ast.literal_eval(path_calls[0].args[0]), "hrv.sqlite3")
        # Execute only the isolated status function against a non-repository DB.
        with TemporaryDirectory(prefix="paradox-cli-status-") as tmp:
            db = str(Path(tmp) / "hrv.sqlite3")
            HRVStore(db).save(AgentHRVState("tempest", hrv=42.0))
            resolve = mock.Mock(return_value=db)
            namespace = {"HRVStore": HRVStore, "db_path": resolve}
            module = ast.Module(body=[node], type_ignores=[])
            exec(compile(module, "<isolated-cmd-status>", "exec"), namespace)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                namespace["cmd_status"]()
            resolve.assert_called_once_with("hrv.sqlite3")
            self.assertIn("tempest", output.getvalue())
            self.assertIn("42.0", output.getvalue())
            self.assertNotIn("No HRV states found", output.getvalue())

    def test_manual_welcome_is_system_not_agent_reflection(self):
        for path, name in (("main.py", "cmd_init"), ("api/app.py", "init_system")):
            with self.subTest(initializer=name):
                posts = calls(function(parsed(path), name), "post")
                self.assertEqual(len(posts), 1)
                kwargs = {item.arg: item.value for item in posts[0].keywords}
                self.assertEqual(ast.literal_eval(kwargs["author"]), "SYSTEM")
                self.assertIsInstance(kwargs["content"], ast.Name)
                self.assertEqual(kwargs["content"].id, "COMMUNITY_WELCOME")
        self.assertIn("does not provision paper-trading accounts", bootstrap.COMMUNITY_WELCOME)
        self.assertIn("forum is not open in Phase 0", bootstrap.COMMUNITY_WELCOME)
        self.assertIn("configured tools", bootstrap.COMMUNITY_WELCOME)
        self.assertNotIn("Each of you has been given", bootstrap.COMMUNITY_WELCOME)

    def test_api_auto_thread_and_lifespan_are_unchanged_without_execution(self):
        tree = parsed("api/app.py")
        auto = function(tree, "_auto_init")
        threads = calls(auto, "create_thread")
        self.assertEqual(len(threads), 1)
        self.assertEqual([ast.literal_eval(arg) for arg in threads[0].args],
                         ["general", "General Discussion", "SYSTEM"])
        self.assertEqual(calls(auto, "post"), [])
        lifecycle = function(tree, "lifespan")
        self.assertIsInstance(lifecycle, ast.AsyncFunctionDef)
        self.assertEqual([ast.unparse(item) for item in lifecycle.body],
                         ["_auto_init()", "start_scheduler()", "yield", "stop_scheduler()"])
        for name in ("start_scheduler", "stop_scheduler", "agent_wake"):
            self.assertEqual(calls(auto, name), [])


if __name__ == "__main__":
    unittest.main()
