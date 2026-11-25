"""Windows launcher contracts and optional smoke against an installed copy."""

import concurrent.futures
import contextlib
import http.client
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

if sys.platform != "win32":
    raise unittest.SkipTest("Windows launcher tests require Windows.")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import win32security
from win32com.shell import shell, shellcon

from launcher import bind_loopback, check_web, open_web, terminal_menu
from node_ipc import NodeIPC
from ratatoss.database import APPLICATION_IDS, NODE_DATABASE_NAME, SCHEMA_VERSION
from ratatoss.settings import LOOPBACK

INSTALL = os.environ.get("RATATOSS_TEST_WINDOWS_APP")


def get(port, path, **headers):
    with contextlib.closing(http.client.HTTPConnection(LOOPBACK, port, timeout=3)) as connection:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()


class LauncherTests(unittest.TestCase):
    def test_mutex_allows_one_node_per_account(self):
        ipc = NodeIPC()
        ipc.mutex_name += f".test.{uuid4().hex}"

        def other_node_can_start():
            with ipc.claim_node() as claimed:
                return claimed

        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            with ipc.claim_node() as claimed:
                self.assertTrue(claimed)
                self.assertFalse(pool.submit(other_node_can_start).result(timeout=3))
            self.assertTrue(pool.submit(other_node_can_start).result(timeout=3))

    def test_port_fallback_uses_exclusive_loopback_socket(self):
        with socket.socket() as reserved, socket.socket() as server:
            configured = bind_loopback(reserved, 0)
            actual = bind_loopback(server, configured)
            self.assertNotEqual(actual, configured)
            self.assertEqual(server.getsockname(), (LOOPBACK, actual))

    def test_named_pipe_uses_account_acl_and_delivers_port_without_state_file(self):
        ipc = NodeIPC()
        ipc.pipe_name += f".test.{uuid4().hex}"
        self.assertIsNone(ipc.read_port(0.25))
        with ipc.create_pipe() as pipe:
            self.assertIsNone(ipc.read_port(0.05))
            security = win32security.GetSecurityInfo(
                pipe, win32security.SE_KERNEL_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION,
            )
            self.assertEqual(security.GetSecurityDescriptorOwner(), ipc.sid)
            acl = security.GetSecurityDescriptorDacl()
            self.assertEqual(acl.GetAceCount(), 1)
            self.assertEqual(acl.GetAce(0)[2], ipc.sid)
            stop = threading.Event()
            worker = threading.Thread(target=ipc.publish_port, args=(pipe, 45678, stop))
            worker.start()
            try:
                for _ in range(2):
                    deadline = time.monotonic() + 2
                    while (port := ipc.read_port(0.5)) is None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertEqual(port, 45678)
            finally:
                stop.set()
                worker.join()

    def test_menu_and_web_use_the_resolved_port(self):
        with (
            patch("launcher.get_node_port", return_value=45678),
            patch("builtins.input", side_effect=["2", "1", "3"]),
            patch("launcher.open_web", return_value=True) as browser,
            patch("builtins.print") as display,
        ):
            self.assertEqual(terminal_menu(NodeIPC()), 0)
        browser.assert_called_once_with(45678, terminal=True)
        self.assertTrue(any(f"http://{LOOPBACK}:45678/" in call.args[0] for call in display.call_args_list))
        with patch("os.startfile") as launch:
            self.assertTrue(open_web(45678, terminal=False))
        launch.assert_called_once_with(f"http://{LOOPBACK}:45678/")


@unittest.skipUnless(INSTALL, "Set RATATOSS_TEST_WINDOWS_APP to an installed starter to run this smoke.")
class InstalledStarterTests(unittest.TestCase):
    def test_packaged_shortcut_targets_share_one_node_and_serve_resources(self):
        root = Path(INSTALL)
        programs = {
            "web": root / "Ratatoss.exe",
            "terminal": root / "Ratatoss-Terminal.exe",
        }
        for program in programs.values():
            self.assertTrue(program.is_file())
        start_menu = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0)) / "Ratatoss"
        web_shortcut = start_menu / "Ratatoss.lnk"
        self.assertTrue(web_shortcut.is_file())
        ipc = NodeIPC()
        with ipc.claim_node() as available:
            self.assertTrue(available, "Stop the existing starter before running the installed smoke.")

        with tempfile.TemporaryDirectory() as workdir, socket.socket() as reserved:
            configured = bind_loopback(reserved, 0)
            data = Path(workdir) / "data"
            fixture_env = {**os.environ, "RATATOSS_NODE_PORT": str(configured),
                           "RATATOSS_NODE_DATA_DIR": str(data),
                           "PATH": str(Path(os.environ["SystemRoot"]) / "System32")}
            fixture_env.pop("PYTHONHOME", None)
            fixture_env.pop("PYTHONPATH", None)

            def launch(program, menu=""):
                with subprocess.Popen(
                    [program], cwd=workdir, env=fixture_env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                ) as process:
                    try:
                        stdout, stderr = process.communicate(menu, timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                        raise
                    self.assertEqual(process.returncode, 0, stderr)
                    return stdout

            try:
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    web = pool.submit(
                        subprocess.run, [sys.executable, "-c", "import os, sys; os.startfile(sys.argv[1])",
                                         web_shortcut], cwd=workdir, env=fixture_env, check=True, timeout=10,
                    )
                    terminal = pool.submit(launch, programs["terminal"], "2\n1\n3\n")
                    web.result()
                    status = terminal.result()
                self.assertIn("Chưa kết nối điều phối", status)
                port = int(re.search(r"http://127\.0\.0\.1:(\d+)/", status)[1])
                self.assertNotEqual(port, configured)
                self.assertEqual(ipc.read_port(2), port)
                self.assertTrue(check_web(port))
                health, body = get(port, "/api/health", Origin=f"http://{LOOPBACK}:{port}")
                self.assertEqual(health, 200)
                self.assertEqual(json.loads(body), {"status": "ok", "mode": "starter", "transport_enabled": False})
                self.assertEqual(get(port, "/", Host=f"{LOOPBACK}:{configured}")[0], 403)
                self.assertEqual(get(port, "/", Origin=f"http://{LOOPBACK}:{configured}")[0], 403)
                self.assertEqual(get(port, "/", Origin="https://example.invalid")[0], 403)

                launch(programs["web"])
                self.assertIn(f"http://{LOOPBACK}:{port}/", launch(programs["terminal"], "2\n3\n"))
                with contextlib.closing(sqlite3.connect(data / NODE_DATABASE_NAME)) as db:
                    self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], APPLICATION_IDS["node"])
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            finally:
                # Stop only the process for this isolated test, identified by its executable and bound port.
                if port := ipc.read_port(0.5):
                    subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                         "$listener = Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 "
                         "-LocalPort ([int]$env:RATATOSS_SMOKE_PORT) -ErrorAction SilentlyContinue; "
                         "if ($listener) { $node = Get-Process -Id $listener.OwningProcess; "
                         "if ($node.Path -eq $env:RATATOSS_SMOKE_EXE) { $node.Kill(); $node.WaitForExit() } }"],
                        env={**os.environ, "RATATOSS_SMOKE_PORT": str(port),
                             "RATATOSS_SMOKE_EXE": str(programs["web"])}, check=True, timeout=15,
                    )
