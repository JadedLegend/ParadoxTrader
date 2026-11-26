import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class LegacyAppSafetyTests(unittest.TestCase):
    def test_scheduler_is_opt_in(self):
        from api import app as legacy
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PARADOX_LEGACY_SCHEDULER", None)
            self.assertFalse(legacy._legacy_scheduler_enabled())
        for value in ("0", "true", "yes", ""):
            with mock.patch.dict(os.environ, {"PARADOX_LEGACY_SCHEDULER": value}):
                self.assertFalse(legacy._legacy_scheduler_enabled())
        with mock.patch.dict(os.environ, {"PARADOX_LEGACY_SCHEDULER": "1"}):
            self.assertTrue(legacy._legacy_scheduler_enabled())

    def test_config_write_requires_operator_and_refuses_guardrails(self):
        from fastapi import HTTPException
        from api import app as legacy
        req = legacy.ConfigUpdateRequest(key_path="guardrails.autonomous_trading_mode", value=True)
        with mock.patch.object(legacy, "save_config_yaml") as save:
            with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": ""}):
                with self.assertRaises(HTTPException) as ctx:
                    legacy.update_config(req, authorization=None)
                self.assertEqual(ctx.exception.status_code, 503)
            with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": "secret"}):
                with self.assertRaises(HTTPException) as ctx:
                    legacy.update_config(req, authorization="Bearer wrong")
                self.assertEqual(ctx.exception.status_code, 403)
                with self.assertRaises(HTTPException) as ctx:
                    legacy.update_config(req, authorization="Bearer secret")
                self.assertEqual(ctx.exception.detail, "guardrails_not_writable_via_api")
            save.assert_not_called()

    def test_phase_write_requires_operator_before_side_effects(self):
        from fastapi.testclient import TestClient
        from api import app as legacy
        from core.runtime import config

        client = TestClient(legacy.app)  # no lifespan or real stores
        cached = {"runtime": {"current_phase": 0}}
        cfg = {"runtime": {"current_phase": 0, "community": {"forum_open": True}}}
        with (
            mock.patch.object(legacy, "load_config_yaml", return_value=cfg) as load,
            mock.patch.object(legacy, "save_config_yaml") as save,
            mock.patch.object(legacy, "get_forum") as forum,
            mock.patch.object(config, "_config_cache", cached),
        ):
            for token, headers, status, detail in (
                ("", {}, 503, "lineage_operator_unavailable"),
                ("test-operator", {}, 403, "lineage_operator_required"),
                ("test-operator", {"Authorization": "Bearer wrong"}, 403, "lineage_operator_required"),
            ):
                with self.subTest(status=status, headers_present=bool(headers)):
                    with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": token}):
                        response = client.post("/api/phase", json={"phase": 1}, headers=headers)
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.json()["detail"], detail)
            load.assert_not_called()
            save.assert_not_called()
            forum.assert_not_called()
            self.assertIs(config._config_cache, cached)

            with mock.patch.dict(os.environ, {"LINEAGE_OPERATOR_TOKEN": "test-operator"}):
                response = client.post(
                    "/api/phase", json={"phase": 1}, headers={"Authorization": "Bearer test-operator"}
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "phase set", "phase": 1})
            save.assert_called_once_with({"runtime": {"current_phase": 1, "community": {"forum_open": True}}})
            self.assertIsNone(config._config_cache)
            forum.return_value.post_announcement.assert_called_once_with(
                author="SYSTEM", content="Phase advanced to Phase 1: Forum Opens."
            )

    def test_no_root_render_blueprint_and_start_sh_refuses_by_default(self):
        self.assertFalse((ROOT / "render.yaml").exists())
        script = (ROOT / "start.sh").read_text()
        self.assertIn('PARADOX_ALLOW_LEGACY_APP:-}" != "1"', script)
        self.assertIn("--host 127.0.0.1", script)

    def test_serving_the_app_is_refused_without_opt_in(self):
        from fastapi.testclient import TestClient
        from api import app as legacy
        with mock.patch.object(legacy, "_auto_init") as init, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PARADOX_ALLOW_LEGACY_APP", None)
            with self.assertRaises(RuntimeError) as ctx:
                with TestClient(legacy.app):
                    pass
            self.assertIn("legacy_app_disabled", str(ctx.exception))
            init.assert_not_called()

    def test_cross_site_writes_are_refused_and_cors_is_not_open(self):
        from fastapi.testclient import TestClient
        from api import app as legacy
        client = TestClient(legacy.app)  # no context manager: lifespan never runs
        for path in ("/api/wake/tempest", "/api/queue/1/approve", "/api/forum"):
            response = client.post(path, headers={"Origin": "https://evil.example"})
            self.assertEqual(response.status_code, 403, path)
            self.assertEqual(response.json()["detail"], "cross_origin_write_refused")
        preflight = client.options("/api/wake/tempest", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertNotEqual(preflight.headers.get("access-control-allow-origin"), "*")
        self.assertNotEqual(preflight.headers.get("access-control-allow-origin"), "https://evil.example")
        self.assertNotIn("*", legacy._legacy_allowed_origins())

    def test_release_excludes_the_legacy_app(self):
        build = (ROOT / "deploy" / "build_release.sh").read_text()
        self.assertIn('rm -f "$WORK/paradoxtrader-$SHA/api/app.py" "$WORK/paradoxtrader-$SHA/start.sh"', build)
        install = (ROOT / "deploy" / "install_host.sh").read_text()
        self.assertIn('[ ! -e "$REL/api/app.py" ] && [ ! -e "$REL/start.sh" ]', install)


if __name__ == "__main__":
    unittest.main()
