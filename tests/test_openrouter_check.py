"""Check connection: key, free reply tests at zero price, paid endpoint checks only.

Scripted HTTP; the network is blocked."""
import base64
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.runtime.openrouter_check import check_connection
from core.runtime.owner_settings import OwnerSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import private_dashboard as gateway  # noqa: E402

KEY = "sk-or-v1-" + "k" * 64
CATALOG = {"data": [
    {"id": "free/model:free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "paid/model", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
    {"id": "paid/empty", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
    {"id": "free/broken", "pricing": {"prompt": "0", "completion": "0", "request": "0"}},
]}


class Response:
    def __init__(self, status, data):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class ScriptedOpenRouter:
    def __init__(self, *, key_status=200, free_tier=False):
        self.key_status, self.free_tier = key_status, free_tier
        self.posts = []

    def get(self, url, **kwargs):
        if url.endswith("/key"):
            if self.key_status != 200:
                return Response(self.key_status, {"error": {"message": "No auth credentials found " + KEY}})
            return Response(200, {"data": {"is_free_tier": self.free_tier, "limit_remaining": None}})
        if url.endswith("/models"):
            return Response(200, CATALOG)
        if url.endswith("/paid/model/endpoints"):
            return Response(200, {"data": {"endpoints": [{"provider_name": "a"}, {"provider_name": "b"}]}})
        if url.endswith("/paid/empty/endpoints"):
            return Response(200, {"data": {"endpoints": []}})
        raise AssertionError("unexpected GET " + url)

    def post(self, url, **kwargs):
        self.posts.append(kwargs["json"])
        assert url.endswith("/chat/completions")
        if kwargs["json"]["model"] == "free/broken":
            return Response(429, {"error": {"message": "Rate limit exceeded: free-models-per-day"}})
        return Response(200, {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]})


def models(**chosen):
    slots = ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter", "witness")
    return {slot: chosen.get(slot) for slot in slots}


class CheckConnectionTests(unittest.TestCase):
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection")):
            blocked = patch.object(target, name, side_effect=AssertionError("network forbidden"))
            blocked.start()
            self.addCleanup(blocked.stop)

    def run_check(self, http, chosen):
        return check_connection(KEY, chosen, http_get=http.get, http_post=http.post)

    def test_free_models_get_a_zero_price_reply_test_and_paid_models_only_an_endpoint_check(self):
        http = ScriptedOpenRouter()
        result = self.run_check(http, models(tempest="free/model:free", siren="paid/model", shadow="paid/model",
                                             alchemist="free/model:free", weaver="paid/model", oracle="paid/model",
                                             paradox_hunter="paid/model"))
        self.assertEqual(result["key"]["status"], "ok")
        rows = {row["model"]: row for row in result["models"]}
        self.assertEqual(rows["free/model:free"]["used_by"], ["Tempest", "Alchemist"])  # Each model tested once.
        self.assertEqual((rows["free/model:free"]["kind"], rows["free/model:free"]["status"]), ("free", "ok"))
        self.assertEqual((rows["paid/model"]["kind"], rows["paid/model"]["status"]), ("paid", "ok"))
        self.assertEqual(len(http.posts), 1)  # Only the free model generated anything.
        self.assertEqual(http.posts[0]["provider"]["max_price"], {"prompt": 0, "completion": 0, "request": 0})
        self.assertEqual(result["unset"], ["Witness"])
        self.assertEqual(result["status"], "ok")  # The witness's model is optional.

    def test_failures_name_the_agents_and_model_and_never_show_the_key(self):
        http = ScriptedOpenRouter()
        result = self.run_check(http, models(tempest="free/broken", siren="paid/empty", oracle="gone/model"))
        rows = {row["model"]: row for row in result["models"]}
        self.assertEqual(rows["free/broken"]["used_by"], ["Tempest"])
        self.assertIn("rate limited", rows["free/broken"]["message"])
        self.assertEqual(rows["paid/empty"]["status"], "fail")
        self.assertIn("does not list", rows["gone/model"]["message"])
        self.assertEqual(result["status"], "fail")
        self.assertIn("Weaver", result["unset"])

    def test_a_rejected_key_is_reported_without_echoing_it_and_skips_reply_tests(self):
        http = ScriptedOpenRouter(key_status=401)
        result = self.run_check(http, models(tempest="free/model:free", siren="paid/model"))
        self.assertEqual(result["key"]["status"], "fail")
        self.assertIn("key was rejected", result["key"]["message"])
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(http.posts, [])

    def test_an_account_without_credits_warns_that_paid_models_will_be_refused(self):
        result = self.run_check(ScriptedOpenRouter(free_tier=True), models(siren="paid/model"))
        self.assertEqual(result["key"]["status"], "warn")
        self.assertEqual(result["models"][0]["status"], "warn")
        self.assertIn("no credits", result["models"][0]["message"])

    def test_network_trouble_is_reported_not_raised(self):
        def down(url, **kwargs):
            raise ConnectionError("down")
        result = check_connection(KEY, models(siren="paid/model"), http_get=down, http_post=down)
        self.assertEqual(result["key"]["status"], "fail")
        self.assertIn("could not reach", result["key"]["message"])


class CheckRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "dist").mkdir()
        (root / "dist" / "index.html").write_text("<html></html>")
        self.settings_dir = root / "settings"
        OwnerSettings(self.settings_dir).update({"openrouter_key": KEY, "models": {"siren": "paid/model"}})
        self.calls = []

        def fake_check(key, chosen):
            self.calls.append((key, chosen["siren"]))
            return {"status": "ok", "key": {"status": "ok", "message": "fine"}, "models": [], "unset": []}

        app = gateway.create_gateway(sessions_root=root / "sessions", frontend_dist=root / "dist",
                                     operator_token="server-side-token", user="owner",
                                     password_hash=gateway.hash_password("pw", iterations=1000),
                                     settings_dir=self.settings_dir, connection_check=fake_check)
        self.client = TestClient(app)
        auth = {"Authorization": "Basic " + base64.b64encode(b"owner:pw").decode()}
        self.write = {**auth, "Origin": "http://testserver", "Content-Type": "application/json"}

    def test_the_check_needs_login_and_same_origin_and_uses_the_saved_key(self):
        self.assertEqual(self.client.post("/api/settings/check", content="{}",
                                          headers={k: v for k, v in self.write.items() if k != "Authorization"}).status_code, 401)
        self.assertEqual(self.client.post("/api/settings/check", content="{}",
                                          headers={**self.write, "Origin": "https://evil.example"}).status_code, 405)
        response = self.client.post("/api/settings/check", content="{}", headers=self.write)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calls, [(KEY, "paid/model")])
        self.assertNotIn(KEY, response.text)

    def test_a_second_click_within_seconds_does_not_spend_another_check(self):
        self.assertEqual(self.client.post("/api/settings/check", content="{}", headers=self.write).status_code, 200)
        self.assertEqual(self.client.post("/api/settings/check", content="{}", headers=self.write).status_code, 429)
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
