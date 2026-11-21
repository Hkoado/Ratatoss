"""Prepare a Windows loopback lab with three isolated Croc endpoints for R0.2."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from ratatoss._croc_process import WindowsChild
from ratatoss.transport import (
    Batch, COMMON_FLAGS, CROC_VERSION, WINDOWS_X64_SHA256, CrocAdapter, CrocError, RelayProfile,
    child_environment, sha256_file,
)
from scripts.croc_smoke import (
    FIXTURE_SHA256, FIXTURE_SIZE, HANDSHAKE_BUDGET_MS, HOST, PORTS, START_GAP_S, TIMEOUT_S,
    new_code, require, wait_for_relay,
)


TRANSFERS = (
    ("A", "B", "a-32mib.bin", FIXTURE_SHA256),
    ("B", "C", "b-to-c-32mib.bin", "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679"),
)
MIN_GOODPUT_BPS = 100_000_000
VERIFY_COMMIT_MS = 200
MARGIN_MS = 200


async def check_path(sender, receiver, fixture, destination, digest, code):
    batch = Batch(uuid4(), FIXTURE_SIZE, digest)
    deadline = time.monotonic() + TIMEOUT_S
    async with asyncio.TaskGroup() as tasks:
        rx = tasks.create_task(receiver.receive(
            destination, code, batch=batch, timeout=TIMEOUT_S, lease_deadline=deadline,
            remaining_setup_ms=receiver.relay.setup_ms,
        ))
        await asyncio.sleep(START_GAP_S)
        tx = tasks.create_task(sender.send(
            fixture, code, batch=batch, timeout=TIMEOUT_S, lease_deadline=deadline,
            remaining_setup_ms=HANDSHAKE_BUDGET_MS,
        ))
    processes = {"rx": rx.result(), "tx": tx.result()}
    for process in processes.values():
        require(process.exit_code == 0 and process.job.active_after_stop == 0
                and not process.staging_cleanup_pending, "LAB_CHILD_NOT_CLEAN")
    received = sha256_file(destination)
    require(destination.stat().st_size == FIXTURE_SIZE and received == digest, "LAB_HASH_MISMATCH")
    return {
        "fixture_sha256": digest, "received_sha256": received, "bytes": FIXTURE_SIZE,
        "processes": {role: {
            "exit_code": process.exit_code, "children_after_stop": process.job.active_after_stop,
            "started_monotonic_s": process.started_monotonic, "stopped_monotonic_s": process.stopped_monotonic,
        } for role, process in processes.items()},
    }


async def check_lab(executable, fixtures, area):
    password = secrets.token_hex(24)
    profile = RelayProfile(f"{HOST}:{PORTS[0]}", password, MIN_GOODPUT_BPS,
                           round(START_GAP_S * 1000) + HANDSHAKE_BUDGET_MS, VERIFY_COMMIT_MS, MARGIN_MS)
    roots = {role: area / uuid4().hex for role in "ABC"}
    for path in roots.values():
        path.mkdir()
    peers = {role: CrocAdapter(executable, path, profile) for role, path in roots.items()}
    endpoints = {role: hashlib.sha256(path.name.encode("ascii")).hexdigest() for role, path in roots.items()}

    relay_root = area / "relay"
    relay_root.mkdir()
    argv = [str(executable), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
    relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
    rooms = set()
    try:
        listeners = wait_for_relay(relay)
        async with asyncio.TaskGroup() as group:
            tasks = {}
            for source, destination, name, digest in TRANSFERS:
                fixture = fixtures / name
                require(fixture.stat().st_size == FIXTURE_SIZE and sha256_file(fixture) == digest,
                        "LAB_FIXTURE_MISMATCH")
                tasks[f"{source}-{destination}"] = group.create_task(check_path(
                    peers[source], peers[destination], fixture, area / f"{destination}-{name}",
                    digest, new_code(rooms),
                ))
    finally:
        cleanup = relay.stop()
    require(cleanup.active_after_stop == 0, "LAB_RELAY_NOT_CLEAN")
    return endpoints, listeners, {pair: task.result() for pair, task in tasks.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--croc", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory for sanitized evidence")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This lab requires Windows")
    if args.output.exists():
        parser.error("The output directory must be new")
    try:
        executable = args.croc.resolve(strict=True)
        require(sha256_file(executable) == WINDOWS_X64_SHA256, "LAB_CROC_PIN_MISMATCH")
        with tempfile.TemporaryDirectory() as area:
            endpoints, listeners, transfers = asyncio.run(check_lab(executable, args.fixtures.resolve(), Path(area)))
    except (CrocError, OSError, ExceptionGroup) as error:
        parser.exit(1, f"Lab preflight failed ({error.code if isinstance(error, CrocError) else type(error).__name__}).\n")

    records = {
        "endpoints.json": endpoints,
        "profile.json": {"croc_version": CROC_VERSION, "croc_sha256": WINDOWS_X64_SHA256,
                         "relay_config": "relay.json", "network_profile": "network.json"},
        "relay.json": {"host": HOST, "ports": PORTS, "listeners_verified": listeners,
                       "transport": "relay", "authentication": "random per run", "children_after_stop": 0},
        "network.json": {"profile": "windows-ipv4-loopback", "topology": "A→relay→B; B→relay→C",
                         "physical_hosts": 1, "endpoint_workspaces": 3, "direct_lan_or_wan_measured": False,
                         "start_gap_s": START_GAP_S, "timeout_s": TIMEOUT_S,
                         "lease_budget_config": {"min_goodput_bps": MIN_GOODPUT_BPS,
                                                 "handshake_ms": HANDSHAKE_BUDGET_MS,
                                                 "verify_commit_ms": VERIFY_COMMIT_MS, "margin_ms": MARGIN_MS}},
        "report.json": {"status": "pass", "commit": subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], text=True).strip(),
                        "os": platform.system(), "os_version": platform.version(),
                        "architecture": platform.machine(), "python": platform.python_version(),
                        "transfers": transfers, "payload_overlap_measured": False},
    }
    args.output.mkdir(parents=True)
    for name, record in records.items():
        (args.output / name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Lab preflight passed: A to B and B to C verified SHA-256; relay and child processes cleaned up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
