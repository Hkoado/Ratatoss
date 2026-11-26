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
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

if sys.platform != "win32":
    raise unittest.SkipTest("Windows launcher tests require Windows.")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pywintypes
import win32api
import win32con
import win32event
import win32job
import win32process
import win32security
import winerror
from win32com.client import Dispatch
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


def stop_smoke_processes(job, programs):
    """Stop only installed Ratatoss processes descended from this smoke runner."""
    access = win32con.PROCESS_QUERY_LIMITED_INFORMATION | win32con.PROCESS_TERMINATE | win32con.SYNCHRONIZE
    deadline = time.monotonic() + 15
    while True:
        stopped = False
        for pid in win32job.QueryInformationJobObject(job, win32job.JobObjectBasicProcessIdList):
            try:
                handle = win32api.OpenProcess(access, False, pid)
            except pywintypes.error as exc:
                if exc.winerror not in (winerror.ERROR_INVALID_PARAMETER, winerror.ERROR_ACCESS_DENIED):
                    raise
                continue
            try:
                if not win32job.IsProcessInJob(handle, job):
                    continue
                if win32event.WaitForSingleObject(handle, 0) == win32event.WAIT_OBJECT_0:
                    continue
                image = Path(win32process.GetModuleFileNameEx(handle, 0))
                if image in programs:
                    try:
                        win32api.TerminateProcess(handle, 1)
                    except pywintypes.error as exc:
                        if exc.winerror != winerror.ERROR_ACCESS_DENIED:
                            raise
                        if win32event.WaitForSingleObject(handle, 0) != win32event.WAIT_OBJECT_0:
                            raise
                    if win32event.WaitForSingleObject(handle, 3000) != win32event.WAIT_OBJECT_0:
                        raise TimeoutError("The smoke test's Ratatoss process did not exit.")
                    stopped = True
            finally:
                handle.Close()
        if not stopped:
            return
        if time.monotonic() >= deadline:
            raise TimeoutError("The smoke test could not clean up its Ratatoss processes.")


def run_installed_worker(web_program, terminal_program, configured, data, log):
    with open(log, "w", encoding="utf-8") as output, contextlib.redirect_stderr(output):
        try:
            InstalledStarterTests().exercise_starter(
                Path(web_program), Path(terminal_program), int(configured), Path(data),
            )
        except Exception:
            traceback.print_exc()
            raise SystemExit(1)


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
        root = Path(INSTALL).resolve()
        programs = {
            "web": root / "Ratatoss.exe",
            "terminal": root / "Ratatoss-Terminal.exe",
        }
        start_menu = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, None, 0)) / "Ratatoss"
        shortcuts = {
            "web": start_menu / "Ratatoss.lnk",
            "terminal": start_menu / "Ratatoss Terminal.lnk",
        }
        windows_shell = Dispatch("WScript.Shell")
        for role, shortcut in shortcuts.items():
            self.assertTrue(shortcut.is_file())
            self.assertTrue(programs[role].is_file())
            target = windows_shell.CreateShortcut(str(shortcut)).TargetPath
            self.assertEqual(Path(target).resolve(), programs[role])
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

            # Assign the suspended worker before even the venv redirector can
            # create a child. Launcher and detached Node processes inherit the job.
            code = (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from test_launcher import run_installed_worker; run_installed_worker(*sys.argv[2:])"
            )
            log = Path(workdir) / "installed-smoke.log"
            command = subprocess.list2cmdline([
                sys.executable, "-c", code, str(Path(__file__).resolve().parent),
                str(programs["web"]), str(programs["terminal"]), str(configured), str(data), str(log),
            ])
            job = win32job.CreateJobObject(None, "")
            try:
                worker, thread, _, _ = win32process.CreateProcess(
                    sys.executable, command, None, None, False,
                    win32con.CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW,
                    fixture_env, workdir, win32process.STARTUPINFO(),
                )
                try:
                    win32job.AssignProcessToJobObject(job, worker)
                    win32process.ResumeThread(thread)
                    if win32event.WaitForSingleObject(worker, 100_000) != win32event.WAIT_OBJECT_0:
                        raise TimeoutError("The installed smoke worker did not finish.")
                    exit_code = win32process.GetExitCodeProcess(worker)
                    if exit_code:
                        details = log.read_text(encoding="utf-8") if log.is_file() else ""
                        self.fail(f"Installed smoke worker exited with {exit_code}.\n{details}")
                finally:
                    if win32event.WaitForSingleObject(worker, 0) != win32event.WAIT_OBJECT_0:
                        win32api.TerminateProcess(worker, 1)
                        win32event.WaitForSingleObject(worker, 3000)
                    thread.Close()
                    worker.Close()
            finally:
                try:
                    stop_smoke_processes(job, programs.values())
                finally:
                    job.Close()

    def exercise_starter(self, web_program, terminal_program, configured, data):
        def launch(program, menu=""):
            result = subprocess.run(
                [program], input=menu, capture_output=True, encoding="utf-8", timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            web = pool.submit(launch, web_program)
            terminal = pool.submit(launch, terminal_program, "2\n1\n3\n")
            web.result()
            status = terminal.result()
        database = data / NODE_DATABASE_NAME
        self.assertTrue(database.is_file(), "Another starter may have won the mutex.")
        self.assertIn("Chưa kết nối điều phối", status)
        port = int(re.search(r"http://127\.0\.0\.1:(\d+)/", status)[1])
        self.assertNotEqual(port, configured)
        self.assertEqual(NodeIPC().read_port(2), port)
        self.assertTrue(check_web(port))
        health, body = get(port, "/api/health", Origin=f"http://{LOOPBACK}:{port}")
        self.assertEqual(health, 200)
        self.assertEqual(json.loads(body), {"status": "ok", "mode": "starter", "transport_enabled": False})
        self.assertEqual(get(port, "/", Host=f"{LOOPBACK}:{configured}")[0], 403)
        self.assertEqual(get(port, "/", Origin=f"http://{LOOPBACK}:{configured}")[0], 403)
        self.assertEqual(get(port, "/", Origin="https://example.invalid")[0], 403)

        launch(web_program)
        self.assertIn(f"http://{LOOPBACK}:{port}/", launch(terminal_program, "2\n3\n"))
        with contextlib.closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("PRAGMA application_id").fetchone()[0], APPLICATION_IDS["node"])
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
