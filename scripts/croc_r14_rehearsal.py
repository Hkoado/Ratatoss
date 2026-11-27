"""Rehearse the #60 Croc routes on an isolated Docker bridge."""

import argparse
import asyncio
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import tempfile
import time

from scripts.croc_r02_tap import RelayTap
from scripts.croc_smoke import new_code

SIZE = 32 * 1024 * 1024
FIXTURES = {
    "a-32mib.bin": "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a",
    "b-to-c-32mib.bin": "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679",
}
CROC_SHA256 = "93648f374ef5dcdb9e64d78ca9729f13af3e723312db44278970695be877f2d2"
IMAGE = "python:3.11-alpine@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1"
PORTS = (19009, 19010)
RX_TAP = "127.0.0.2"
TX_TAP = "127.0.0.3"
THROTTLE = "8M"
COMMON_FLAGS = ("--disable-clipboard", "--no-update-check", "--no-compress")
TX_FLAGS = ("--no-local", "--transport", "relay", "--no-multi")
CASES = {
    "bc": (("B", "C", "b-to-c-32mib.bin"),),
    "cb": (("C", "B", "b-to-c-32mib.bin"),),
    "ab_bc": (("A", "B", "a-32mib.bin"), ("B", "C", "b-to-c-32mib.bin")),
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def docker(*args, **kwargs):
    return subprocess.check_output(["docker", *args], text=True, timeout=20, **kwargs).strip()


async def observe(directory):
    receiver = RelayTap(RX_TAP, "relay", PORTS, transmit=False)
    sender = RelayTap(TX_TAP, "relay", PORTS, transmit=True)
    async with receiver.listen(), sender.listen():
        (directory / "observer-ready").touch()
        while not (directory / "observer-stop").exists():
            await asyncio.sleep(0.05)
    intervals = {"rx": receiver.interval(SIZE), "tx": sender.interval(SIZE)}
    print(json.dumps({role: asdict(value) if value else None for role, value in intervals.items()}))


def stop_process(process):
    if process.poll() is None:
        process.kill()
        process.wait()


def start(stack, *args, env=None, observe_stdout=False):
    process = subprocess.Popen(["docker", "exec", *args], env=env, text=True,
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE if observe_stdout else subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    if process.stdout:
        stack.callback(process.stdout.close)
    stack.callback(stop_process, process)
    return process


def croc_transfer(stack, node, folder, session, password, relay, filename=None):
    env = {**os.environ, "CROC_SECRET": session, "CROC_PASS": password}
    args = ["/croc", *COMMON_FLAGS, "--relay", f"{relay}:{PORTS[0]}"]
    if filename is None:
        args.append("--yes")
    else:
        args[1:1] = ["--throttleUpload", THROTTLE]
        args += ["send", *TX_FLAGS, f"/fixtures/{filename}"]
    return start(stack, "-e", "CROC_SECRET", "-e", "CROC_PASS",
                 "-e", f"CROC_CONFIG_DIR={folder}", "-w", folder, node, *args, env=env)


def run_case(root, nodes, password, name, transfers):
    directory = root / name
    directory.mkdir()
    with ExitStack() as stack:
        observer = start(stack, nodes["B"], "python", "-B", "-m", "scripts.croc_r14_rehearsal",
                         "--observe", f"/lab/{name}", observe_stdout=True)
        deadline = time.monotonic() + 8
        while not (directory / "observer-ready").exists():
            if observer.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("B observer did not start")
            time.sleep(0.05)
        processes = []
        senders = []
        received = {}
        rooms = set()
        for source, target, filename in transfers:
            lane = f"{source}-{target}"
            session = new_code(rooms)
            for role in ("rx", "tx"):
                (directory / f"{lane}-{role}").mkdir()
            rx = croc_transfer(stack, nodes[target], f"/lab/{name}/{lane}-rx", session, password,
                               RX_TAP if target == "B" else "relay")
            received[lane] = (directory / f"{lane}-rx" / filename, filename)
            processes.append((lane, "rx", rx))
            senders.append((lane, source, session, filename))
        time.sleep(0.5)
        for lane, source, session, filename in senders:
            tx = croc_transfer(stack, nodes[source], f"/lab/{name}/{lane}-tx", session, password,
                               TX_TAP if source == "B" else "relay", filename)
            processes.append((lane, "tx", tx))
        deadline = time.monotonic() + 45
        for lane, role, process in processes:
            if process.wait(timeout=max(0, deadline - time.monotonic())) != 0:
                raise RuntimeError(f"{name} {lane} {role} failed")
        (directory / "observer-stop").touch()
        output, _ = observer.communicate(timeout=10)
        if observer.returncode != 0:
            raise RuntimeError("B observer failed")
        intervals = json.loads(output)

    results = {}
    for lane, (path, filename) in received.items():
        checksum = digest(path)
        if path.stat().st_size != SIZE or checksum != FIXTURES[filename]:
            raise RuntimeError(f"{name} {lane} received file differs from the fixture")
        results[lane] = {"route": "relay", "bytes": SIZE, "received_sha256": checksum}
    expected_directions = {
        role for role, index in (("tx", 0), ("rx", 1)) if any(item[index] == "B" for item in transfers)
    }
    if any(intervals[role] is None for role in expected_directions):
        raise RuntimeError(f"{name} did not capture all expected payload intervals at B")
    overlap = None
    if intervals["rx"] and intervals["tx"]:
        rx, tx = intervals["rx"], intervals["tx"]
        overlap = max(0, min(rx["last_ns"], tx["last_ns"]) - max(rx["first_ns"], tx["first_ns"]))
    return {
        "transfers": results, "observed_intervals_at_b": intervals, "payload_overlap_at_b_ns": overlap,
    }


def rehearse(binary, fixtures):
    if digest(binary) != CROC_SHA256:
        raise ValueError("Wrong Linux ARM64 Croc v11.6.5 executable")
    for name, expected in FIXTURES.items():
        fixture = fixtures / name
        if fixture.stat().st_size != SIZE or digest(fixture) != expected:
            raise ValueError(f"Fixture mismatch for {name}")
    token = "ratatoss-r14-" + secrets.token_hex(5)
    repo = Path(__file__).resolve().parents[1]
    password = secrets.token_hex(24)
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory).resolve()
        docker("network", "create", "--internal", token)
        stack.callback(docker, "network", "rm", token)
        nodes = {}
        for role in ("A", "B", "C", "relay"):
            node = f"{token}-{role.lower()}"
            docker("run", "-d", "--name", node, "--network", token, "--network-alias", role.lower(),
                   "--mount", f"type=bind,src={repo},dst=/work,readonly",
                   "--mount", f"type=bind,src={binary},dst=/croc,readonly",
                   "--mount", f"type=bind,src={fixtures},dst=/fixtures,readonly",
                   "--mount", f"type=bind,src={root},dst=/lab",
                   "--workdir", "/work", IMAGE, "sleep", "600")
            stack.callback(docker, "rm", "-f", node)
            nodes[role] = node
        relay = start(stack, "-e", "CROC_PASS", nodes["relay"], "/croc", *COMMON_FLAGS, "relay",
                      "--host", "0.0.0.0", "--ports", "19009,19010",
                      env={**os.environ, "CROC_PASS": password})
        for _ in range(5):
            if subprocess.run(
                ["docker", "exec", nodes["B"], "python", "-c",
                 "import socket; socket.create_connection(('relay', 19009), timeout=1).close()"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            ).returncode == 0:
                break
            if relay.poll() is not None:
                raise RuntimeError("Relay exited before opening its control port")
            time.sleep(0.2)
        else:
            raise RuntimeError("Relay did not open its control port")
        version = docker("exec", nodes["B"], "/croc", "--version")
        system = docker("exec", nodes["B"], "uname", "-srm")
        runs = {name: run_case(root, nodes, password, name, transfers) for name, transfers in CASES.items()}
        if relay.poll() is not None:
            raise RuntimeError("Relay stopped during rehearsal")
    return {
        "started_at": started, "host_os": platform.platform(), "physical_hosts": 1,
        "container_os": system, "image": IMAGE, "topology": "A/B/C và relay trên Docker internal bridge",
        "common_flags": COMMON_FLAGS, "sender_flags": TX_FLAGS, "upload_throttle": THROTTLE,
        "croc_version": version, "croc_sha256": CROC_SHA256, "relay_ports": PORTS,
        "observer": "RelayTap trong container B, time.monotonic_ns()",
        "runner_sha256": digest(Path(__file__)),
        "observer_sha256": digest(repo / "scripts/croc_r02_tap.py"),
        "temporary_containers_and_network_removed": True, "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observe", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--croc", type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.observe:
        asyncio.run(observe(args.observe))
        return
    if not (args.croc and args.fixtures and args.output):
        parser.error("--croc, --fixtures and --output are required")
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("--output must be a new file in an existing directory")
    result = rehearse(args.croc.resolve(strict=True), args.fixtures.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
