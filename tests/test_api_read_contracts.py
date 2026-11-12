"""Offline API read contracts: python -m unittest tests.test_api_read_contracts -v.

Compile only selected, undecorated handler definitions from api/app.py. Never
import the FastAPI application, run its lifespan/scheduler, initialize an agent,
or consult real config, credentials, brokers, or providers. Position snapshots
are deterministic helper fixtures; profile JSON is read-only and HRV is mocked.
"""
import ast
import contextlib
import copy
from datetime import datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

# Reuse the wake suite's guarded imports and socket/HTTP fixture style, but not
# OfflineCase.setUp: these handler tests must not construct any database stores.
from tests.test_agent_loop import (
    alpaca, block_network, config, isolated_environment, loop,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = REPO_ROOT / "api" / "app.py"
API_AST = ast.parse(API_SOURCE.read_text(encoding="utf-8"), filename=str(API_SOURCE))
AGENTS = next(
    ast.literal_eval(node.value) for node in API_AST.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "AGENTS" for target in node.targets)
)
OBSERVED_AT = "2026-01-01T00:00:00+00:00"


def extracted_handler(name, namespace):
    """Compile one function with mocked names; skip every app-level statement."""
    function = copy.deepcopy(next(
        node for node in API_AST.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ))
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(API_SOURCE), "exec"), namespace)
    return namespace[name]


def snapshot_fixture():
    """Mix confirmed holdings/empty accounts and unknowns across all agents."""
    result = {}
    for index, agent_id in enumerate(AGENTS):
        status = ("ok", "ok", "error", "not_configured")[index % 4]
        entry = {"status": status, "positions": [], "observed_at": OBSERVED_AT}
        if index % 4 == 0:
            entry["positions"] = [{"symbol": "OFFLINE", "qty": "2"}]
        elif status == "error":
            entry.update(reason="position_lookup_failed", error_type="RuntimeError")
        elif status == "not_configured":
            entry["reason"] = "credentials_not_configured"
        result[agent_id] = entry
    return result


class APIReadContracts(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(TemporaryDirectory(prefix="paradox-api-read-"))
        isolated_environment(self.stack, self.tmp)
        for guard in block_network(self.stack):
            self.addCleanup(guard.assert_not_called)

        # All configuration, credential, broker, model, and initialization paths
        # are hard failures, even for dummy/offline accounts. Only the delegated
        # position helper is mocked; none of its real account lookup is executed.
        for target, names in (
            (config, ("load_config", "get_agent_model", "get_alpaca_creds")),
            (alpaca, ("AlpacaClient",)),
            (loop, ("call_llm", "agent_wake", "HRVStore", "ThresholdMemory",
                    "ForumStore", "MessagingStore")),
        ):
            for name in names:
                guard = self.stack.enter_context(mock.patch.object(
                    target, name, side_effect=AssertionError(f"Forbidden read-contract call: {name}"),
                ))
                self.addCleanup(guard.assert_not_called)

        self.identities = {
            path: path.read_bytes() for path in (REPO_ROOT / "agents").glob("*/*.json")
        }
        self.addCleanup(self.assert_profiles_unchanged)
        self.souls = {
            agent_id: json.loads(self.identities[REPO_ROOT / "agents" / agent_id / "soul.json"])
            for agent_id in AGENTS
        }
        self.living = {
            agent_id: json.loads(self.identities[REPO_ROOT / "agents" / agent_id / "living.json"])
            for agent_id in AGENTS
        }
        self.store = mock.Mock(spec=("get_all_states", "load", "save", "_init_db"))
        self.store.get_all_states.return_value = []
        for name in ("load", "save", "_init_db"):
            guard = getattr(self.store, name)
            guard.side_effect = AssertionError(f"HRV initialization/mutation forbidden: {name}")
            self.addCleanup(guard.assert_not_called)

        self.namespace = {
            "AGENTS": list(AGENTS),
            "get_hrv_store": mock.Mock(return_value=self.store),
            "load_soul": mock.Mock(side_effect=lambda aid: self.souls[aid]),
            "load_living": mock.Mock(side_effect=lambda aid: self.living[aid]),
        }
        for name in ("load_config_yaml", "load_config", "get_agent_model", "get_alpaca_creds",
                     "AlpacaClient", "call_llm", "_auto_init", "init_system", "start_scheduler",
                     "stop_scheduler", "save_config_yaml", "save_living", "agent_wake"):
            guard = mock.Mock(side_effect=AssertionError(f"Forbidden handler call: {name}"))
            self.namespace[name] = guard
            self.addCleanup(guard.assert_not_called)
        self.api_before = sys.modules.get("api.app")
        self.addCleanup(self.assert_api_not_imported)

    def assert_api_not_imported(self):
        self.assertIs(sys.modules.get("api.app"), self.api_before)

    def assert_profiles_unchanged(self):
        for path, original in self.identities.items():
            self.assertEqual(path.read_bytes(), original, str(path))

    def handler(self, name):
        return extracted_handler(name, self.namespace)

    def mock_positions(self, snapshots):
        return self.stack.enter_context(mock.patch.object(
            loop, "get_cross_agent_positions", return_value=snapshots,
        ))

    def test_positions_pass_through_normalized_snapshots_without_account_reads(self):
        snapshots = snapshot_fixture()
        before = copy.deepcopy(snapshots)
        helper = self.mock_positions(snapshots)
        positions = self.handler("get_all_positions")
        result = positions()
        helper.assert_called_once_with(self.namespace["AGENTS"])
        self.assertEqual(result, {"positions": before})
        self.assertIs(result["positions"], snapshots)
        self.assertEqual(snapshots, before)
        self.assertEqual(set(result["positions"]), set(AGENTS))
        for entry in result["positions"].values():
            self.assertIn(entry["status"], ("ok", "error", "not_configured"))
            self.assertIsInstance(entry["positions"], list)
            self.assertEqual(entry["observed_at"], OBSERVED_AT)
            self.assertIsNotNone(datetime.fromisoformat(entry["observed_at"]).tzinfo)
        # Repeat calls remain deterministic and do not add a wrapper timestamp.
        self.assertEqual(positions(), result)
        self.namespace["get_hrv_store"].assert_not_called()
        self.namespace["load_soul"].assert_not_called()
        self.namespace["load_living"].assert_not_called()

    def test_empty_positions_are_confirmed_only_for_ok_status(self):
        snapshots = snapshot_fixture()
        self.mock_positions(snapshots)
        entries = self.handler("get_all_positions")()["positions"]
        for status, agent_id in (("ok", "siren"), ("error", "alchemist"),
                                 ("not_configured", "weaver")):
            with self.subTest(status=status):
                self.assertEqual(entries[agent_id]["positions"], [])
                self.assertEqual(entries[agent_id]["status"], status)
                self.assertEqual(entries[agent_id]["status"] == "ok", status == "ok")
        self.assertEqual(entries["alchemist"]["reason"], "position_lookup_failed")
        self.assertEqual(entries["weaver"]["reason"], "credentials_not_configured")

    def test_positions_pass_safe_error_categories_not_credentials_or_raw_exceptions(self):
        snapshots = snapshot_fixture()
        self.mock_positions(snapshots)
        # These markers would leak if the wrapper tried its old config/broker path.
        self.namespace["load_config_yaml"].side_effect = RuntimeError("private-credential-marker")
        self.namespace["AlpacaClient"].side_effect = RuntimeError("private-broker-exception-marker")
        result = self.handler("get_all_positions")()
        rendered = json.dumps(result)
        self.assertNotIn("private-credential-marker", rendered)
        self.assertNotIn("private-broker-exception-marker", rendered)
        self.assertEqual(result["positions"]["alchemist"]["error_type"], "RuntimeError")

    def test_agents_use_profile_preferences_and_leave_uninitialized_hrv_unknown(self):
        profiles_before = copy.deepcopy((self.souls, self.living))
        result = self.handler("get_all_agents")()
        self.assertEqual(list(result), ["agents"])
        self.assertEqual([entry["agent_id"] for entry in result["agents"]], AGENTS)
        self.store.get_all_states.assert_called_once_with()
        for entry in result["agents"]:
            agent_id = entry["agent_id"]
            with self.subTest(agent=agent_id):
                self.assertEqual(entry["model"], self.souls[agent_id]["model_preference"])
                for field in ("name", "epistemic_role", "core_drive"):
                    self.assertEqual(entry[field], self.souls[agent_id][field])
                for field in ("current_focus", "curiosity_questions"):
                    self.assertEqual(entry[field], self.living[agent_id][field])
                self.assertIsNone(entry["hrv"])
                self.assertIsNone(entry["max_hrv"])
                self.assertEqual(entry["hrv_status"], "not_initialized")
                self.assertIs(entry["in_interval"], False)
        self.assertEqual((self.souls, self.living), profiles_before)
        self.assertEqual(self.namespace["load_soul"].call_count, len(AGENTS))
        self.assertEqual(self.namespace["load_living"].call_count, len(AGENTS))

    def test_agents_read_capacity_and_interval_from_existing_state_including_zero_hrv(self):
        states = [
            SimpleNamespace(agent_id="tempest", hrv=41.234, max_hrv=80.0, in_interval=True),
            SimpleNamespace(agent_id="siren", hrv=0.0, max_hrv=125.0, in_interval=False),
        ]
        before = [vars(state).copy() for state in states]
        self.store.get_all_states.return_value = states
        entries = {entry["agent_id"]: entry for entry in self.handler("get_all_agents")()["agents"]}
        for agent_id, hrv, max_hrv, interval in (
            ("tempest", 41.2, 80.0, True), ("siren", 0.0, 125.0, False),
        ):
            with self.subTest(agent=agent_id):
                self.assertEqual(entries[agent_id]["hrv"], hrv)
                self.assertEqual(entries[agent_id]["max_hrv"], max_hrv)
                self.assertIs(entries[agent_id]["in_interval"], interval)
                self.assertEqual(entries[agent_id]["hrv_status"], "ok")
        self.assertIsNone(entries["shadow"]["max_hrv"])
        self.assertEqual([vars(state) for state in states], before)
        self.store.get_all_states.assert_called_once_with()

    def test_model_preference_wins_and_legacy_model_remains_a_config_free_fallback(self):
        self.souls["tempest"].update(model_preference="offline/preferred", model="offline/legacy")
        self.souls["siren"].pop("model_preference")
        self.souls["siren"]["model"] = "offline/legacy-only"
        self.souls["alchemist"].pop("model_preference")
        self.souls["alchemist"].pop("model", None)
        self.souls["weaver"].update(model_preference=None, model="offline/null-fallback")
        self.souls["oracle"].update(model_preference="", model="offline/empty-fallback")
        entries = {entry["agent_id"]: entry for entry in self.handler("get_all_agents")()["agents"]}
        for agent_id, expected in (
            ("tempest", "offline/preferred"), ("siren", "offline/legacy-only"),
            ("alchemist", ""), ("weaver", "offline/null-fallback"),
            ("oracle", "offline/empty-fallback"),
        ):
            with self.subTest(agent=agent_id):
                self.assertEqual(entries[agent_id]["model"], expected)

    def test_profile_failure_is_bounded_and_does_not_expose_raw_exception(self):
        marker = "private-profile-exception-credential-marker"
        def read_soul(agent_id):
            if agent_id == "tempest":
                raise RuntimeError(marker)
            return self.souls[agent_id]
        self.namespace["load_soul"].side_effect = read_soul
        entries = self.handler("get_all_agents")()["agents"]
        self.assertEqual(entries[0], {"agent_id": "tempest", "error": "profile_unavailable"})
        self.assertNotIn(marker, json.dumps(entries))
        self.assertEqual(len(entries), len(AGENTS))
        self.assertNotIn("error", entries[1])

    def test_queue_route_uses_store_helper_without_name_collision(self):
        records = [{"id": 7, "agent_id": "tempest", "proposal": {
            "symbol": "DEMO", "qty": 2, "side": "buy", "thesis": "Offline fixture only",
        }}]
        queue = mock.Mock(spec=("get_pending",))
        queue.get_pending.return_value = records
        self.namespace["get_trade_queue"] = mock.Mock(return_value=queue)
        result = self.handler("get_pending_trades")()
        self.assertEqual(result, {"trades": records})
        self.namespace["get_trade_queue"].assert_called_once_with()
        queue.get_pending.assert_called_once_with()
        definitions = [node for node in API_AST.body
                       if isinstance(node, ast.FunctionDef) and node.name == "get_trade_queue"]
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].decorator_list, [])


if __name__ == "__main__":
    unittest.main()
