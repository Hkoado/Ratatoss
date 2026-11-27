"""Launch or connect to the packaged Ratatoss starter."""

import ctypes
import errno
import http.client
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pywintypes
import uvicorn

from node_ipc import NodeDataPermissionError, NodeIPC
from ratatoss.__main__ import prepare_node
from ratatoss.database import NODE_DATABASE_NAME
from ratatoss.settings import LOOPBACK, NodeSettings

START_TIMEOUT = 20
# Allow headroom for the observed 78-second cold start on the offline Windows VM.
SETUP_START_TIMEOUT = 120
START_ERROR = (
    "Không khởi động được Ratatoss. Hãy kiểm tra quyền ghi thư mục dữ liệu "
    "và dung lượng đĩa, rồi thử lại."
)
DATA_PERMISSION_ERROR = (
    "Thư mục dữ liệu Ratatoss hoặc tệp SQLite hiện có chưa được bảo vệ theo tài khoản. "
    "Hãy kiểm tra quyền truy cập hoặc chọn thư mục dữ liệu riêng, rồi thử lại."
)
EXIT_DATA_PERMISSION = 3
EXECUTABLE = "Ratatoss.exe"


class NodeStartupTimeout(TimeoutError):
    """The launcher did not receive a ready port before its deadline."""


def bind_loopback(listener, port):
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind((LOOPBACK, port))
    except OSError as exc:
        # Windows can report WSAEACCES for a port held with SO_EXCLUSIVEADDRUSE.
        if exc.errno not in (errno.WSAEADDRINUSE, errno.WSAEACCES):
            raise
        listener.bind((LOOPBACK, 0))
    listener.listen()
    return listener.getsockname()[1]


def check_web(port):
    for path, expected_type in (("/", "text/html"), ("/style.css", "text/css"),
                                ("/api/health", "application/json")):
        connection = http.client.HTTPConnection(LOOPBACK, port, timeout=0.5)
        try:
            connection.request("GET", path, headers={"Host": f"{LOOPBACK}:{port}"})
            response = connection.getresponse()
            if (response.status != 200
                    or not response.getheader("Content-Type", "").startswith(expected_type)
                    or not response.read(1)):
                return False
        except (OSError, http.client.HTTPException):
            return False
        finally:
            connection.close()
    return True


def publish_when_ready(ipc, pipe, server, port, stop):
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline and not stop.is_set():
        if server.started and check_web(port):
            try:
                ipc.publish_port(pipe, port, stop)
            except pywintypes.error:
                server.should_exit = True
            return
        stop.wait(0.05)
    server.should_exit = True


def run_node(ipc):
    with ipc.claim_node() as claimed:
        if not claimed:
            return 0

        settings = NodeSettings.load()
        ipc.create_data_dir(settings.data_dir, NODE_DATABASE_NAME)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, ipc.create_pipe() as pipe:
            port = bind_loopback(listener, settings.port)
            app = prepare_node(settings, port)
            server = uvicorn.Server(uvicorn.Config(
                app, loop="asyncio", http="h11", proxy_headers=False, log_config=None, access_log=False,
            ))
            stop = threading.Event()
            publisher = threading.Thread(target=publish_when_ready, args=(ipc, pipe, server, port, stop))
            publisher.start()
            try:
                server.run(sockets=[listener])
            finally:
                stop.set()
                publisher.join()
            return 0 if server.started else 2


def get_node_port(ipc, *, timeout=START_TIMEOUT):
    port = ipc.read_port(0.25)
    if port is not None:
        return port

    executable = Path(sys.executable).with_name(EXECUTABLE)
    process = subprocess.Popen(
        [str(executable), "--node"],
        cwd=executable.parent,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
    )
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        port = ipc.read_port(min(0.25, remaining))
        if port is not None:
            return port
        if process.poll() == EXIT_DATA_PERMISSION:
            raise NodeDataPermissionError()
        time.sleep(0.05)
    raise NodeStartupTimeout(f"Ratatoss chưa báo sẵn sàng sau {timeout} giây. Hãy thử lại.")


def message_box(message, flags):
    return ctypes.windll.user32.MessageBoxW(None, message, "Ratatoss", flags)


def startup_error(exc):
    if isinstance(exc, NodeStartupTimeout):
        return str(exc)
    return DATA_PERMISSION_ERROR if isinstance(exc, NodeDataPermissionError) else START_ERROR


def open_web(port, *, terminal):
    url = f"http://{LOOPBACK}:{port}/"
    while True:
        try:
            # Restore the Windows DLL search order for the external browser.
            runtime = getattr(sys, "_MEIPASS", None)
            if runtime is not None:
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                os.startfile(url)
            finally:
                if runtime is not None:
                    ctypes.windll.kernel32.SetDllDirectoryW(ctypes.c_wchar_p(runtime))
            return True
        except OSError:
            message = f"Không mở được trình duyệt. Hãy mở địa chỉ này thủ công:\n{url}"
            if terminal:
                print(message, flush=True)
                return False
            if message_box(message, 0x15) != 4:  # MB_RETRYCANCEL | MB_ICONWARNING, IDRETRY
                return False


def terminal_menu(ipc):
    while True:
        print("\n1. Mở giao diện web\n2. Kiểm tra trạng thái\n3. Đóng menu", flush=True)
        try:
            choice = input("Chọn 1, 2 hoặc 3: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if choice == "3":
            return 0
        if choice not in ("1", "2"):
            continue
        try:
            port = get_node_port(ipc)
        except (OSError, pywintypes.error) as exc:
            print(startup_error(exc), flush=True)
            continue
        if choice == "1":
            open_web(port, terminal=True)
        else:
            print(f"Ratatoss đang chạy · http://{LOOPBACK}:{port}/", flush=True)
            print("Starter · Chưa kết nối điều phối", flush=True)


def main():
    ipc = NodeIPC()
    if sys.argv[1:] == ["--node"]:
        try:
            return run_node(ipc)
        except NodeDataPermissionError:
            return EXIT_DATA_PERMISSION
        except (OSError, ValueError, sqlite3.Error, pywintypes.error):
            return 2

    if Path(sys.executable).stem.lower() == "ratatoss-terminal":
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(encoding="utf-8")
        try:
            get_node_port(ipc)
        except (OSError, pywintypes.error) as exc:
            print(startup_error(exc), flush=True)
        return terminal_menu(ipc)

    timeout = SETUP_START_TIMEOUT if sys.argv[1:] == ["--from-setup"] else START_TIMEOUT
    while True:
        try:
            return 0 if open_web(get_node_port(ipc, timeout=timeout), terminal=False) else 1
        except (OSError, pywintypes.error) as exc:
            if message_box(startup_error(exc), 0x15) != 4:
                return 2


if __name__ == "__main__":
    raise SystemExit(main())
