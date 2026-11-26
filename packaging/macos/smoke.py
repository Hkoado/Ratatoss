"""Install one exact DMG into a temporary home and exercise the frozen starter."""

import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
import platform
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

# The packaged Node inherits this seatbelt profile from its first launcher.
OFFLINE = ["/usr/bin/sandbox-exec", "-p", '(version 1)(allow default)(deny network-outbound)'
           '(allow network-outbound (remote ip "localhost:*") (remote unix-socket))']


def digest(path):
    with path.open("rb") as stream:
        checksum = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
        return checksum.hexdigest()


def request(port, path, headers=None):
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=4)) as client:
        client.request("GET", path, headers=headers or {})
        response = client.getresponse()
        return response.status, response.read()


def exercise(home, app, manifest):
    binary = app / "Contents/MacOS/Ratatoss"
    croc = binary.with_name("croc")
    assert digest(croc) == manifest["croc"]["executable_sha256"]
    for notice in manifest["licenses"]:
        assert (app / "Contents/Resources/licenses" / notice).stat().st_size
    subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
    # Exclude the build environment and system/developer tools from the launcher's PATH.
    env = {"HOME": str(home), "PATH": "/nonexistent", "TMPDIR": str(home)}
    common = dict(cwd=home, env=env, text=True, timeout=45)
    subprocess.run([*OFFLINE, sys.executable, "-I", "-c",
                    "import errno, socket; s=socket.socket(); s.settimeout(2); "
                    "assert s.connect_ex(('192.0.2.1', 443)) == errno.EPERM"], check=True, **common)
    assert subprocess.check_output([*OFFLINE, croc, "--version"], **common).strip() == (
        "croc version " + manifest["croc"]["version"])
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        configured = busy.getsockname()[1]
        env["RATATOSS_NODE_PORT"] = str(configured)

        def status():
            return subprocess.check_output([*OFFLINE, binary, "--status"], **common).strip()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            urls = list(pool.map(lambda _: status(), range(2)))
        assert urls[0] == urls[1], urls
        url = urlsplit(urls[0])
        assert url.scheme == "http" and url.hostname == "127.0.0.1" and url.port != configured
        assert status() == urls[0]
        menu = subprocess.check_output([*OFFLINE, binary, "--terminal"], input="2\n3\n", **common)
        assert urls[0] in menu
        for path, fragment in (("/", b"Ratatoss"), ("/style.css", b"{"), ("/api/health", b'"starter"')):
            code, data = request(url.port, path, {"Origin": urls[0].rstrip("/")})
            assert code == 200 and fragment in data, (path, code)
        for headers in ({"Host": f"127.0.0.1:{configured}"}, {"Origin": "https://example.invalid"}):
            assert request(url.port, "/", headers)[0] == 403
        state = home / "Library/Application Support/Ratatoss"
        db = state / "node.sqlite3"
        assert db.is_file() and not db.stat().st_mode & 0o077
        with closing(sqlite3.connect(db.as_uri() + "?mode=rw", uri=True)) as connection:
            assert connection.execute("PRAGMA application_id").fetchone() == (0x5241544E,)
            assert connection.execute("PRAGMA user_version").fetchone()[0] > 0

        # LaunchServices uses the same route as Finder. Capture the status of that instance.
        launch = ["/usr/bin/open", "-W", "-n", "--env", f"HOME={home}",
                  "--env", f"RATATOSS_NODE_PORT={configured}"]
        output = home / "finder-status.txt"
        subprocess.run([*launch, "--stdout", output, app, "--args", "--status"], check=True, timeout=45)
        assert output.read_text().strip() == urls[0]
        subprocess.run([*launch, app], check=True, timeout=45)
        assert status() == urls[0]
        assert len(test_workers(app)) == 1
        original_db = db.stat().st_ino
        stop_test_node(app)
        restarted = urlsplit(status())
        assert request(restarted.port, "/api/health")[0] == 200
        assert len(test_workers(app)) == 1 and db.stat().st_ino == original_db


def test_workers(app):
    # Only match the worker from this uniquely named temporary installation.
    prefix = str(app / "Contents/MacOS/Ratatoss") + " --node "
    rows = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    workers = []
    for row in rows.splitlines():
        fields = row.strip().split(maxsplit=1)
        if len(fields) == 2 and fields[1].startswith(prefix):
            workers.append(int(fields[0]))
    return workers


def stop_test_node(app):
    for pid in test_workers(app):
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while test_workers(app):
        if time.monotonic() >= deadline:
            raise TimeoutError("Test Node did not stop")
        time.sleep(0.1)


def smoke(image):
    manifest = json.loads(image.with_suffix(".manifest.json").read_text())
    assert os.getuid() != 0 and platform.machine() == "arm64"
    assert image.name == manifest["disk_image"]["file"] and digest(image) == manifest["disk_image"]["sha256"]
    with tempfile.TemporaryDirectory(prefix="ratatoss-install-") as tmp:
        home = Path(tmp).resolve()
        mount = home / "volume"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, image], check=True)
        try:
            app = home / "Applications/Ratatoss.app"
            app.parent.mkdir()
            subprocess.run(["ditto", mount / app.name, app], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", mount], check=True)
        try:
            exercise(home, app, manifest)
        finally:
            stop_test_node(app)
    print(f"Passed DMG installation, offline Node, HTTP and LaunchServices smoke on macOS {platform.mac_ver()[0]} arm64.")
    print(f"{image.name} sha256={manifest['disk_image']['sha256']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    smoke(parser.parse_args().image.resolve(strict=True))
