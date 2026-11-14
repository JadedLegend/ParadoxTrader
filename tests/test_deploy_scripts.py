import base64
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy"))

import backup_data  # noqa: E402
import private_dashboard as gateway  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "server-side-operator-token"
PASSWORD = "correct horse battery staple"


def basic(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


class DashboardGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.dist = root / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text("<!doctype html><title>app</title>")
        (self.dist / "assets" / "app.js").write_text("console.log(1)")
        self.sessions = root / "sessions"
        self.sessions.mkdir()
        app = gateway.create_gateway(sessions_root=self.sessions, frontend_dist=self.dist, operator_token=TOKEN,
                                     user="owner", password_hash=gateway.hash_password(PASSWORD, iterations=1000))
        self.client = TestClient(app, raise_server_exceptions=True)
        self.auth = basic("owner", PASSWORD)

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_owner_authentication(self):
        self.assertEqual(self.client.get("/").status_code, 401)
        self.assertEqual(self.client.get("/", headers=basic("owner", "wrong")).status_code, 401)
        self.assertEqual(self.client.get("/", headers=basic("other", PASSWORD)).status_code, 401)
        self.assertEqual(self.client.get("/", headers={"Authorization": "Bearer " + TOKEN}).status_code, 401)

    def test_serves_index_assets_and_spa_routes(self):
        self.assertIn("app", self.client.get("/", headers=self.auth).text)
        self.assertEqual(self.client.get("/assets/app.js", headers=self.auth).status_code, 200)
        spa = self.client.get("/journals", headers=self.auth)
        self.assertEqual(spa.status_code, 200)
        self.assertIn("app", spa.text)

    def test_missing_static_asset_returns_404_not_500(self):
        for path in ("/assets/missing.js", "/favicon.ico", "/assets/deep/nope.css"):
            response = self.client.get(path, headers=self.auth)
            self.assertEqual(response.status_code, 404, path)
        traversal = self.client.get("/..%2f..%2fetc%2fpasswd", headers=self.auth)
        self.assertEqual(traversal.status_code, 404)

    def test_only_reads_are_allowed(self):
        for method in ("post", "put", "delete", "patch"):
            response = getattr(self.client, method)("/api/rehearsals", headers=self.auth)
            self.assertEqual(response.status_code, 405, method)

    def test_rehearsal_api_gets_server_side_token_and_legacy_api_is_absent(self):
        runs = self.client.get("/api/rehearsals", headers=self.auth)
        self.assertNotIn(runs.status_code, (401, 403, 503))
        self.assertNotIn(TOKEN, runs.text)
        for legacy in ("/api/config", "/api/status", "/api/queue", "/api/wake/tempest"):
            self.assertEqual(self.client.get(legacy, headers=self.auth).status_code, 404, legacy)

    def test_security_headers_present(self):
        response = self.client.get("/", headers=self.auth)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-frame-options"], "DENY")

    def test_refuses_to_build_without_credentials(self):
        with self.assertRaises(ValueError):
            gateway.create_gateway(sessions_root=self.sessions, frontend_dist=self.dist, operator_token="",
                                   user="owner", password_hash="x")
        with self.assertRaises(ValueError):
            gateway.create_gateway(sessions_root=self.sessions, frontend_dist=self.dist, operator_token=TOKEN,
                                   user="", password_hash="")

    def test_gateway_never_imports_broad_app(self):
        source = (ROOT / "deploy" / "private_dashboard.py").read_text()
        self.assertNotIn("api.app", source)
        self.assertNotIn("start_scheduler", source)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source, self.dest = root / "data", root / "backups"
        (self.source / "sessions" / "run1").mkdir(parents=True)
        for name in ("control.sqlite3", "sessions/run1/witness.sqlite3"):
            with closing(sqlite3.connect(self.source / name)) as conn:
                conn.execute("CREATE TABLE t (v TEXT)")
                conn.execute("INSERT INTO t VALUES ('kept')")
                conn.commit()
        (self.source / "notes.db").write_text("not a database")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_consistent_databases(self):
        result = backup_data.run_backup(self.source, self.dest, now=datetime(2026, 11, 14, tzinfo=timezone.utc))
        self.assertEqual(sorted(result["databases"]), ["control.sqlite3", "sessions/run1/witness.sqlite3"])
        snapshot = Path(result["snapshot"])
        with closing(sqlite3.connect(snapshot / "sessions/run1/witness.sqlite3")) as conn:
            self.assertEqual(conn.execute("SELECT v FROM t").fetchone()[0], "kept")

    def test_interrupted_staging_is_cleaned_up_next_run(self):
        self.dest.mkdir()
        leftover = self.dest / ".backup-20261113T000000Z"
        (leftover / "partial").mkdir(parents=True)
        result = backup_data.run_backup(self.source, self.dest)
        self.assertEqual(result["cleaned_staging"], [leftover.name])
        self.assertFalse(leftover.exists())
        self.assertFalse([p for p in self.dest.iterdir() if p.name.startswith(".backup-")])

    def test_failed_copy_leaves_no_staging_or_snapshot(self):
        original = backup_data.copy_database

        def boom(src, target):
            raise RuntimeError("disk full")

        backup_data.copy_database = boom
        try:
            with self.assertRaises(RuntimeError):
                backup_data.run_backup(self.source, self.dest)
        finally:
            backup_data.copy_database = original
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_handles_are_closed_so_source_files_can_be_removed(self):
        backup_data.run_backup(self.source, self.dest)
        (self.source / "control.sqlite3").unlink()  # would fail on platforms that lock open handles

    def test_prunes_old_snapshots(self):
        for day in range(1, 5):
            backup_data.run_backup(self.source, self.dest, keep=2, now=datetime(2026, 11, day, tzinfo=timezone.utc))
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), ["20261103T000000Z", "20261104T000000Z"])


if __name__ == "__main__":
    unittest.main()
