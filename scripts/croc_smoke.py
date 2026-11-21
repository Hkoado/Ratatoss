"""Exercise Ratatoss with the pinned Windows Croc and a local test relay."""

import argparse
import asyncio
import ctypes
import json
import os
import platform
import secrets
import socket
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from ratatoss._croc_process import WindowsChild
from ratatoss.transport import (
    COMMON_FLAGS, CROC_VERSION, WINDOWS_X64_SHA256, Batch, CrocAdapter, CrocError,
    RelayProfile, child_environment, sha256_file,
)

HOST = "127.0.0.1"
PORTS = (19009, 19010)
FIXTURE_SIZE = 32 * 1024 * 1024
FIXTURE_SHA256 = "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a"
START_GAP_S = 0.75
HANDSHAKE_BUDGET_MS = 200
TIMEOUT_S = 25
FAULT_TIMEOUT_S = 6
NO_PEER_TIMEOUT_S = 4.5
THROTTLE = "512k"


class ThrottledAdapter(CrocAdapter):
    def argv(self, role, batch):
        argv = super().argv(role, batch)
        if role == "tx":
            argv[1:1] = ["--throttleUpload", THROTTLE]
        return argv


def wait_for_relay(relay):
    netstat = Path(os.environ["SystemRoot"]) / "System32" / "netstat.exe"
    expected = {f"{HOST}:{port}" for port in PORTS}
    deadline = time.monotonic() + 5
    while relay.poll() is None and time.monotonic() < deadline:
        result = subprocess.run(
            [netstat, "-ano", "-p", "TCP"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=3, check=True, text=True, errors="replace",
        )
        rows = [line.split() for line in result.stdout.splitlines()]
        owned = {row[1] for row in rows if len(row) == 5 and row[-1] == str(relay.pid)}
        if owned == expected:
            for port in PORTS:
                with socket.create_connection((HOST, port), timeout=1):
                    pass
            return sorted(owned)
        time.sleep(0.05)
    raise CrocError("LAB_RELAY_NOT_READY")


def require(condition, code):
    if not condition:
        raise CrocError(code)


def new_code(rooms):
    while True:
        room = str(1000 + secrets.randbelow(9000))
        if room not in rooms:
            rooms.add(room)
            return room + "-" + "-".join(secrets.token_hex(6) for _ in range(3))


def redact(argv):
    return ["CROC", *argv[1:]]


async def run_case(label, adapter, fixture, destination, cases, rooms, *, first="rx",
                   timeout=TIMEOUT_S, omit_tx=False, retry_of=None):
    batch = Batch(uuid4(), FIXTURE_SIZE, FIXTURE_SHA256)
    code = new_code(rooms)
    lease_deadline = time.monotonic() + timeout
    case = {
        "name": label, "status": "fail", "attempt_id": str(batch.attempt_id),
        "retry_of": retry_of, "timeout_s": timeout, "lease_deadline_monotonic": lease_deadline,
        "roles": {},
    }
    cases.append(case)

    async def start(role):
        setup_ms = adapter.relay.setup_ms if role == first else HANDSHAKE_BUDGET_MS
        outcome = {"argv": redact(adapter.argv(role, batch)), "remaining_setup_ms": setup_ms}
        case["roles"][role] = outcome
        fn, path = (adapter.send, fixture) if role == "tx" else (adapter.receive, destination)
        try:
            outcome["process"] = asdict(await fn(
                path, code, batch=batch, timeout=timeout, lease_deadline=lease_deadline,
                remaining_setup_ms=setup_ms,
            ))
            outcome["status"] = "ok"
        except CrocError as exc:
            outcome["status"] = exc.code
            outcome["process"] = asdict(exc.process) if exc.process else None
            outcome["partial_isolated"] = exc.partial_isolated
            outcome["staging_cleanup_pending"] = exc.staging_cleanup_pending

    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(start(first))
        if not omit_tx:
            await asyncio.sleep(START_GAP_S)
            tasks.create_task(start("tx" if first == "rx" else "rx"))

    for outcome in case["roles"].values():
        process = outcome["process"]
        require(process and process["job"]["active_after_stop"] == 0, "LAB_PROCESS_NOT_REAPED")
        require(
            not process["staging_cleanup_pending"] and not outcome.get("staging_cleanup_pending"),
            "LAB_STAGING_CLEANUP_PENDING",
        )
    case["destination_exists"] = destination.is_file()
    return case, batch


def check_success(case, destination, first):
    roles = case["roles"]
    for outcome in roles.values():
        require(outcome["status"] == "ok" and outcome["process"]["exit_code"] == 0, "LAB_CHILD_FAILED")
    first_run = roles[first]["process"]
    second_run = roles["tx" if first == "rx" else "rx"]["process"]
    require(
        first_run["started_monotonic"] < second_run["started_monotonic"] < first_run["stopped_monotonic"],
        "LAB_START_ORDER_FAILED",
    )
    require(case["destination_exists"], "LAB_DESTINATION_MISSING")
    case["received_sha256"] = sha256_file(destination)
    case["received_bytes"] = destination.stat().st_size
    require(case["received_sha256"] == FIXTURE_SHA256, "LAB_HASH_MISMATCH")
    case["status"] = "pass"


async def simulate(executable, fixture, area, report):
    require(fixture.stat().st_size == FIXTURE_SIZE, "LAB_FIXTURE_SIZE_MISMATCH")
    require(sha256_file(fixture) == FIXTURE_SHA256, "LAB_FIXTURE_HASH_MISMATCH")
    password = secrets.token_hex(24)
    setup_ms = round(START_GAP_S * 1000) + HANDSHAKE_BUDGET_MS
    profile = RelayProfile(f"{HOST}:{PORTS[0]}", password, 100_000_000, setup_ms, 200, 200)
    report["profile"] = {
        "name": "lab-windows-loopback", "endpoint": profile.endpoint, "ports": PORTS,
        "min_goodput_bps": profile.min_goodput_bps, "setup_ms": profile.setup_ms,
        "verify_commit_ms": profile.verify_commit_ms, "margin_ms": profile.margin_ms,
        "route": "unknown", "start_gap_s": START_GAP_S, "fault_upload_limit": THROTTLE,
    }
    adapter_root = area / "attempts"
    adapter_root.mkdir()
    adapter = CrocAdapter(executable, adapter_root, profile)
    throttled = ThrottledAdapter(executable, adapter_root, profile)
    report["croc"] = {
        "version": CROC_VERSION, "sha256": sha256_file(executable),
        "probes_passed": ["--version", "--help", "send --help", "relay --help"],
    }
    relay_root = area / "relay"
    relay_root.mkdir()
    args = [
        str(executable), *COMMON_FLAGS, "relay", "--host", HOST, "--ports",
        ",".join(map(str, PORTS)),
    ]
    report["relay"] = {"argv": redact(args)}
    clipboard = ctypes.windll.user32.GetClipboardSequenceNumber
    clipboard_before = clipboard()
    relay = WindowsChild(args, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
    try:
        report["relay"]["listeners"] = wait_for_relay(relay)
        cases = report["cases"]
        rooms = set()
        for first in ("rx", "tx"):
            dest = area / f"{first}-first.bin"
            case, _ = await run_case(f"{first}-first", adapter, fixture, dest, cases, rooms, first=first)
            check_success(case, dest, first)

        dest = area / "retried.bin"
        case, _ = await run_case(
            "rx-without-tx", adapter, fixture, dest, cases, rooms, timeout=NO_PEER_TIMEOUT_S, omit_tx=True,
        )
        rx = case["roles"]["rx"]
        require(rx["status"] == "TRANSPORT_TIMEOUT" and not case["destination_exists"], "LAB_NO_PEER_FAILED")
        require(rx["process"]["job"]["active_before_stop"] >= 1, "LAB_RX_ALREADY_EXITED")
        case["status"] = "pass"

        case, batch = await run_case(
            "partial-rx-timeout", throttled, fixture, dest, cases, rooms, timeout=FAULT_TIMEOUT_S,
        )
        rx = case["roles"]["rx"]
        require(rx["status"] == "TRANSPORT_TIMEOUT" and not case["destination_exists"], "LAB_PARTIAL_TIMEOUT_FAILED")
        require(case["roles"]["tx"]["status"] == "TRANSPORT_TIMEOUT", "LAB_TX_TIMEOUT_FAILED")
        require(rx["process"]["job"]["active_before_stop"] >= 1, "LAB_RX_ALREADY_EXITED")
        require(rx["partial_isolated"], "LAB_PARTIAL_NOT_ISOLATED")
        partial = adapter_root / batch.attempt_id.hex / "rx" / "quarantine" / batch.filename
        with partial.open("rb") as stream:
            prefix = stream.read(64 * 1024)
        with fixture.open("rb") as stream:
            require(bool(prefix) and prefix == stream.read(len(prefix)), "LAB_PARTIAL_BYTES_MISSING")
        case["quarantined_file_size"] = partial.stat().st_size
        case["quarantined_sha256"] = sha256_file(partial)
        require(case["quarantined_sha256"] != FIXTURE_SHA256, "LAB_TRANSFER_WAS_COMPLETE")
        case["status"] = "pass"

        retry, retried = await run_case(
            "retry", adapter, fixture, dest, cases, rooms, retry_of=str(batch.attempt_id),
        )
        require(retried.attempt_id != batch.attempt_id, "LAB_ATTEMPT_REUSED")
        check_success(retry, dest, "rx")
        require(
            all(sha256_file(area / f"{first}-first.bin") == FIXTURE_SHA256 for first in ("rx", "tx")),
            "LAB_COMMITTED_BATCH_CHANGED",
        )
        report["previous_verified_files_preserved"] = True
    finally:
        report["relay"]["cleanup"] = asdict(relay.stop())
        report["clipboard_sequence_unchanged"] = clipboard() == clipboard_before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--croc", type=Path, required=True, help="absolute path to the pinned .exe")
    parser.add_argument("--fixture", type=Path, required=True, help="the #3 synthetic a-32mib.bin fixture")
    parser.add_argument("--work-parent", type=Path, required=True, help="absolute path to a private lab directory")
    parser.add_argument("--report", type=Path, required=True, help="write the sanitized JSON report to a new file")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This profile requires Windows")
    report = {
        "status": "fail", "os": platform.system(), "os_version": platform.version(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "tree_clean": not subprocess.check_output(["git", "status", "--porcelain"], text=True).strip(),
        "fixture": {"bytes": FIXTURE_SIZE, "expected_sha256": FIXTURE_SHA256},
        "expected_croc_sha256": WINDOWS_X64_SHA256,
        "cases": [],
    }
    with args.report.open("x", encoding="utf-8") as output:
        try:
            with tempfile.TemporaryDirectory(dir=args.work_parent) as temp:
                asyncio.run(simulate(args.croc, args.fixture, Path(temp), report))
            report["status"] = "pass"
        except CrocError as exc:
            report["error"] = exc.code
        except (OSError, ExceptionGroup) as exc:
            report["error"] = type(exc).__name__
        finally:
            output.write(json.dumps(report, indent=2) + "\n")
    print(report["status"], report.get("error", "R0.1 Croc smoke"))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
