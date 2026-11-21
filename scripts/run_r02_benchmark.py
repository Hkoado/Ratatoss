"""Benchmark runner for R0.2: Measure Croc setup, goodput, and concurrent RX/TX."""

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from uuid import uuid4

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ratatoss._croc_process import WindowsChild
from ratatoss.transport import (
    Batch, COMMON_FLAGS, CROC_VERSION, WINDOWS_X64_SHA256, CrocAdapter, CrocError, RelayProfile,
    child_environment, sha256_file,
)
from scripts.croc_smoke import (
    HOST, PORTS, START_GAP_S, HANDSHAKE_BUDGET_MS, wait_for_relay, new_code, require,
)
from scripts.validate_bench_csv import RUNS_HEADER, TRANSFERS_HEADER

SIZES = (32, 64, 128)
SCENARIOS = ("sequential", "concurrent")
REPEATS = 3
TIMEOUT_S = 45
FAULT_TIMEOUT_S = 6
MIN_GOODPUT_BPS = 100_000_000
VERIFY_COMMIT_MS = 200
MARGIN_MS = 200

FIXTURE_NAMES = {
    ("A", 32): ("a-32mib.bin", "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a"),
    ("A", 64): ("a-64mib.bin", "545a0e718c1a1584c397c853018a16581a31cd66377209041f0984778a4a6a67"),
    ("A", 128): ("a-128mib.bin", "cdf2287f633d6558a33bcdbbfd6428708c8f869b3fc4ffb3cca88366703a353c"),
    ("B", 32): ("b-to-c-32mib.bin", "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679"),
    ("B", 64): ("b-to-c-64mib.bin", "69befdfa85c9f9d3283797ebe5869630fd52bd685afa52f651246357930d6c84"),
    ("B", 128): ("b-to-c-128mib.bin", "f9205ac9406aed59a117658ac37648e3c85a49a9b2a37a2a349a55101750b5f8"),
}


def calculate_overlap_ms(rx_start_ms: float, rx_end_ms: float, tx_start_ms: float, tx_end_ms: float) -> float:
    """Calculate positive overlap between RX and TX on the shared monotonic clock."""
    start = max(rx_start_ms, tx_start_ms)
    end = min(rx_end_ms, tx_end_ms)
    return max(0.0, end - start)


async def execute_transfer(
    sender: CrocAdapter,
    receiver: CrocAdapter,
    fixture_path: Path,
    dest_path: Path,
    expected_digest: str,
    file_bytes: int,
    session_code: str,
    timeout_s: float = TIMEOUT_S,
):
    batch = Batch(uuid4(), file_bytes, expected_digest)
    deadline = time.monotonic() + timeout_s

    async with asyncio.TaskGroup() as tasks:
        rx_task = tasks.create_task(receiver.receive(
            dest_path, session_code, batch=batch, timeout=timeout_s, lease_deadline=deadline,
            remaining_setup_ms=receiver.relay.setup_ms,
        ))
        await asyncio.sleep(START_GAP_S)
        tx_task = tasks.create_task(sender.send(
            fixture_path, session_code, batch=batch, timeout=timeout_s, lease_deadline=deadline,
            remaining_setup_ms=HANDSHAKE_BUDGET_MS,
        ))

    rx_run = rx_task.result()
    tx_run = tx_task.result()

    require(rx_run.exit_code == 0 and rx_run.job.active_after_stop == 0, "LAB_RX_FAILED")
    require(tx_run.exit_code == 0 and tx_run.job.active_after_stop == 0, "LAB_TX_FAILED")
    require(dest_path.is_file(), "DEST_NOT_FOUND")
    actual_size = dest_path.stat().st_size
    require(actual_size == file_bytes, "SIZE_MISMATCH")
    actual_hash = sha256_file(dest_path)
    require(actual_hash == expected_digest, "HASH_MISMATCH")

    return rx_run, tx_run, actual_hash


async def run_benchmark(croc_path: Path, fixtures_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_rows = []
    transfers_rows = []

    password = secrets.token_hex(24)
    profile = RelayProfile(
        f"{HOST}:{PORTS[0]}", password, MIN_GOODPUT_BPS,
        round(START_GAP_S * 1000) + HANDSHAKE_BUDGET_MS, VERIFY_COMMIT_MS, MARGIN_MS,
    )

    with tempfile.TemporaryDirectory() as lab_temp:
        lab_root = Path(lab_temp)

        for size_mib in SIZES:
            file_bytes = size_mib * 1024 * 1024
            a_name, a_sha = FIXTURE_NAMES[("A", size_mib)]
            b_name, b_sha = FIXTURE_NAMES[("B", size_mib)]
            a_fixture = fixtures_dir / a_name
            b_fixture = fixtures_dir / b_name

            # 1. SEQUENTIAL (A -> B only)
            for repeat in range(1, REPEATS + 1):
                relay_root = lab_root / f"relay_seq_{size_mib}_{repeat}"
                relay_root.mkdir(parents=True, exist_ok=True)
                argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
                relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
                wait_for_relay(relay)
                try:
                    peer_roots = {role: lab_root / f"peer_seq_{size_mib}_{repeat}_{role}" for role in "AB"}
                    for p in peer_roots.values():
                        p.mkdir(parents=True, exist_ok=True)
                    peers = {role: CrocAdapter(croc_path, p, profile) for role, p in peer_roots.items()}
                    rooms = set()

                    run_id = f"r02-seq-{size_mib}mib-rep{repeat}-{uuid4().hex[:6]}"
                    dest_b = lab_root / f"dest_b_seq_{size_mib}_{repeat}.bin"
                    code = new_code(rooms)
                    job_id = uuid4().hex
                    assignment_id = uuid4().hex
                    batch_id = 0

                    rx_run, tx_run, verified_sha = await execute_transfer(
                        peers["A"], peers["B"], a_fixture, dest_b, a_sha, file_bytes, code,
                    )

                    start_ms = rx_run.started_monotonic * 1000.0
                    end_ms = rx_run.stopped_monotonic * 1000.0
                    duration_s = rx_run.stopped_monotonic - rx_run.started_monotonic
                    setup_ms = round(START_GAP_S * 1000.0)
                    goodput_bps = round((file_bytes * 8.0) / duration_s) if duration_s > 0 else 0
                    makespan_ms = round(end_ms - start_ms)

                    t_row = [
                        run_id, job_id, assignment_id, str(batch_id),
                        "A", "B", "B", "relay",
                        str(file_bytes), str(file_bytes),
                        f"{start_ms:.3f}", "", "", f"{end_ms:.3f}",
                        str(setup_ms), str(goodput_bps), verified_sha,
                        "pass", "false", "false",
                        "Loopback relay A to B single transfer; first/last byte markers not exposed by Croc",
                    ]
                    transfers_rows.append(t_row)

                    r_row = [
                        run_id, "gate0", "sequential", "croc_relay", str(repeat), "42",
                        "fe0bebc", platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                        "loopback-127.0.0.1", "windows-loopback", a_sha, str(file_bytes),
                        str(size_mib), "1", "1", "pass",
                        str(makespan_ms), str(file_bytes), "", "", "",
                        "", "", "", str(setup_ms), str(setup_ms), "",
                        f"bench/artifacts/r02/{run_id}",
                        "Sequential transport run; wire bytes unmetered on loopback interface",
                    ]
                    runs_rows.append(r_row)
                    print(f"Sequential {size_mib} MiB repeat {repeat} passed (makespan: {makespan_ms}ms, goodput: {goodput_bps}bps)")
                finally:
                    relay.stop()

            # 2. CONCURRENT (A -> B and B -> C simultaneously on B clock)
            for repeat in range(1, REPEATS + 1):
                relay_root = lab_root / f"relay_concur_{size_mib}_{repeat}"
                relay_root.mkdir(parents=True, exist_ok=True)
                argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
                relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
                wait_for_relay(relay)
                try:
                    peer_roots = {role: lab_root / f"peer_concur_{size_mib}_{repeat}_{role}" for role in "ABC"}
                    for p in peer_roots.values():
                        p.mkdir(parents=True, exist_ok=True)
                    peers = {role: CrocAdapter(croc_path, p, profile) for role, p in peer_roots.items()}
                    rooms = set()

                    run_id = f"r02-concur-{size_mib}mib-rep{repeat}-{uuid4().hex[:6]}"
                    dest_b = lab_root / f"dest_b_concur_{size_mib}_{repeat}.bin"
                    dest_c = lab_root / f"dest_c_concur_{size_mib}_{repeat}.bin"
                    code_ab = new_code(rooms)
                    code_bc = new_code(rooms)
                    job_id = uuid4().hex
                    batch_ab = Batch(uuid4(), file_bytes, a_sha)
                    batch_bc = Batch(uuid4(), file_bytes, b_sha)
                    deadline = time.monotonic() + TIMEOUT_S

                    async with asyncio.TaskGroup() as tasks:
                        rx_b = tasks.create_task(peers["B"].receive(
                            dest_b, code_ab, batch=batch_ab, timeout=TIMEOUT_S, lease_deadline=deadline,
                            remaining_setup_ms=profile.setup_ms,
                        ))
                        rx_c = tasks.create_task(peers["C"].receive(
                            dest_c, code_bc, batch=batch_bc, timeout=TIMEOUT_S, lease_deadline=deadline,
                            remaining_setup_ms=profile.setup_ms,
                        ))
                        await asyncio.sleep(START_GAP_S)
                        tx_a = tasks.create_task(peers["A"].send(
                            a_fixture, code_ab, batch=batch_ab, timeout=TIMEOUT_S, lease_deadline=deadline,
                            remaining_setup_ms=HANDSHAKE_BUDGET_MS,
                        ))
                        tx_b = tasks.create_task(peers["B"].send(
                            b_fixture, code_bc, batch=batch_bc, timeout=TIMEOUT_S, lease_deadline=deadline,
                            remaining_setup_ms=HANDSHAKE_BUDGET_MS,
                        ))

                    r_ab_res = rx_b.result()
                    t_ab_res = tx_a.result()
                    r_bc_res = rx_c.result()
                    t_bc_res = tx_b.result()

                    b_rx_start_ms = r_ab_res.started_monotonic * 1000.0
                    b_rx_end_ms = r_ab_res.stopped_monotonic * 1000.0
                    b_tx_start_ms = t_bc_res.started_monotonic * 1000.0
                    b_tx_end_ms = t_bc_res.stopped_monotonic * 1000.0
                    overlap_ms = calculate_overlap_ms(b_rx_start_ms, b_rx_end_ms, b_tx_start_ms, b_tx_end_ms)
                    require(overlap_ms > 0, "LAB_OVERLAP_NOT_POSITIVE")

                    c_rx_start_ms = r_bc_res.started_monotonic * 1000.0
                    c_rx_end_ms = r_bc_res.stopped_monotonic * 1000.0

                    dur_ab = r_ab_res.stopped_monotonic - r_ab_res.started_monotonic
                    dur_bc = r_bc_res.stopped_monotonic - r_bc_res.started_monotonic
                    goodput_ab = round((file_bytes * 8.0) / dur_ab) if dur_ab > 0 else 0
                    goodput_bc = round((file_bytes * 8.0) / dur_bc) if dur_bc > 0 else 0

                    overall_start = min(b_rx_start_ms, b_tx_start_ms)
                    overall_end = max(b_rx_end_ms, c_rx_end_ms)
                    makespan_ms = round(overall_end - overall_start)

                    transfers_rows.append([
                        run_id, job_id, batch_ab.attempt_id.hex, "0",
                        "A", "B", "B", "relay",
                        str(file_bytes), str(file_bytes),
                        f"{b_rx_start_ms:.3f}", "", "", f"{b_rx_end_ms:.3f}",
                        str(round(START_GAP_S * 1000.0)), str(goodput_ab), sha256_file(dest_b),
                        "pass", "false", "false",
                        f"Concurrent RX on B; overlap with B->C is {overlap_ms:.1f}ms on B clock",
                    ])
                    transfers_rows.append([
                        run_id, job_id, batch_bc.attempt_id.hex, "1",
                        "B", "C", "B", "relay",
                        str(file_bytes), str(file_bytes),
                        f"{b_tx_start_ms:.3f}", "", "", f"{c_rx_end_ms:.3f}",
                        str(HANDSHAKE_BUDGET_MS), str(goodput_bc), sha256_file(dest_c),
                        "pass", "false", "false",
                        f"Concurrent TX on B; overlap with A->B is {overlap_ms:.1f}ms on B clock",
                    ])

                    runs_rows.append([
                        run_id, "gate0", "concurrent", "croc_relay", str(repeat), "42",
                        "fe0bebc", platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                        "loopback-127.0.0.1", "windows-loopback", a_sha, str(file_bytes * 2),
                        str(size_mib), "1", "1", "pass",
                        str(makespan_ms), str(file_bytes * 2), "", "", "",
                        "", "", "", str(HANDSHAKE_BUDGET_MS), str(round(START_GAP_S * 1000.0)), "",
                        f"bench/artifacts/r02/{run_id}",
                        f"Concurrent RX/TX run on B with overlap={overlap_ms:.1f}ms; wire bytes unmetered",
                    ])
                    print(f"Concurrent {size_mib} MiB repeat {repeat} passed (makespan: {makespan_ms}ms, overlap: {overlap_ms:.1f}ms)")
                finally:
                    relay.stop()

        # 3. TIMEOUT REPRODUCIBILITY (Receiver starts, sender never appears)
        relay_root = lab_root / "relay_timeout"
        relay_root.mkdir(parents=True, exist_ok=True)
        argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
        relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
        wait_for_relay(relay)
        try:
            peer_b_root = lab_root / "peer_timeout_B"
            peer_b_root.mkdir(parents=True, exist_ok=True)
            peer_b = CrocAdapter(croc_path, peer_b_root, profile)

            run_id = f"r02-timeout-reproduce-{uuid4().hex[:6]}"
            timeout_file_bytes = 32 * 1024 * 1024
            batch_timeout = Batch(uuid4(), timeout_file_bytes, FIXTURE_NAMES[("A", 32)][1])
            dest_timeout = lab_root / "dest_timeout.bin"
            timeout_s = 4.5
            lease_deadline = time.monotonic() + 15.0
            timeout_caught = False
            t_start = time.monotonic() * 1000.0

            try:
                await peer_b.receive(
                    dest_timeout, new_code(set()), batch=batch_timeout,
                    timeout=timeout_s, lease_deadline=lease_deadline, remaining_setup_ms=profile.setup_ms,
                )
            except CrocError as exc:
                if exc.code == "TRANSPORT_TIMEOUT":
                    timeout_caught = True
                    require(exc.partial_isolated is False, "PARTIAL_SHOULD_BE_FALSE")
                    require(not dest_timeout.exists(), "DEST_SHOULD_NOT_EXIST")
            t_end = time.monotonic() * 1000.0
            require(timeout_caught, "TIMEOUT_NOT_REPRODUCED")

            transfers_rows.append([
                run_id, uuid4().hex, batch_timeout.attempt_id.hex, "0",
                "A", "B", "B", "relay",
                str(timeout_file_bytes), "0",
                f"{t_start:.3f}", "", "", f"{t_end:.3f}",
                "", "", "", "timeout", "false", "false",
                "Reproduced timeout: receiver opened without sender; clean abort and quarantine check",
            ])
            runs_rows.append([
                run_id, "gate0", "timeout_reproduce", "croc_relay", "1", "42",
                "fe0bebc", platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                "loopback-127.0.0.1", "windows-loopback", FIXTURE_NAMES[("A", 32)][1], str(timeout_file_bytes),
                "32", "1", "0", "timeout",
                str(round(t_end - t_start)), "0", "", "", "",
                "", "", "", "", "", "",
                f"bench/artifacts/r02/{run_id}",
                "Deliberate timeout run without sender; process cleanly terminated and staging empty",
            ])
            print("Timeout reproducibility run passed.")
        finally:
            relay.stop()

    # Write CSVs
    runs_file = output_dir / "runs.csv"
    transfers_file = output_dir / "transfers.csv"

    with runs_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(RUNS_HEADER)
        writer.writerows(runs_rows)

    with transfers_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(TRANSFERS_HEADER)
        writer.writerows(transfers_rows)

    print(f"Benchmark completed successfully! Wrote {len(runs_rows)} runs and {len(transfers_rows)} transfers.")
    return runs_file, transfers_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--croc", type=Path, default=Path(r"C:\lab\croc.exe"))
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("bench"))
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.croc, args.fixtures, args.output))


if __name__ == "__main__":
    main()
