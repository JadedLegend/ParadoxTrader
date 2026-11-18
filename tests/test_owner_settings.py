"""Owner settings: key (write-only), eight models, daily budget, append-only history,
and the dashboard gateway's single protected write."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.runtime.owner_settings import MODEL_SLOTS, OwnerSettings, SettingsError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))
import private_dashboard as gateway  # noqa: E402

KEY = "sk-or-v1-" + "a1b2c3d4" * 8
PASSWORD = "correct horse battery staple"
SEVEN = {"tempest": "deepseek/deepseek-v3.2", "siren": "qwen/qwen3-235b-a22b-2507",
         "alchemist": "deepseek/deepseek-r1-0528", "weaver": "moonshotai/kimi-k2.6",
         "oracle": "google/gemini-2.5-pro", "shadow": "x-ai/grok-4.5",
         "paradox_hunter": "qwen/qwen3-235b-a22b-thinking-2507"}


class OwnerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = OwnerSettings(Path(self.temp.name) / "settings")

    def test_empty_settings_read_cleanly(self):
        value = self.settings.read()
        self.assertEqual(value["models"], {slot: None for slot in MODEL_SLOTS})
        self.assertEqual(value["key"], {"set": False, "ends_with": None})
        self.assertIsNone(value["daily_budget_usd"])
        self.assertIsNone(self.settings.agent_models())

    def test_models_budget_and_key_are_saved_and_the_key_never_read_back(self):
        value = self.settings.update({"models": {**SEVEN, "witness": "anthropic/claude-haiku-5.5"},
                                      "daily_budget_usd": "2.5", "openrouter_key": KEY})
        self.assertEqual(value["models"]["oracle"], "google/gemini-2.5-pro")
        self.assertEqual(value["daily_budget_usd"], "2.50")
        self.assertEqual(value["key"], {"set": True, "ends_with": KEY[-4:]})
        self.assertNotIn(KEY, json.dumps(value))
        self.assertEqual(self.settings.agent_models(), SEVEN)
        self.assertEqual(self.settings.key(), KEY)
        path = self.settings.directory / "openrouter.key"
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.settings.update({"openrouter_key": ""})
        self.assertIsNone(self.settings.key())
        self.assertFalse(path.exists())

    def test_one_change_at_a_time_keeps_everything_else(self):
        self.settings.update({"models": SEVEN, "daily_budget_usd": "1.00"})
        self.settings.update({"models": {"shadow": "openai/gpt-6"}})
        self.assertEqual(self.settings.agent_models()["shadow"], "openai/gpt-6")
        self.assertEqual(self.settings.agent_models()["siren"], SEVEN["siren"])
        self.assertEqual(str(self.settings.daily_budget()), "1.00")

    def test_history_is_append_only_and_never_holds_the_key(self):
        self.settings.update({"daily_budget_usd": "1"})
        self.settings.update({"daily_budget_usd": "3", "openrouter_key": KEY})
        history = self.settings.read()["history"]
        self.assertEqual([row["field"] for row in history], ["openrouter_key", "daily_budget_usd", "daily_budget_usd"])
        self.assertNotIn(KEY, json.dumps(history))
        self.assertIn("ends in ..." + KEY[-4:], json.dumps(history))
        with sqlite3.connect(self.settings.directory / "settings.sqlite3") as conn:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM history")
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE history SET value='\"0\"'")

    def test_bad_values_are_refused_and_change_nothing(self):
        for bad in ({}, {"surprise": 1}, {"models": {"eighth": "a/b"}}, {"models": {"siren": "not a model"}},
                    {"daily_budget_usd": "-1"}, {"daily_budget_usd": "101"}, {"daily_budget_usd": "1.234"},
                    {"daily_budget_usd": 5}, {"daily_budget_usd": "NaN"}, {"openrouter_key": "hunter2"},
                    {"openrouter_key": 12}):
            with self.subTest(bad=bad), self.assertRaises(SettingsError):
                self.settings.update(bad)
        self.assertEqual(self.settings.read()["history"], [])


class SecretSlotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = OwnerSettings(Path(self.temp.name) / "settings")

    def test_data_and_broker_keys_are_write_only(self):
        values = {"alpaca_key_id": "PKABCDEFGH12345678", "alpaca_secret": "s" * 40,
                  "public_com": "pub-key-123456789", "alphavantage": "ABCDEF123456",
                  "fmp": "f" * 32, "bigdata": "bd_key_0123456789"}
        result = self.settings.update({"secrets": values})
        dumped = json.dumps(result)
        for slot, value in values.items():
            self.assertEqual(result["secrets"][slot], {"set": True, "ends_with": value[-4:]})
            self.assertNotIn(value, dumped)
            self.assertEqual(self.settings.secret(slot), value)
            if os.name == "posix":
                path = self.settings.directory / "secrets" / slot
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.settings.update({"secrets": {"fmp": ""}})
        self.assertIsNone(self.settings.secret("fmp"))
        self.assertEqual(self.settings.secret("bigdata"), values["bigdata"])

    def test_slot_read_errors_do_not_hide_settings_or_fail_budget_updates(self):
        self.settings.update({"secrets": {"fmp": "f" * 32, "bigdata": "b" * 20}})
        path = self.settings._secret_path("fmp")
        path.write_bytes(b"\xff")
        result = self.settings.update({"daily_budget_usd": "2"})
        self.assertEqual(result["daily_budget_usd"], "2.00")
        self.assertEqual(result["secrets"]["fmp"]["error"], "secret_unreadable")
        self.assertTrue(result["secrets"]["bigdata"]["set"])
        original = Path.read_text
        def unreadable(path, *args, **kwargs):
            if path.name == "fmp":
                raise PermissionError("sensitive detail")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", unreadable):
            self.assertNotIn("sensitive detail", json.dumps(self.settings.read()))

    def test_only_literal_empty_string_clears_and_history_has_no_suffix(self):
        self.settings.update({"secrets": {"fmp": "  " + "f" * 32 + "  "}})
        for value in (" ", "\t\n"):
            with self.assertRaises(SettingsError):
                self.settings.update({"secrets": {"fmp": value}})
        self.assertEqual(self.settings.secret("fmp"), "f" * 32)
        self.assertEqual(self.settings.read()["history"][0]["value"], "set")
        self.settings.update({"secrets": {"fmp": ""}})
        self.assertEqual(self.settings.read()["history"][0]["value"], "cleared")

    def test_failed_replace_removes_temporary_file(self):
        self.settings.update({"secrets": {"fmp": "f" * 32}})
        with patch("core.runtime.owner_settings.os.replace", side_effect=OSError("failure")):
            with self.assertRaises(OSError):
                self.settings.update({"secrets": {"fmp": "g" * 32}})
        self.assertEqual(list((self.settings.directory / "secrets").glob(".*")), [])
        self.assertEqual(self.settings.secret("fmp"), "f" * 32)

    def test_failed_write_removes_temporary_file_and_preserves_error(self):
        failure = OSError("write failed")
        original = os.fdopen
        def failing_handle(*args, **kwargs):
            handle = original(*args, **kwargs)
            class FailingWriter:
                def __enter__(self):
                    return self
                def write(self, value):
                    raise failure
                def __exit__(self, *args):
                    handle.close()
            return FailingWriter()
        with patch("core.runtime.owner_settings.os.fdopen", failing_handle):
            with self.assertRaises(OSError) as raised:
                self.settings.update({"secrets": {"fmp": "f" * 32}})
        self.assertIs(raised.exception, failure)
        self.assertEqual(list((self.settings.directory / "secrets").iterdir()), [])

    def test_later_write_failure_records_completed_clear(self):
        self.settings.update({"secrets": {"fmp": "f" * 32}})
        with patch.object(self.settings, "_write_private", side_effect=OSError("failure")):
            with self.assertRaises(OSError):
                self.settings.update({"secrets": {"fmp": "", "bigdata": "b" * 20}})
        self.assertIsNone(self.settings.secret("fmp"))
        self.assertEqual(self.settings.read()["history"][0]["value"], "cleared")

    def test_all_destinations_are_checked_before_mutation(self):
        self.settings.update({"secrets": {"fmp": "f" * 32}})
        self.settings._secret_path("bigdata").symlink_to(self.settings._secret_path("fmp"))
        with self.assertRaises(SettingsError):
            self.settings.update({"secrets": {"fmp": "", "bigdata": "b" * 20}})
        self.assertEqual(self.settings.secret("fmp"), "f" * 32)

    def test_live_alpaca_keys_and_unknown_slots_are_refused(self):
        for bad in ({"secrets": {"alpaca_key_id": "AKLIVEKEY123456789"}}, {"secrets": {"unknown": "x" * 20}},
                    {"secrets": {"fmp": "has spaces in it 1234"}}, {"secrets": {"public_com": 5}}, {"secrets": {}}):
            with self.subTest(bad=bad), self.assertRaises(SettingsError):
                self.settings.update(bad)
        self.assertFalse((self.settings.directory / "secrets").exists())


class SettingsGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "dist").mkdir()
        (root / "dist" / "index.html").write_text("<!doctype html><title>app</title>")
        (root / "sessions").mkdir()
        self.settings_dir = root / "settings"
        app = gateway.create_gateway(sessions_root=root / "sessions", frontend_dist=root / "dist",
                                     operator_token="server-side-token", user="owner",
                                     password_hash=gateway.hash_password(PASSWORD, iterations=1000),
                                     settings_dir=self.settings_dir)
        self.client = TestClient(app, base_url="http://127.0.0.1:8080")
        self.auth = {"Authorization": "Basic " + base64.b64encode(f"owner:{PASSWORD}".encode()).decode()}
        self.write = {**self.auth, "Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}

    def test_owner_reads_and_saves_settings(self):
        self.assertEqual(self.client.get("/api/settings", headers=self.auth).json()["key"], {"set": False, "ends_with": None})
        response = self.client.post("/api/settings", headers=self.write,
                                    content=json.dumps({"models": SEVEN, "daily_budget_usd": "1.50", "openrouter_key": KEY}))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(KEY, response.text)
        self.assertEqual(response.json()["daily_budget_usd"], "1.50")
        self.assertNotIn(KEY, self.client.get("/api/settings", headers=self.auth).text)
        self.assertEqual(OwnerSettings(self.settings_dir).key(), KEY)

    def test_the_write_needs_login_same_origin_and_json(self):
        body = json.dumps({"daily_budget_usd": "9.00"})
        self.assertEqual(self.client.post("/api/settings", content=body,
                                          headers={"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"}).status_code, 401)
        for headers in ({**self.write, "Origin": "https://evil.example"}, {k: v for k, v in self.write.items() if k != "Origin"},
                        {**self.write, "Content-Type": "text/plain"},
                        {**self.write, "Content-Type": "application/x-www-form-urlencoded"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post("/api/settings", content=body, headers=headers).status_code, 405)
        self.assertIsNone(OwnerSettings(self.settings_dir).daily_budget())

    def test_no_other_write_is_opened(self):
        for path in ("/api/rehearsals", "/api/config", "/api/settings/extra", "/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, content="{}", headers=self.write).status_code, 405)

    def test_bad_and_oversized_bodies_are_refused_without_echo(self):
        bad = self.client.post("/api/settings", headers=self.write, content=json.dumps({"openrouter_key": "secret-but-wrong"}))
        self.assertEqual((bad.status_code, bad.json()), (400, {"error": "invalid_openrouter_key"}))
        self.assertNotIn("secret-but-wrong", bad.text)
        self.assertEqual(self.client.post("/api/settings", headers=self.write, content="not json").status_code, 400)
        huge = json.dumps({"models": {"siren": "a/" + "b" * 9000}})
        self.assertEqual(self.client.post("/api/settings", headers=self.write, content=huge).status_code, 413)


if __name__ == "__main__":
    unittest.main()
