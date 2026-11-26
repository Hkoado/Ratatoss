"""Open the starter UI or print its URL, sharing one Node per macOS account."""

import errno
import fcntl
import http.client
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path

import uvicorn

from ratatoss.app import create_app
from ratatoss.database import NODE_DATABASE_NAME, initialize_database
from ratatoss.settings import LOOPBACK, NodeSettings


def private_directory(path):
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError(f"Thư mục phải thuộc tài khoản hiện tại và có quyền 700: {path}")


def private_file(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, "r+")


def healthy(port):
    client = http.client.HTTPConnection(LOOPBACK, port, timeout=0.4)
    try:
        client.request("GET", "/api/health")
        response = client.getresponse()
        return response.status == 200 and json.load(response).get("mode") == "starter"
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        client.close()


def wait_ready(port, process=None):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("Node dừng khi khởi động. Hãy kiểm tra thư mục dữ liệu và SQLite.")
        if healthy(port):
            return port
        time.sleep(0.1)
    raise TimeoutError("Hết thời gian chờ Node.")


def node_port():
    state = Path.home() / "Library" / "Application Support" / "Ratatoss"
    private_directory(state)
    # Serialize launchers; the child inherits the second flock for its entire lifetime.
    with private_file(state / "launch.lock") as launch, private_file(state / "node.lock") as node:
        fcntl.flock(launch, fcntl.LOCK_EX)
        try:
            fcntl.flock(node, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return wait_ready(int(node.read()))

        settings = NodeSettings.load()
        private_directory(settings.data_dir)
        with socket.socket() as listener:
            try:
                listener.bind((LOOPBACK, settings.port))
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise
                listener.bind((LOOPBACK, 0))
            listener.listen()
            port = listener.getsockname()[1]
            node.seek(0)
            node.truncate()
            node.write(str(port))
            node.flush()
            process = subprocess.Popen(
                [sys.executable, "--node", str(listener.fileno())],
                pass_fds=(node.fileno(), listener.fileno()), start_new_session=True,
                cwd=state, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
            )
            try:
                return wait_ready(port, process)
            except (TimeoutError, KeyboardInterrupt):
                process.terminate()
                raise


def serve(fd):
    settings = NodeSettings.load()
    initialize_database(settings.data_dir / NODE_DATABASE_NAME, "node")
    with socket.socket(fileno=fd) as listener:
        app = create_app(listener.getsockname()[1])
        server = uvicorn.Server(uvicorn.Config(
            app, loop="asyncio", http="h11", ws="none", proxy_headers=False,
            log_config=None, access_log=False,
        ))
        server.run(sockets=[listener])
        return 0 if server.started else 1


def terminal_menu():
    while True:
        try:
            choice = input("1. Mở web    2. Xem trạng thái    3. Đóng menu\nChọn: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice == "3":
            return
        if choice in ("1", "2"):
            url = f"http://{LOOPBACK}:{node_port()}/"
            if choice == "1":
                subprocess.run(["/usr/bin/open", url], check=True)
            else:
                print(f"Starter đang chạy · {url}", flush=True)


def main(args):
    os.umask(0o077)
    if len(args) == 2 and args[0] == "--node":
        return serve(int(args[1]))
    if args not in ([], ["--status"], ["--terminal"]):
        print("Ratatoss [--status | --terminal]", file=sys.stderr)
        return 2
    try:
        if args == ["--terminal"]:
            terminal_menu()
            return 0
        url = f"http://{LOOPBACK}:{node_port()}/"
        if args:
            print(url, flush=True)
        else:
            subprocess.run(["/usr/bin/open", url], check=True)
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        if args:
            print(str(exc), file=sys.stderr)
        else:
            subprocess.run(["/usr/bin/osascript", "-e", "on run argv", "-e",
                            'display alert "Ratatoss" message (item 1 of argv) as critical',
                            "-e", "end run", "--", str(exc)])
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
