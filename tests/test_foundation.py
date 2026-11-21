import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from ratatoss.database import NODE_DATABASE_NAME, open_database
from ratatoss.settings import DEFAULT_NODE_PORT, NodeSettings, local_absolute_path, node_data_dir


class FoundationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("RATATOSS_")}

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "ratatoss", *args],
            env=self.env, capture_output=True, text=True, timeout=15,
        )

    def parallel_cli(self, commands):
        processes = []
        try:
            for args in commands:
                processes.append(subprocess.Popen(
                    [sys.executable, "-m", "ratatoss", *args],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                ))
            results = []
            for process in processes:
                _, stderr = process.communicate(timeout=15)
                results.append((process.returncode, stderr))
            return results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def assert_cli_succeeded(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_node_settings_default_and_validation(self):
        with patch.dict(os.environ, self.env, clear=True):
            settings = NodeSettings.load()
            self.assertEqual(settings.port, DEFAULT_NODE_PORT)
            self.assertEqual(settings.data_dir, node_data_dir())
            self.assertTrue(settings.data_dir.is_absolute())
        self.env["RATATOSS_NODE_DATA_DIR"] = "relative/path"
        self.assertIn("absolute path", self.cli("init", "node").stderr)
        self.env["RATATOSS_NODE_PORT"] = "wrong"
        self.assertIn("must be an integer", self.cli("serve").stderr)
        self.env["RATATOSS_NODE_PORT"] = "65536"
        self.assertIn("between 1 and 65535", self.cli("serve").stderr)
        self.assertIn("RATATOSS_CONTROLLER_DB", self.cli("init", "controller").stderr)
        self.assertFalse(list(self.root.iterdir()))

    def test_cli_initializes_each_role_and_reopens_existing_data(self):
        self.env["RATATOSS_NODE_DATA_DIR"] = str(self.root / "node")
        self.env["RATATOSS_CONTROLLER_DB"] = str(self.root / "controller.sqlite3")
        self.assert_cli_succeeded(self.cli("init", "node"))
        self.assert_cli_succeeded(self.cli("init", "controller"))

        controller_db = Path(self.env["RATATOSS_CONTROLLER_DB"])
        with closing(open_database(controller_db, "controller")) as connection:
            for pragma, expected in (
                ("foreign_keys", 1), ("journal_mode", "wal"), ("synchronous", 2), ("busy_timeout", 5000)
            ):
                self.assertEqual(connection.execute(f"PRAGMA {pragma}").fetchone(), (expected,))
            with connection:
                connection.execute(
                    "INSERT INTO devices (device_id, display_name, token_sha256, enrolled_at_ms) "
                    "VALUES (?, ?, ?, ?)",
                    ("fixture", "Fixture", bytes(32), 0),
                )
        self.assert_cli_succeeded(self.cli("init", "controller"))
        with closing(open_database(controller_db, "controller")) as connection:
            self.assertEqual(connection.execute("SELECT device_id FROM devices").fetchall(), [("fixture",)])

        node_db = Path(self.env["RATATOSS_NODE_DATA_DIR"]) / NODE_DATABASE_NAME
        with closing(open_database(node_db, "node")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM local_jobs").fetchone(), (0,))
        result = self.cli("init", "controller", "--db", str(node_db))
        self.assertEqual(result.returncode, 2)
        self.assertIn("other Ratatoss role", result.stderr)

    def test_network_paths_are_rejected_without_network_access(self):
        for value in ("//server/share/db.sqlite3", "//?/UNC/server/share/db.sqlite3"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "local drive"):
                local_absolute_path(PureWindowsPath(value), "Database path")
        local_path = PureWindowsPath("//?/C:/data/db.sqlite3")
        self.assertEqual(local_absolute_path(local_path, "Database path"), local_path)

    def test_rejects_unknown_and_future_databases(self):
        db = self.root / "unknown.sqlite3"
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("CREATE TABLE unrelated (name TEXT)")
        result = self.cli("init", "controller", "--db", str(db))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unrecognized SQLite database schema", result.stderr)
        with closing(sqlite3.connect(db)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone(), ("delete",))
            self.assertEqual(connection.execute("SELECT name FROM sqlite_schema").fetchall(), [("unrelated",)])

        self.assert_cli_succeeded(self.cli("init", "node", "--data-dir", str(self.root)))
        node_db = self.root / NODE_DATABASE_NAME
        with closing(sqlite3.connect(node_db)) as connection:
            connection.execute("PRAGMA user_version = 99")
        result = self.cli("init", "node", "--data-dir", str(self.root))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unsupported node database schema version", result.stderr)

    def test_concurrent_initialization(self):
        db = self.root / "controller.sqlite3"
        command = ("init", "controller", "--db", str(db))
        for returncode, stderr in self.parallel_cli([command] * 6):
            self.assertEqual(returncode, 0, stderr)
        with closing(open_database(db, "controller")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM assignments").fetchone(), (0,))
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_concurrent_roles_do_not_mix_schemas_at_the_same_path(self):
        db = self.root / NODE_DATABASE_NAME
        node_result, controller_result = self.parallel_cli([
            ("init", "node", "--data-dir", str(self.root)),
            ("init", "controller", "--db", str(db)),
        ])
        self.assertCountEqual([node_result[0], controller_result[0]], [0, 2],
                              (node_result, controller_result))
        role, loser, own_table, other_table = (
            ("node", controller_result, "local_jobs", "assignments")
            if node_result[0] == 0 else ("controller", node_result, "assignments", "local_jobs")
        )
        self.assertIn("other Ratatoss role", loser[1])
        with closing(open_database(db, role)) as connection:
            tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")}
            self.assertIn(own_table, tables)
            self.assertNotIn(other_table, tables)
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone(), ("ok",))

    def test_schema_and_identity_roll_back_together(self):
        db = self.root / NODE_DATABASE_NAME
        broken_schema = ["CREATE TABLE added_before_error (name TEXT);", "INVALID SQL;"]
        with patch("ratatoss.database._schema_statements", return_value=broken_schema):
            with self.assertRaises(sqlite3.OperationalError):
                open_database(db, "node")
        with closing(sqlite3.connect(db)) as connection:
            self.assertEqual(connection.execute("PRAGMA application_id").fetchone(), (0,))
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (0,))
            self.assertEqual(connection.execute("SELECT name FROM sqlite_schema").fetchall(), [])
        self.assert_cli_succeeded(self.cli("init", "node", "--data-dir", str(self.root)))

    def test_reopen_wal_while_another_connection_is_writing(self):
        db = self.root / NODE_DATABASE_NAME
        with closing(open_database(db, "node")) as writer:
            with writer:
                writer.execute("BEGIN IMMEDIATE")
                with closing(open_database(db, "node")) as reader:
                    self.assertEqual(reader.execute("SELECT count(*) FROM local_jobs").fetchone(), (0,))

    def test_serve_uses_real_http_and_cli_overrides_environment(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.env["RATATOSS_NODE_PORT"] = "invalid-env-port"
        self.env["RATATOSS_NODE_DATA_DIR"] = "invalid/env/path"
        data_dir = self.root / "node"
        args = [sys.executable, "-m", "ratatoss", "serve", "--port", str(port), "--data-dir", str(data_dir)]
        process = subprocess.Popen(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def request(path, headers=None):
            with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=1)) as connection:
                connection.request("GET", path, headers=headers or {})
                response = connection.getresponse()
                return response.status, response.read(), response.headers

        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    status, body, headers = request("/api/health")
                    break
                except OSError:
                    if process.poll() is not None:
                        self.fail(process.communicate()[1].decode(errors="replace"))
                    if time.monotonic() >= deadline:
                        self.fail("Loopback UI did not start")
                    time.sleep(0.05)

            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"status": "ok", "mode": "starter", "transport_enabled": False})
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(request("/")[0], 200)
            self.assertEqual(request("/style.css")[0], 200)
            self.assertEqual(request("/api/health", {"Host": "example.invalid"})[0], 403)
            self.assertEqual(request("/api/health", {"Origin": "https://example.invalid"})[0], 403)
            self.assertEqual(request("/api/health", {"Origin": f"http://127.0.0.1:{port}"})[0], 200)
            self.assertEqual(request("/v1/devices/me")[0], 404)
            self.assertTrue((data_dir / NODE_DATABASE_NAME).is_file())
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=5)

    def test_manifest_and_verify_cli(self):
        self.env["RATATOSS_NODE_DATA_DIR"] = "invalid/env/path"
        fixture = self.root / "fixture.bin"
        fixture.write_bytes(b"abcdefghij")
        manifest = self.root / "manifest.json"
        self.assert_cli_succeeded(self.cli("manifest", str(fixture), "--output", str(manifest)))
        self.assert_cli_succeeded(self.cli("verify", str(fixture), str(manifest)))
        fixture.write_bytes(b"abcd")
        self.assertEqual(self.cli("verify", str(fixture), str(manifest)).returncode, 1)

    def test_verify_batch_cli_checks_the_selected_batch(self):
        fixture = self.root / "fixture.bin"
        fixture.write_bytes(b"abcdefghij")
        manifest = self.root / "manifest.json"
        self.assert_cli_succeeded(self.cli(
            "manifest", str(fixture), "--piece-size", "3", "--batch-size", "6", "--output", str(manifest),
        ))
        batch = self.root / "batch.bin"
        batch.write_bytes(b"ghij")
        verify = ("verify", str(batch), str(manifest), "--batch")
        self.assert_cli_succeeded(self.cli(*verify, "1"))
        self.assertEqual(self.cli(*verify, "0").returncode, 1)
        self.assertEqual(self.cli(*verify, "2").returncode, 2)
        batch.write_bytes(b"ghix")
        self.assertEqual(self.cli(*verify, "1").returncode, 1)
