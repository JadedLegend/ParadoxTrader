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

    def test_no_root_render_blueprint_and_start_sh_refuses_by_default(self):
        self.assertFalse((ROOT / "render.yaml").exists())
        script = (ROOT / "start.sh").read_text()
        self.assertIn('PARADOX_ALLOW_LEGACY_APP:-}" != "1"', script)
        self.assertIn("--host 127.0.0.1", script)


if __name__ == "__main__":
    unittest.main()
