"""The heartbeat page's data: read-only, honest, never a key or a private note.

Actual temporary stores, scripted offline wakes, a scripted clock and a blocked network."""
import base64
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.runtime.owner_settings import OwnerSettings
from core.runtime.rehearsal.heartbeat_view import day_view
from tests.test_heartbeat import CONFIG, HeartbeatTests, at

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import private_dashboard as gateway  # noqa: E402

KEY = "sk-or-v1-" + "v" * 64


class HeartbeatViewTests(unittest.TestCase):
    # Borrow the heartbeat suite's stores and scripted wakes without rerunning its tests.
    setUp = HeartbeatTests.setUp
    prepare_day = HeartbeatTests.prepare_day
    run_wake = HeartbeatTests.run_wake
    heartbeat = HeartbeatTests.heartbeat

    def test_the_page_shows_wakes_choices_cost_and_the_window(self):
        settings_dir = Path(self.temp.name) / "settings"
        (settings_dir / "market").mkdir(parents=True)
        (settings_dir / "market" / "headlines.json").write_text(json.dumps(
            {"status": "ok", "checked_at": "2026-11-18T09:00:00+00:00",
             "items": [{"title": "Fed holds rates", "source": "Wire"}]}), encoding="utf-8")
        (settings_dir / "market" / "x_posts.json").write_text(json.dumps(
            {"status": "unavailable", "reason": "it answered 403", "checked_at": "2026-11-18T09:00:00+00:00"}),
            encoding="utf-8")
        beat = self.heartbeat()
        self.clock = at(9, 3)
        beat.tick()
        self.clock = at(9, 4)
        view = day_view(beat, settings_dir=settings_dir)
        self.assertTrue(view["reason"].startswith("running"))
        self.assertEqual([w["agent_id"] for w in view["wakes"]], ["tempest", "siren"])
        self.assertEqual(view["wakes"][1]["choices"], ["journal"])  # Siren journals in the scripted wake.
        self.assertTrue(view["wakes"][0]["model"])
        siren = next(a for a in view["agents"] if a["agent_id"] == "siren")
        self.assertEqual(siren["last_wake"]["scheduled_at"][11:16], "09:02")
        self.assertIsNotNone(siren["next_wake"])
        self.assertIn("spent_usd", view["today"])
        lines = view["window"]["lines"]
        self.assertTrue(lines[0].startswith("Market window: unavailable"))
        self.assertIn("Headlines (Massive news): Fed holds rates (Wire)", lines)
        self.assertIn("On X: unavailable (it answered 403).", lines)
        feeds = {f["feed"]: f for f in view["window"]["feeds"]}
        self.assertEqual((feeds["Headlines"]["status"], feeds["X posts"]["status"], feeds["Prices"]["status"]),
                         ("ok", "unavailable", "unchecked"))

    def test_clock_only_slots_are_left_out_and_an_empty_day_is_plain(self):
        beat = self.heartbeat(dispatch="clock-only")
        self.clock = at(9, 3)
        beat.tick()
        view = day_view(beat)
        self.assertEqual(view["wakes"], [])
        self.assertTrue(view["reason"].startswith("clock-only"))
        self.assertEqual(view["window"], {"lines": [], "feeds": []})


class HeartbeatRouteTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "dist").mkdir()
        (root / "dist" / "index.html").write_text("<html></html>")
        self.settings_dir = root / "settings"
        OwnerSettings(self.settings_dir).update({"openrouter_key": KEY})
        self.config = root / "heartbeat.json"
        self.root = root
        self.auth = {"Authorization": "Basic " + base64.b64encode(b"owner:pw").decode()}

    def client(self, config):
        app = gateway.create_gateway(sessions_root=self.root / "sessions", frontend_dist=self.root / "dist",
                                     operator_token="server-side-token", user="owner",
                                     password_hash=gateway.hash_password("pw", iterations=1000),
                                     settings_dir=self.settings_dir, heartbeat_config=config)
        return TestClient(app)

    def test_the_route_needs_login_and_says_when_the_heartbeat_is_not_set_up(self):
        client = self.client(self.config)
        self.assertEqual(client.get("/api/heartbeat").status_code, 401)
        answer = client.get("/api/heartbeat", headers=self.auth).json()
        self.assertEqual(answer["available"], False)
        self.config.write_text(json.dumps({**CONFIG, "dispatch": "clock-only"}), encoding="utf-8")
        answer = client.get("/api/heartbeat", headers=self.auth).json()
        self.assertEqual(answer["available"], True)
        self.assertNotIn(KEY, json.dumps(answer))
        self.assertEqual(client.post("/api/heartbeat", content="{}", headers={
            **self.auth, "Origin": "http://testserver", "Content-Type": "application/json"}).status_code, 405)

    def test_an_unreadable_config_is_a_plain_error_without_paths(self):
        self.config.write_text("{not json", encoding="utf-8")
        response = self.client(self.config).get("/api/heartbeat", headers=self.auth)
        self.assertEqual((response.status_code, response.json()), (503, {"error": "heartbeat_unreadable"}))


if __name__ == "__main__":
    unittest.main()
