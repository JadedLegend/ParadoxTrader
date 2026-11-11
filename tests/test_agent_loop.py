"""Offline wake/action contract: python -m unittest tests.test_agent_loop -v."""
import contextlib
import json
import os
from pathlib import Path
import random
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest import mock


TRACING_ENV = (
    "LANGCHAIN_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_TRACING",
    "LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING_V2",
)


def isolated_environment(stack, data_dir):
    stack.enter_context(mock.patch.dict(os.environ, {"DATA_DIR": data_dir}))
    for key in TRACING_ENV:
        os.environ.pop(key, None)
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"


def block_network(stack):
    """Block both direct sockets and requests, including during project import."""
    guards = [stack.enter_context(mock.patch.object(
        target, name, side_effect=AssertionError("Network forbidden in offline tests")
    )) for target, name in (
        (socket.socket, "connect"), (socket.socket, "connect_ex"),
        (socket, "create_connection"),
    )]
    try:
        import requests
    except ImportError:
        pass
    else:
        guards.append(stack.enter_context(mock.patch.object(
            requests.sessions.Session, "request",
            side_effect=AssertionError("HTTP forbidden in offline tests"),
        )))
    return guards


# DATA_DIR is resolved at module import by several stores. Never import the
# project before installing a temporary directory and disabling tracing.
_IMPORT_DATA = TemporaryDirectory(prefix="paradox-import-")
with contextlib.ExitStack() as _imports:
    isolated_environment(_imports, _IMPORT_DATA.name)
    _import_guards = block_network(_imports)
    from core.runtime import agent_loop as loop, config
    from core.trading import alpaca, council
    from core.hrv.engine import AgentHRVState, HRVStore
    from core.memory.engine import ThresholdMemory
    from core.forum.store import ForumStore
    from core.messaging.store import MessagingStore
    from core import data_dir
    for _guard in _import_guards:
        _guard.assert_not_called()


def tearDownModule():
    _IMPORT_DATA.cleanup()


MENU = [
    {"action": "monitor", "label": "Monitor", "hrv_cost": 1.0},
    {"action": "rest", "label": "Rest", "hrv_cost": -1.5},
]


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(TemporaryDirectory(prefix="paradox-test-"))
        isolated_environment(self.stack, self.tmp)
        self.network_guards = block_network(self.stack)
        for guard in self.network_guards:
            self.addCleanup(guard.assert_not_called)
        self.patch(data_dir, "DATA_DIR", Path(self.tmp))
        self.identities = {p: p.read_bytes() for p in (loop.REPO_ROOT / "agents").glob("*/*.json")}
        self.addCleanup(self.assert_identities_unchanged)
        self.patch(loop, "save_living", side_effect=AssertionError("Identity writes forbidden"))
        self.hrv = HRVStore(str(Path(self.tmp) / "hrv.sqlite3"))
        self.forum = ForumStore(str(Path(self.tmp) / "forum.sqlite3"))
        self.messages = MessagingStore(str(Path(self.tmp) / "messages.sqlite3"))
        self.memories = {}
        self.patch(loop, "get_agent_memory", side_effect=self.memory)
        self.patch(loop, "get_hrv_store", return_value=self.hrv)
        self.patch(loop, "ForumStore", return_value=self.forum)
        self.patch(loop, "MessagingStore", return_value=self.messages)
        self.llm = self.patch(loop, "call_llm", return_value="observed offline test")
        self.creds = self.patch(config, "get_alpaca_creds", return_value={"api_key": "", "api_secret": ""})
        self.broker = self.patch(alpaca, "AlpacaClient", side_effect=AssertionError("Unexpected broker construction"))
        for module, name in ((alpaca, "submit_trade"), (council, "submit_trade"),
                             (council, "run_council_deliberation")):
            guard = self.patch(module, name, side_effect=AssertionError("Trading forbidden"))
            self.addCleanup(guard.assert_not_called)
        rng_state = random.getstate()
        self.addCleanup(random.setstate, rng_state)

    def patch(self, target, name, *args, **kwargs):
        return self.stack.enter_context(mock.patch.object(target, name, *args, **kwargs))

    def assert_identities_unchanged(self):
        for path, original in self.identities.items():
            self.assertEqual(path.read_bytes(), original, str(path))

    def memory(self, agent_id="tempest"):
        if agent_id not in self.memories:
            self.memories[agent_id] = ThresholdMemory(str(Path(self.tmp) / agent_id / "memory.sqlite3"))
        return self.memories[agent_id]

    def state(self, agent_id="tempest", **kwargs):
        return AgentHRVState(agent_id, specialty_actions=loop.load_soul(agent_id).get("hrv_specialties", []), **kwargs)

    def execute(self, action, phase=3, agent_id="tempest", **kwargs):
        return loop.execute_action(agent_id, action, loop.load_soul(agent_id), loop.load_living(agent_id),
                                   self.memory(agent_id), self.forum, self.messages, self.state(agent_id), phase, **kwargs)


class ActionMenuTests(OfflineCase):
    def test_choices_are_unique_affordable_and_use_actual_costs(self):
        for aid in loop.AGENTS:
            for phase in (0, 1, 3):
                for energy in (0.0, 1.0, 3.0, 100.0):
                    with self.subTest(agent=aid, phase=phase, energy=energy):
                        state = self.state(aid, hrv=energy)
                        actions = loop.get_available_actions(aid, phase, state)
                        names = [a["action"] for a in actions]
                        self.assertLessEqual(len(actions), 5)
                        self.assertEqual(len(names), len(set(names)))
                        self.assertIn("rest", names)
                        for action in actions:
                            self.assertTrue(state.can_perform(action["action"]))
                            expected = (-min(state.recovery_rate, max(0.0, state.max_hrv - state.hrv))
                                        if action["action"] == "rest" else state.get_action_cost(action["action"]))
                            self.assertEqual(action["hrv_cost"], expected)

    def test_oracle_rest_menu_matches_actual_recovery_including_cap(self):
        self.llm.return_value = "Resting."
        for energy in (20.0, 99.5, 100.0):
            with self.subTest(energy=energy):
                state = self.state("oracle", hrv=energy)
                self.assertIn("rest", state.specialty_actions)
                rest = next(a for a in loop.get_available_actions("oracle", 0, state) if a["action"] == "rest")
                expected = min(state.recovery_rate, max(0.0, state.max_hrv - energy))
                result = loop.execute_action("oracle", "rest", loop.load_soul("oracle"), loop.load_living("oracle"),
                                             self.memory("oracle"), self.forum, self.messages, state, 0)
                self.assertEqual(rest["hrv_cost"], -expected)
                self.assertEqual(result["hrv"]["hrv_recovered"], expected)
                self.assertEqual(rest["hrv_cost"], energy - state.hrv)

    def test_sampling_reaches_eligible_pool_including_trade_and_review(self):
        for aid in loop.AGENTS:
            for phase in (0, 1, 3):
                seen = set()
                for seed in range(80):
                    random.seed(seed)
                    seen.update(a["action"] for a in loop.get_available_actions(aid, phase, self.state(aid)))
                expected = {"monitor", "research", "roam", "rest", "review_position", "propose_trade"}
                specialties = set(loop.load_soul(aid).get("hrv_specialties", []))
                specialized = {s for s in specialties if s.startswith(("analyze_", "roam_"))}
                if not any(s.startswith("analyze_") for s in specialized):
                    expected.add("analyze")
                if any(s.startswith("roam_") for s in specialized):
                    expected.discard("roam")
                expected.update(specialized - {"analyze_consensus"})
                if phase >= 1:
                    expected.update(("forum_post", "direct_message"))
                if phase >= 3:
                    expected.add("analyze_consensus")
                with self.subTest(agent=aid, phase=phase):
                    self.assertTrue(expected <= seen, f"Unreachable choices: {expected - seen}")

    def test_phase_zero_excludes_communications_and_consensus_for_all_agents(self):
        for aid in loop.AGENTS:
            for seed in range(40):
                random.seed(seed)
                names = {a["action"] for a in loop.get_available_actions(aid, 0, self.state(aid))}
                self.assertFalse(names & {"forum_post", "direct_message", "analyze_consensus"}, aid)


class PositionSnapshotTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.broker.side_effect = None

    def configured(self):
        # Dummy markers only; no environment/config secrets are read.
        self.creds.return_value = {"api_key": "offline-key-marker", "api_secret": "offline-secret-marker"}

    def assert_snapshot(self, entry, status, positions):
        self.assertIsInstance(entry, dict)
        self.assertEqual(entry["status"], status)
        self.assertEqual(entry["positions"], positions)
        self.assertIsInstance(entry["positions"], list)
        from datetime import datetime
        self.assertIsNotNone(datetime.fromisoformat(entry["observed_at"]).tzinfo)
        rendered = json.dumps(entry)
        self.assertNotIn("offline-key-marker", rendered)
        self.assertNotIn("offline-secret-marker", rendered)

    def test_missing_credentials_are_not_configured_not_empty_success(self):
        for creds in ({}, {"api_key": "", "api_secret": ""}, {"api_key": "offline-key-marker"}):
            with self.subTest(fields=sorted(creds)):
                self.creds.return_value = creds
                result = loop.get_cross_agent_positions(["tempest"])
                self.assert_snapshot(result["tempest"], "not_configured", [])
        self.broker.assert_not_called()

    def test_empty_positions_are_confirmed_success_and_client_uses_agent_id(self):
        self.configured()
        self.broker.return_value.get_positions.return_value = []
        result = loop.get_cross_agent_positions(["tempest"])
        self.creds.assert_called_once_with("tempest")
        self.broker.assert_called_once_with("tempest")
        self.assert_snapshot(result["tempest"], "ok", [])

    def test_success_preserves_positions(self):
        self.configured()
        positions = [{"symbol": "OFFLINE", "qty": "2"}]
        self.broker.return_value.get_positions.return_value = positions
        self.assert_snapshot(loop.get_cross_agent_positions(["siren"])["siren"], "ok", positions)

    def test_exception_is_error_and_does_not_log_raw_message(self):
        self.configured()
        marker = "private-broker-exception-marker"
        self.broker.return_value.get_positions.side_effect = RuntimeError(marker)
        with self.assertLogs(level="DEBUG") as logs:
            import logging
            logging.getLogger(__name__).debug("offline log capture active")
            entry = loop.get_cross_agent_positions(["tempest"])["tempest"]
        self.assert_snapshot(entry, "error", [])
        self.assertNotIn(marker, json.dumps(entry) + "\n".join(logs.output))

    def test_malformed_payload_is_error(self):
        self.configured()
        for payload in (None, {"error": "unavailable"}, "invalid", [None], ["invalid"]):
            with self.subTest(payload_type=type(payload).__name__):
                self.broker.return_value.get_positions.return_value = payload
                self.assert_snapshot(loop.get_cross_agent_positions(["tempest"])["tempest"], "error", [])

    def test_optional_targets_default_to_all_and_explicit_empty_means_none(self):
        self.assertEqual(set(loop.get_cross_agent_positions()), set(loop.AGENTS))
        self.creds.reset_mock()
        self.assertEqual(loop.get_cross_agent_positions([]), {})
        self.creds.assert_not_called()
        self.assertEqual(set(loop.get_cross_agent_positions(["shadow", "oracle"])), {"shadow", "oracle"})


class WakeTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.menu = self.patch(loop, "get_available_actions", return_value=MENU)
        self.positions = self.patch(loop, "get_cross_agent_positions", side_effect=self.snapshots)

    @staticmethod
    def snapshots(agent_ids=None):
        return {aid: {"status": "ok", "positions": [{"symbol": "OWN_ONLY" if aid == "tempest" else "PEER_ONLY", "qty": "1"}],
                      "observed_at": "2026-01-01T00:00:00+00:00"} for aid in (loop.AGENTS if agent_ids is None else agent_ids)}

    def targets(self):
        args, kwargs = self.positions.call_args
        return args[0] if args else kwargs.get("agent_ids", loop.AGENTS)

    def test_all_seven_phase_zero_wakes_persist_monitor_episode_and_hrv(self):
        self.assertEqual(len(loop.AGENTS), 7)
        for aid in loop.AGENTS:
            with self.subTest(agent=aid):
                self.positions.reset_mock()
                self.llm.side_effect = ["1", "observed offline test"]
                result = loop.agent_wake(aid, phase=0)
                self.assertEqual(result["action"], "monitor")
                self.assertEqual(list(self.targets()), [aid])
                fresh_memory = ThresholdMemory(self.memory(aid).db_path)
                self.assertEqual(fresh_memory.get_recent_episodes()[0]["content"], "observed offline test")
                stored = HRVStore(self.hrv.db_path).load(aid)
                self.assertEqual(stored.hrv, 100.0 - self.state(aid).get_action_cost("monitor"))
                self.assertIsNotNone(stored.last_tick_at)
        self.broker.assert_not_called()

    def test_phase_one_context_reaches_actual_action_user_message(self):
        self.messages.send("user", "tempest", "UNREAD_DM_SENTINEL")
        self.llm.side_effect = ["1", "observed offline test"]
        loop.agent_wake("tempest", phase=1)
        self.assertEqual(set(self.targets()), set(loop.AGENTS))
        actual_user = "\n".join(m["content"] for m in self.llm.call_args.args[1] if m["role"] == "user")
        for sentinel in ("UNREAD_DM_SENTINEL", "OWN_ONLY", "PEER_ONLY"):
            self.assertIn(sentinel, actual_user)

    def test_phase_zero_actual_action_context_has_no_peer_holdings(self):
        self.llm.side_effect = ["1", "observed offline test"]
        loop.agent_wake("tempest", phase=0)
        actual_user = json.dumps(self.llm.call_args.args[1])
        self.assertIn("OWN_ONLY", actual_user)
        self.assertNotIn("PEER_ONLY", actual_user)

    def test_phase_zero_older_user_message_survives_newer_peer_inbox_limit(self):
        user_id = self.messages.send("user", "tempest", "OLDER_USER_DM_SENTINEL")
        peers = {self.messages.send("siren", "tempest", f"PRIVATE_PEER_DM_SENTINEL_{i}") for i in range(5)}
        self.assertEqual({m["id"] for m in self.messages.get_inbox("tempest", True, 5)}, peers)
        self.assertEqual([m["id"] for m in self.messages.get_inbox("tempest", True, 5, "user")], [user_id])
        mark = self.patch(self.messages, "mark_read", wraps=self.messages.mark_read)
        self.llm.side_effect = ["1", "observed offline test"]
        result = loop.agent_wake("tempest", phase=0)
        self.assertEqual(result["action"], "monitor")
        self.assertEqual(self.llm.call_count, 2)
        for call in self.llm.call_args_list:
            actual_user = "\n".join(m["content"] for m in call.args[1] if m["role"] == "user")
            self.assertIn("OLDER_USER_DM_SENTINEL", actual_user)
            self.assertNotIn("PRIVATE_PEER_DM_SENTINEL", json.dumps(call.args) + json.dumps(call.kwargs))
        mark.assert_called_once_with([user_id])
        self.assertEqual({m["id"] for m in self.messages.get_inbox("tempest", unread_only=True)}, peers)
        self.assertTrue(self.messages.get_inbox("tempest", sender="user")[0]["read"])

    def test_interval_short_circuits_before_inbox_positions_and_picker(self):
        self.hrv.save(self.state(hrv=20.0, in_interval=True))
        inbox = self.patch(self.messages, "get_inbox", side_effect=AssertionError("Interval must not read messages"))
        self.llm.return_value = "Resting."
        result = loop.agent_wake("tempest", phase=3)
        self.assertEqual(result["wake"], "interval")
        self.assertEqual(result["result"]["action"], "rest")
        self.assertEqual(self.hrv.load("tempest").hrv, 21.5)
        inbox.assert_not_called()
        self.positions.assert_not_called()
        self.menu.assert_not_called()
        self.assertEqual(self.llm.call_count, 1)

    def test_messages_acknowledged_only_after_action_and_hrv_save(self):
        self.messages.send("user", "tempest", "pending until durable success")
        original_save, original_mark = self.hrv.save, self.messages.mark_read
        saved = []
        def save(state):
            self.assertEqual(self.messages.unread_count("tempest"), 1)
            self.assertTrue(self.memory().get_recent_episodes())
            original_save(state)
            saved.append(True)
        def mark(ids):
            self.assertTrue(saved)
            original_mark(ids)
        # Seed first so the assertion observes the post-action save, not load's initial insert.
        self.hrv.save(self.state())
        self.patch(self.hrv, "save", side_effect=save)
        self.patch(self.messages, "mark_read", side_effect=mark)
        self.llm.side_effect = ["1", "observed offline test"]
        loop.agent_wake("tempest", phase=1)
        self.assertEqual(self.messages.unread_count("tempest"), 0)

    def test_choice_llm_failure_keeps_messages_unread(self):
        self.messages.send("user", "tempest", "retry after picker failure")
        self.llm.side_effect = RuntimeError("offline picker failure")
        self.assert_failed_wake_leaves_message()

    def test_execution_failure_keeps_messages_unread(self):
        self.messages.send("user", "tempest", "retry after action failure")
        self.llm.side_effect = ["1", RuntimeError("offline execution failure")]
        self.assert_failed_wake_leaves_message()

    def test_hrv_save_failure_keeps_messages_unread(self):
        self.messages.send("user", "tempest", "retry after save failure")
        self.hrv.save(self.state())
        self.patch(self.hrv, "save", side_effect=RuntimeError("offline save failure"))
        self.llm.side_effect = ["1", "observed offline test"]
        self.assert_failed_wake_leaves_message()

    def assert_failed_wake_leaves_message(self):
        try:
            loop.agent_wake("tempest", phase=1)
        except RuntimeError:
            pass  # Returning an explicit failure or propagating it are both safe.
        self.assertEqual(self.messages.unread_count("tempest"), 1)

    def test_invalid_picker_responses_explicitly_fall_back_to_rest(self):
        for response in ("", "0", "3", "10", "-1", "1 because", "choice 1", "1\n2", "１"):
            with self.subTest(response=response):
                self.hrv.save(self.state())
                self.llm.side_effect = [response, "Resting."]
                result = loop.agent_wake("tempest", phase=0)
                self.assertEqual(result["action"], "rest")
                self.assertEqual(result["choice_status"], "fallback_rest")


class ActionExecutionTests(OfflineCase):
    def test_unknown_action_is_explicitly_unsupported_not_monitor(self):
        result = self.execute("not_a_real_action")
        self.assertEqual(result["status"], "unsupported_action")
        self.llm.assert_not_called()
        self.assertEqual(self.memory().get_recent_episodes(), [])

    def test_consensus_is_explicit_forum_analysis_without_orders_or_council(self):
        self.forum.post("siren", "FORUM_ANALYSIS_SENTINEL")
        for aid in loop.AGENTS:
            with self.subTest(agent=aid):
                result = self.execute("analyze_consensus", agent_id=aid)
                self.assertEqual(result["action"], "analyze_consensus")
                prompt = json.dumps(self.llm.call_args.args[1]) + self.llm.call_args.kwargs.get("system_prompt", "")
                self.assertIn("FORUM_ANALYSIS_SENTINEL", prompt)
        self.broker.assert_not_called()

    def test_private_journal_does_not_copy_content_to_episodes_or_result(self):
        private = "PRIVATE_JOURNAL_SENTINEL not an episode"
        self.llm.return_value = private
        result = self.execute("journal")
        self.assertEqual(result["action"], "journal")
        self.assertIs(result["journal_written"], True)
        self.assertNotIn(private, json.dumps(result))
        self.assertNotIn(private, json.dumps(self.memory().get_recent_episodes()))
        self.assertEqual(self.memory().read_journal()[0]["content"], private)
        self.assertTrue(self.memory().read_journal()[0]["private"])

    def test_history_actions_keep_wake_context_and_records_in_user_messages(self):
        self.memory().store_episode("EPISODE_TITLE_SENTINEL", "EPISODE_CONTENT_SENTINEL", phase="symmetry")
        self.forum.post("siren", "FORUM_HISTORY_SENTINEL")
        context = {"messages": "WAKE_DM_SENTINEL", "positions": "WAKE_POSITIONS_SENTINEL"}
        for action in ("journal", "forum_post", "propose_trade"):
            with self.subTest(action=action):
                before = self.memory().get_recent_episodes()
                response = f"GENERATED_{action}_SENTINEL"
                self.llm.reset_mock()
                self.llm.return_value = response
                result = self.execute(action, context=context)
                self.assertEqual(result["action"], action)
                self.llm.assert_called_once()
                call = self.llm.call_args
                actual_user = "\n".join(m["content"] for m in call.args[1] if m["role"] == "user")
                system = call.kwargs.get("system_prompt", "") + "\n".join(
                    m["content"] for m in call.args[1] if m["role"] == "system")
                history = ["FORUM_HISTORY_SENTINEL"] if action == "forum_post" else ["EPISODE_TITLE_SENTINEL"]
                if action == "propose_trade":
                    history.append("EPISODE_CONTENT_SENTINEL")
                for marker in [*context.values(), *history]:
                    self.assertIn(marker, actual_user)
                    self.assertNotIn(marker, system)
                after = self.memory().get_recent_episodes()
                if action == "journal":
                    self.assertEqual(after, before)
                    self.assertNotIn(response, json.dumps(result))
                    journal = self.memory().read_journal()[0]
                    self.assertEqual(journal["content"], response)
                    self.assertTrue(journal["private"])
                else:
                    self.assertEqual(len(after), len(before) + 1)
                    episode = next(e for e in after if e["content"] == response)
                    self.assertEqual(episode["title"], "Forum post" if action == "forum_post" else "Trade idea")
                    if action == "forum_post":
                        post = next(p for p in self.forum.get_recent() if p["content"] == response)
                        self.assertEqual(post["author"], "tempest")
                self.assertNotIn("order", result)
                self.broker.assert_not_called()

    def test_execute_action_accepts_and_propagates_context_in_user_call(self):
        self.execute("review_position", context={"messages": "DIRECT_CONTEXT_SENTINEL", "positions": "POSITION_CONTEXT_SENTINEL"})
        actual_user = json.dumps(self.llm.call_args.args[1])
        self.assertIn("DIRECT_CONTEXT_SENTINEL", actual_user)
        self.assertIn("POSITION_CONTEXT_SENTINEL", actual_user)


if __name__ == "__main__":
    unittest.main()
