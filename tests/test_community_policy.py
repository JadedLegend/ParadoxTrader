"""Offline contracts: python -m unittest tests.test_community_policy -v.

No API import, scheduler, account, provider, or tracing activation is needed.
"""
import contextlib
import importlib
import json
import os
from pathlib import Path
import runpy
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = {
    "introduction_stage": "settling",
    "available_concepts": ["environment"],
    "forum_open": False,
    "peer_messages_open": False,
    "share_peer_positions": False,
}
GATES = ("forum_open", "peer_messages_open", "share_peer_positions")


class OfflineCommunityCase(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = self.stack.enter_context(TemporaryDirectory(prefix="community-offline-"))
        self.stack.enter_context(mock.patch.dict(os.environ, {
            "DATA_DIR": self.tmp,
            "LANGCHAIN_TRACING_V2": "false",
            "LANGSMITH_TRACING": "false",
            "LANGSMITH_TRACING_V2": "false",
        }, clear=True))
        self.network_guards = []
        for target, attribute in (
            (socket.socket, "connect"), (socket.socket, "connect_ex"),
            (socket, "create_connection"),
        ):
            guard = self.stack.enter_context(mock.patch.object(
                target, attribute, side_effect=AssertionError("Network forbidden")
            ))
            self.network_guards.append(guard)
            self.addCleanup(guard.assert_not_called)
        try:
            import requests
        except ImportError:
            pass
        else:
            guard = self.stack.enter_context(mock.patch.object(
                requests.sessions.Session, "request", side_effect=AssertionError("HTTP forbidden")
            ))
            self.network_guards.append(guard)
            self.addCleanup(guard.assert_not_called)
        paths = [p for filename in ("soul.json", "living.json")
                 for p in (ROOT / "agents").glob(f"*/{filename}")]
        self.original_bytes = {p: p.read_bytes() for p in paths}
        self.assertEqual(len(self.original_bytes), 14)
        self.addCleanup(self.assert_originals_unchanged)
        self.community = importlib.import_module("core.runtime.community")

    def assert_originals_unchanged(self):
        for path, content in self.original_bytes.items():
            self.assertEqual(path.read_bytes(), content, str(path))


class CommunityPolicyTests(OfflineCommunityCase):
    def policy(self, **block):
        return self.community.get_community_policy({"community": block})

    def test_defaults_and_exact_public_keys(self):
        self.assertEqual(self.community.get_community_policy({}), DEFAULT_POLICY)
        self.assertEqual(set(self.policy()), set(DEFAULT_POLICY))
        self.assertEqual(self.policy(untrusted_key="not retained"), DEFAULT_POLICY)

    def test_import_does_not_read_asset_or_config(self):
        config = importlib.import_module("core.runtime.config")
        with mock.patch.object(config, "get_runtime_config", side_effect=AssertionError("Eager config")), \
             mock.patch.object(Path, "read_text", side_effect=AssertionError("Eager asset")):
            namespace = runpy.run_path(self.community.__file__)
            self.assertTrue(callable(namespace["get_community_policy"]))

    def test_none_reads_runtime_lazily_but_supplied_runtime_never_does(self):
        config = importlib.import_module("core.runtime.config")
        with mock.patch.object(config, "get_runtime_config", return_value={
            "community": {"forum_open": True}
        }) as getter:
            self.assertFalse(self.community.get_community_policy({})["forum_open"])
            getter.assert_not_called()
            self.assertTrue(self.community.get_community_policy()["forum_open"])
            getter.assert_called_once_with()

    def test_missing_and_malformed_blocks_fail_closed(self):
        for runtime in (False, True, "runtime", 1, [], {"community": None},
                        {"community": []}, {"community": "yes"},
                        {"community": True}, {"runtime": {"community": {"forum_open": True}}}):
            with self.subTest(runtime=runtime):
                self.assertEqual(self.community.get_community_policy(runtime), DEFAULT_POLICY)

    def test_malformed_gate_values_never_open(self):
        for value in (None, False, 0, 1, 1.0, "true", "True", "yes", [], {}, [True]):
            with self.subTest(value=value):
                result = self.policy(**{gate: value for gate in GATES})
                self.assertTrue(all(result[gate] is False for gate in GATES))

    def test_literal_true_and_gates_are_independent(self):
        for gate in GATES:
            result = self.policy(**{gate: True})
            self.assertEqual(result[gate], True)
            for other in set(GATES) - {gate}:
                self.assertIs(result[other], False)
            self.assertEqual(result["available_concepts"], ["environment"])
            self.assertEqual(result["introduction_stage"], "settling")

    def test_known_stages_do_not_imply_concepts_or_permissions(self):
        for stage in self.community.INTRODUCTION_STAGES:
            result = self.policy(introduction_stage=stage)
            self.assertEqual(result["introduction_stage"], stage)
            self.assertEqual(result["available_concepts"], ["environment"])
            self.assertFalse(any(result[gate] for gate in GATES))
        for stage in (None, True, [], {}, "MARKET", "graduated", "exploring\n"):
            self.assertEqual(self.policy(introduction_stage=stage)["introduction_stage"], "settling")

    def test_concepts_are_explicit_known_bounded_and_deduplicated(self):
        result = self.policy(available_concepts=[
            "options", "options", "inquiry", "unknown", None, True, {}, [],
            "environment", "markets", "paradox",
        ])
        self.assertEqual(result["available_concepts"],
                         ["options", "inquiry", "environment", "markets", "paradox"])
        self.assertEqual(self.policy(available_concepts=[])["available_concepts"], [])
        self.assertEqual(self.policy(available_concepts=["unknown"])["available_concepts"], [])
        for malformed in (None, True, "options", {"options": True}, ("options",)):
            self.assertEqual(self.policy(available_concepts=malformed)["available_concepts"], ["environment"])
        self.assertEqual(self.policy(available_concepts=["unknown"] * 32 + ["options"])["available_concepts"], [])

    def test_returned_policy_is_defensive_and_input_unchanged(self):
        runtime = {"community": {"available_concepts": ["environment", "inquiry"]}}
        before = json.dumps(runtime, sort_keys=True)
        result = self.community.get_community_policy(runtime)
        result["available_concepts"].append("options")
        self.assertEqual(json.dumps(runtime, sort_keys=True), before)
        self.assertEqual(self.community.get_community_policy({}), DEFAULT_POLICY)

    def test_context_contains_only_available_versioned_invitations(self):
        context = self.community.get_onboarding_context(self.policy(available_concepts=["options", "inquiry"]))
        self.assertEqual(set(context), {"version", "introduction_stage", "invitations"})
        self.assertEqual(context["version"], "community-invitations/v1")
        self.assertEqual(list(context["invitations"]), ["options", "inquiry"])
        self.assertTrue(all(isinstance(text, str) for text in context["invitations"].values()))
        self.assertEqual(self.community.get_onboarding_context(self.policy(available_concepts=[]))["invitations"], {})

    def test_full_invitation_context_stays_compact_and_optional(self):
        context = self.community.get_onboarding_context(self.policy(
            available_concepts=list(self.community.CONCEPT_IDS), introduction_stage="market",
            forum_open=True, peer_messages_open=True, share_peer_positions=True,
        ))
        rendered = json.dumps(context, ensure_ascii=False)
        self.assertLessEqual(len(rendered), 3000)
        self.assertEqual(set(context["invitations"]), set(self.community.CONCEPT_IDS))
        for phrase in ("not maturity deadlines", "journals and inquiries are optional",
                       "not a required curriculum", "separate runtime boundaries",
                       "Nonfinancial exploration remains available",
                       "grants no trading permission", "Neither opposition nor reconciliation"):
            self.assertIn(phrase, rendered)
        for field in (*GATES, "opens_at", "deadline", "source_text", "reward", "grade"):
            self.assertNotIn(f'"{field}":', rendered)

    def test_unintroduced_concepts_do_not_remove_general_exploration(self):
        context = self.community.get_onboarding_context(self.policy())
        text = context["invitations"]["environment"]
        self.assertIn("Explore, read, ask, rest", text)
        self.assertIn("not a required curriculum", text)
        self.assertNotIn("inquiry", context["invitations"])
        changed = self.policy(introduction_stage="market", available_concepts=[])
        self.assertEqual(self.community.get_onboarding_context(changed)["invitations"], {})
        self.assertFalse(any(changed[gate] for gate in GATES))


if __name__ == "__main__":
    unittest.main()
