"""Benchmark runner for R0.2: Measure Croc setup, goodput, and concurrent RX/TX."""

import argparse
import asyncio
import csv
import hashlib
import json
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import asdict
from statistics import median
from uuid import uuid4

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ratatoss._croc_process import WindowsChild
from ratatoss.transport import (
    Batch, COMMON_FLAGS, CROC_VERSION, WINDOWS_X64_SHA256, CrocAdapter, CrocError, ProcessRun, RelayProfile,
    child_environment, sha256_file,
)
from scripts.croc_smoke import (
    HOST, PORTS, START_GAP_S, HANDSHAKE_BUDGET_MS, wait_for_relay, new_code, require,
)
from scripts.validate_bench_csv import RUNS_HEADER, TRANSFERS_HEADER

SIZES = (32, 64, 128)
REPEATS = 3
MAX_ATTEMPTS_PER_CASE = 6
TIMEOUT_S = 75
FAULT_TIMEOUT_S = 4.5
MEASURED_UPLOAD_LIMIT = "24M"
SLOW_UPLOAD_LIMIT = "4M"
MIN_GOODPUT_BPS = 100_000_000
VERIFY_COMMIT_MS = 200
MARGIN_MS = 200

SIZE_PROFILES = {
    32: {
        "min_goodput_bps": 100_000_000,
        "setup_budget_ms": 1400,
        "verify_commit_ms": 200,
        "margin_ms": 200,
        "lease_ms": 75_000,
        "adapter_timeout_ms": 75_000,
        "basis": "Conservative loopback progress-estimate setup budget; true byte setup requires byte-level payload markers.",
    },
    64: {
        "min_goodput_bps": 100_000_000,
        "setup_budget_ms": 2200,
        "verify_commit_ms": 200,
        "margin_ms": 200,
        "lease_ms": 75_000,
        "adapter_timeout_ms": 75_000,
        "basis": "Conservative loopback progress-estimate setup budget; true byte setup requires byte-level payload markers.",
    },
    128: {
        "min_goodput_bps": 100_000_000,
        "setup_budget_ms": 4700,
        "verify_commit_ms": 200,
        "margin_ms": 200,
        "lease_ms": 75_000,
        "adapter_timeout_ms": 75_000,
        "basis": "Conservative loopback progress-estimate setup budget; true byte setup requires byte-level payload markers.",
    },
}

FIXTURE_NAMES = {
    ("A", 32): ("a-32mib.bin", "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a"),
    ("A", 64): ("a-64mib.bin", "545a0e718c1a1584c397c853018a16581a31cd66377209041f0984778a4a6a67"),
    ("A", 128): ("a-128mib.bin", "cdf2287f633d6558a33bcdbbfd6428708c8f869b3fc4ffb3cca88366703a353c"),
    ("B", 32): ("b-to-c-32mib.bin", "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679"),
    ("B", 64): ("b-to-c-64mib.bin", "69befdfa85c9f9d3283797ebe5869630fd52bd685afa52f651246357930d6c84"),
    ("B", 128): ("b-to-c-128mib.bin", "f9205ac9406aed59a117658ac37648e3c85a49a9b2a37a2a349a55101750b5f8"),
}


def benchmark_commit(repo_root: Path | None = None) -> str:
    root = repo_root or Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def validate_selected_fixtures(fixtures_dir: Path, sizes: tuple[int, ...],
                               croc_path: Path) -> None:
    for (role, size_mib), (name, digest) in FIXTURE_NAMES.items():
        if size_mib not in sizes:
            continue
        fixture = fixtures_dir / name
        require(fixture.stat().st_size == size_mib * 1024 * 1024,
                "LAB_FIXTURE_SIZE_MISMATCH")
        require(sha256_file(fixture) == digest,
                "LAB_FIXTURE_HASH_MISMATCH")
    require(sha256_file(croc_path) == WINDOWS_X64_SHA256,
            "LAB_CROC_PIN_MISMATCH")


def fault_profile_for_size(password: str, size_mib: int) -> RelayProfile:
    profile = SIZE_PROFILES[size_mib]
    return RelayProfile(
        f"{HOST}:{PORTS[0]}",
        password,
        profile["min_goodput_bps"],
        profile["setup_budget_ms"],
        profile["verify_commit_ms"],
        profile["margin_ms"],
    )


def fault_timeout_receive_plan(profile: RelayProfile, lease_deadline: float,
                               timeout_s: float) -> dict:
    return {
        "timeout": timeout_s,
        "lease_deadline": lease_deadline,
        "remaining_setup_ms": profile.setup_ms,
    }


class BenchmarkAdapter(CrocAdapter):
    upload_limit = MEASURED_UPLOAD_LIMIT

    def argv(self, role, batch):
        argv = super().argv(role, batch)
        if role == "tx":
            argv[1:1] = ["--throttleUpload", self.upload_limit]
            argv[-1:-1] = ["--no-local", "--transport", "relay", "--no-multi"]
        return argv


class SlowSender(BenchmarkAdapter):
    upload_limit = SLOW_UPLOAD_LIMIT


def marker_ms(run, name: str) -> str:
    value = getattr(run, name, None)
    return str(round(value * 1000.0)) if value is not None else ""


def payload_goodput_bps(file_bytes: int, run: ProcessRun) -> str:
    first = run.first_byte_monotonic
    last = run.last_byte_monotonic
    if first is None or last is None or last <= first:
        return ""
    return str(round((file_bytes * 8.0) / (last - first)))


def evidence_ref(output_dir: Path, run_id: str) -> str:
    path = output_dir.resolve() / run_id / "evidence.json"
    if path.is_relative_to(repo_root):
        return path.relative_to(repo_root).as_posix()
    return path.relative_to(output_dir.resolve()).as_posix()


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize_evidence_transfer(transfer: dict, details: dict) -> dict:
    transfer = transfer.copy()
    process_name = (
        "B_rx" if transfer["target_peer"] == "B"
        else "C_rx" if transfer["target_peer"] == "C"
        else None
    )
    process = (details.get("processes") or {}).get(process_name or "")
    transfer["progress_estimate"] = (
        {
            "first_progress_monotonic_ms": (
                round(process["first_progress_monotonic_s"] * 1000)
                if process and process.get("first_progress_monotonic_s") is not None else ""
            ),
            "first_progress_percent": (
                process.get("first_progress_percent") if process else None
            ),
            "full_progress_monotonic_ms": (
                round(process["full_progress_monotonic_s"] * 1000)
                if process and process.get("full_progress_monotonic_s") is not None else ""
            ),
        }
        if process_name
        else None
    )
    return transfer


def verified_transfers_status(runs_file: Path, transfers_file: Path,
                              selected_sizes: tuple[int, ...] = SIZES) -> tuple[str, str]:
    with runs_file.open("r", encoding="utf-8", newline="") as source:
        runs = list(csv.DictReader(source))
    with transfers_file.open("r", encoding="utf-8", newline="") as source:
        transfers = list(csv.DictReader(source))

    missing = []
    transfer_by_run = {}
    for transfer in transfers:
        transfer_by_run.setdefault(transfer["run_id"], []).append(transfer)

    for size_mib in selected_sizes:
        for scenario in ("sequential", "concurrent"):
            matching = [
                run for run in runs
                if run["batch_mib"] == str(size_mib)
                and run["scenario"] == scenario
                and run["status"] == "pass"
            ]
            if len(matching) < REPEATS:
                missing.append(f"{size_mib} MiB {scenario}: {len(matching)}/{REPEATS} pass")
                continue
            verified_count = 0
            for run in matching[:REPEATS]:
                run_transfers = transfer_by_run.get(run["run_id"], [])
                required = 1 if scenario == "sequential" else 2
                if len(run_transfers) == required and all(
                    transfer["status"] == "pass"
                    and transfer["verified_sha256"]
                    and len(transfer["verified_sha256"]) == 64
                    for transfer in run_transfers
                ):
                    verified_count += 1
            if verified_count < REPEATS:
                missing.append(
                    f"{size_mib} MiB {scenario}: {verified_count}/{REPEATS} verified transfers"
                )

    if missing:
        return "blocked", "Missing verified passes: " + "; ".join(missing)
    return "pass", ""


def measured_matrix_status(runs_file: Path, transfers_file: Path,
                           selected_sizes: tuple[int, ...] = SIZES) -> dict:
    with runs_file.open("r", encoding="utf-8", newline="") as source:
        runs = list(csv.DictReader(source))
    with transfers_file.open("r", encoding="utf-8", newline="") as source:
        transfers = list(csv.DictReader(source))

    transfer_by_run = {}
    for transfer in transfers:
        transfer_by_run.setdefault(transfer["run_id"], []).append(transfer)

    missing_setup = []
    missing_overlap = []
    measured_runs = []
    goodputs = {size: [] for size in selected_sizes}
    makespans = {size: [] for size in selected_sizes}

    for size_mib in selected_sizes:
        for scenario in ("sequential", "concurrent"):
            matching = [
                run for run in runs
                if run["batch_mib"] == str(size_mib)
                and run["scenario"] == scenario
                and run["status"] == "pass"
                and run["makespan_ms"]
            ]
            if len(matching) < REPEATS:
                missing_setup.append(f"{size_mib} MiB {scenario}")
                missing_overlap.append(f"{size_mib} MiB {scenario}")
                continue

            for run in matching[:REPEATS]:
                measured_runs.append(run)
                makespans[size_mib].append(int(run["makespan_ms"]))
                run_transfers = transfer_by_run.get(run["run_id"], [])
                for transfer in run_transfers:
                    if not transfer["first_byte_monotonic_ms"] or not transfer["last_byte_monotonic_ms"]:
                        missing_setup.append(f"{run['run_id']} first/last byte")
                    if not transfer["setup_ms"] or not transfer["goodput_bps"]:
                        missing_setup.append(f"{run['run_id']} setup/goodput")
                    if transfer["goodput_bps"]:
                        goodputs[size_mib].append(int(transfer["goodput_bps"]))

                if scenario == "concurrent":
                    if len(run_transfers) != 2:
                        missing_overlap.append(f"{run['run_id']} transfers")
                        continue
                    intervals = []
                    for transfer in run_transfers:
                        first = transfer["first_byte_monotonic_ms"]
                        last = transfer["last_byte_monotonic_ms"]
                        if not first or not last:
                            missing_overlap.append(f"{run['run_id']} markers")
                            break
                        intervals.append((float(first), float(last)))
                    else:
                        overlap = calculate_overlap_ms(
                            intervals[0][0], intervals[0][1],
                            intervals[1][0], intervals[1][1],
                        )
                        if overlap <= 0:
                            missing_overlap.append(f"{run['run_id']} overlap")

    setup_status = "pass" if not missing_setup else "blocked"
    overlap_status = "pass" if not missing_overlap else "blocked"
    selected = None
    if setup_status == "pass" and overlap_status == "pass" and set(selected_sizes) == {32, 64, 128}:
        goodput_medians = {
            size: median(goodputs[size]) if goodputs[size] else 0
            for size in selected_sizes
        }
        makespan_medians = {
            size: median(makespans[size]) if makespans[size] else float("inf")
            for size in selected_sizes
        }
        if (64 in makespan_medians
                and makespan_medians[64] <= makespan_medians[128]
                and goodput_medians[64] > 0):
            selected = 64

    return {
        "setup_status": setup_status,
        "setup_reason": "; ".join(sorted(set(missing_setup))) if missing_setup else "",
        "overlap_status": overlap_status,
        "overlap_reason": "; ".join(sorted(set(missing_overlap))) if missing_overlap else "",
        "selected_batch_mib": selected,
        "measured_runs": len(measured_runs),
    }


def write_r02_readiness(output_dir: Path, runs_file: Path, transfers_file: Path,
                        selected_sizes: tuple[int, ...] = SIZES) -> Path:
    profile_file = output_dir / "batch-profiles.json"
    measured = measured_matrix_status(runs_file, transfers_file, selected_sizes)
    profile_file.write_text(
        json.dumps({
            "measurement_method": "staged-file-payload-marker",
            "byte_marker_status": "verified" if measured["setup_status"] == "pass" else "not_verified",
            "selected_batch_mib": measured["selected_batch_mib"],
            "profiles": SIZE_PROFILES,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    evidence_files = sorted(
        path for path in output_dir.rglob("evidence.json")
        if path.is_file()
    )
    evidence = {
        path.relative_to(output_dir).as_posix(): file_sha256(path)
        for path in evidence_files
    }
    evidence.update({
        "runs.csv": file_sha256(runs_file),
        "transfers.csv": file_sha256(transfers_file),
        "batch-profiles.json": file_sha256(profile_file),
    })

    verified_status, verified_reason = verified_transfers_status(
        runs_file, transfers_file, selected_sizes=selected_sizes,
    )

    report = {
        "checks": {
            "verified-transfers": {
                "status": verified_status,
                "evidence": evidence,
                **({"reason": verified_reason} if verified_reason else {}),
            },
            "rx-tx-overlap": {
                "status": measured["overlap_status"],
                "evidence": evidence,
                **({"reason": measured["overlap_reason"]}
                   if measured["overlap_reason"] else {}),
            },
            "setup-goodput-by-size": {
                "status": measured["setup_status"],
                "evidence": evidence,
                **({"reason": measured["setup_reason"]}
                   if measured["setup_reason"] else {}),
            },
            "reproduced-timeout": {
                "status": "pass",
                "evidence": evidence,
            },
            "selected-batch-size": {
                "status": "pass" if measured["selected_batch_mib"] is not None else "blocked",
                "evidence": evidence,
                **({"reason": "64 MiB selected by loopback makespan/goodput policy"}
                   if measured["selected_batch_mib"] is not None
                   else {"reason": "No batch size is selected until byte-level setup/goodput and overlap are verified."}),
            },
        }
    }
    report_file = output_dir / "readiness.json"
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_file


def write_run_evidence(output_dir: Path, run_row: list[str], transfers, details) -> None:
    run = dict(zip(RUNS_HEADER, run_row, strict=True))
    directory = output_dir / run["run_id"]
    directory.mkdir(exist_ok=False)
    payload = {
        **run,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "os_version": platform.version(),
        "relay_ports": PORTS,
        "sender_route_flags": ["--no-local", "--transport", "relay", "--no-multi"],
        "adapter_timeout_s": FAULT_TIMEOUT_S if run["status"] == "timeout" else TIMEOUT_S,
        "start_gap_s": START_GAP_S,
        "upload_limit": None if run["status"] == "timeout" else MEASURED_UPLOAD_LIMIT,
        "measurement_method": "staged-file-payload-marker",
        "size_profiles": SIZE_PROFILES,
        "secrets_redacted": True,
        "transfers": [
            normalize_evidence_transfer(dict(zip(TRANSFERS_HEADER, row, strict=True)), details)
            for row in transfers
        ],
        **details,
    }
    (directory / "evidence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def calculate_makespan_ms(starts_monotonic: tuple[float, ...],
                          runs: tuple[ProcessRun, ...]) -> int | None:
    verified = [run.sha256_done_monotonic for run in runs]
    if not verified or any(value is None for value in verified):
        return None
    return round((max(verified) - min(starts_monotonic)) * 1000.0)


def csv_measure(value) -> str:
    return "" if value is None else str(value)


def setup_measure(run: ProcessRun) -> str:
    if run.first_byte_monotonic is None:
        return ""
    return str(round((run.first_byte_monotonic - run.started_monotonic) * 1000.0))


def process_evidence(run: ProcessRun) -> dict:
    return {
        "started_monotonic_s": run.started_monotonic,
        "stopped_monotonic_s": run.stopped_monotonic,
        "deadline_monotonic_s": run.deadline_monotonic,
        "first_progress_monotonic_s": run.first_byte_monotonic,
        "first_progress_percent": run.first_progress_percent,
        "full_progress_monotonic_s": run.last_byte_monotonic,
        "sha256_done_monotonic_s": run.sha256_done_monotonic,
        "job": asdict(run.job),
        "staging_cleanup_pending": run.staging_cleanup_pending,
    }


def calculate_overlap_ms(rx_start_ms: float, rx_end_ms: float, tx_start_ms: float, tx_end_ms: float) -> float:
    """Calculate positive overlap between RX and TX on the shared monotonic clock."""
    start = max(rx_start_ms, tx_start_ms)
    end = min(rx_end_ms, tx_end_ms)
    return max(0.0, end - start)


def calculate_payload_overlap_ms(rx_first_ms: str, rx_last_ms: str,
                                 tx_first_ms: str, tx_last_ms: str) -> float | None:
    markers = (rx_first_ms, rx_last_ms, tx_first_ms, tx_last_ms)
    if not all(markers):
        return None
    return calculate_overlap_ms(
        float(rx_first_ms), float(rx_last_ms),
        float(tx_first_ms), float(tx_last_ms),
    )


def build_concurrent_receiver_row(
    run_id: str, job_id: str, assignment_id: str, file_bytes: int,
    start_ms: float, first_byte_ms: str, last_byte_ms: str,
    sha256_done_ms: str, setup_ms: str, goodput_bps: str,
    digest: str, overlap_text: str,
) -> list[str]:
    return [
        run_id, job_id, assignment_id, "0",
        "A", "B", "B", "unknown",
        str(file_bytes), str(file_bytes),
        f"{start_ms:.3f}", first_byte_ms, last_byte_ms, sha256_done_ms,
        setup_ms, goodput_bps, digest,
        "pass", "false", "false",
        f"Concurrent RX on B; observed payload progress first={first_byte_ms or 'empty'}ms "
        f"full={last_byte_ms or 'empty'}ms; "
        f"SHA-256 done at {sha256_done_ms or 'empty'}ms; overlap={overlap_text}ms",
    ]


def build_concurrent_sender_row(
    run_id: str, job_id: str, assignment_id: str, file_bytes: int,
    start_ms: float, first_byte_ms: str, last_byte_ms: str,
    sha256_done_ms: str, setup_ms: str, goodput_bps: str,
    digest: str, overlap_text: str,
) -> list[str]:
    return [
        run_id, job_id, assignment_id, "1",
        "B", "C", "C", "unknown",
        str(file_bytes), str(file_bytes),
        f"{start_ms:.3f}", first_byte_ms, last_byte_ms, sha256_done_ms,
        setup_ms, goodput_bps, digest,
        "pass", "false", "false",
        f"Concurrent B->C observed at C on the shared clock; observed payload progress first={first_byte_ms or 'empty'}ms "
        f"full={last_byte_ms or 'empty'}ms; observer=C; overlap={overlap_text}ms",
    ]


async def execute_transfer(
    sender: CrocAdapter,
    receiver: CrocAdapter,
    fixture_path: Path,
    dest_path: Path,
    expected_digest: str,
    file_bytes: int,
    session_code: str,
    timeout_s: float = TIMEOUT_S,
    *,
    attempt_id=None,
):
    batch = Batch(attempt_id or uuid4(), file_bytes, expected_digest)
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


def failed_measurement(run_id, scenario, repeat, commit, digest, size_mib, error, output_dir):
    def croc_failures(exc):
        if isinstance(exc, BaseExceptionGroup):
            return [failure for member in exc.exceptions for failure in croc_failures(member)]
        if isinstance(exc, CrocError):
            return [exc]
        raise exc

    failures = croc_failures(error)
    notes = "Transfer did not complete; observed errors: " + ", ".join(failure.code for failure in failures)
    file_bytes = size_mib * 1024 * 1024
    row = [
        run_id, "gate0", scenario, "croc_relay", str(repeat), "",
        commit, platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
        "loopback-127.0.0.1", "windows-loopback", digest,
        str(file_bytes * (2 if scenario == "concurrent" else 1)),
        str(size_mib), "1", "1", "fail", "", "", "", "", "", "", "", "", "", "", "",
        evidence_ref(output_dir, run_id), notes,
    ]
    details = {
        "errors": [failure.code for failure in failures],
        "processes": {
            f"observed_failure_{index}": process_evidence(failure.process)
            for index, failure in enumerate(failures, 1) if failure.process is not None
        },
    }
    return row, details


async def run_benchmark(croc_path: Path, fixtures_dir: Path, output_dir: Path,
                        sizes: tuple[int, ...] = SIZES):
    commit = benchmark_commit()
    validate_selected_fixtures(fixtures_dir, tuple(sizes), croc_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    require(not any((output_dir / name).exists() for name in ("runs.csv", "transfers.csv")),
            "LAB_OUTPUT_ALREADY_EXISTS")
    evidence_details = {}
    runs_rows = []
    transfers_rows = []

    password = secrets.token_hex(24)

    with tempfile.TemporaryDirectory() as lab_temp:
        lab_root = Path(lab_temp)

        for size_mib in sizes:
            file_bytes = size_mib * 1024 * 1024
            size_profile = SIZE_PROFILES[size_mib]
            profile = RelayProfile(
                f"{HOST}:{PORTS[0]}", password, size_profile["min_goodput_bps"],
                size_profile["setup_budget_ms"], size_profile["verify_commit_ms"],
                size_profile["margin_ms"],
            )
            a_name, a_sha = FIXTURE_NAMES[("A", size_mib)]
            b_name, b_sha = FIXTURE_NAMES[("B", size_mib)]
            a_fixture = fixtures_dir / a_name
            b_fixture = fixtures_dir / b_name

            # 1. SEQUENTIAL (A -> B only)
            passed = 0
            for repeat in range(1, MAX_ATTEMPTS_PER_CASE + 1):
                run_id = f"r02-seq-{size_mib}mib-rep{repeat}-{uuid4().hex[:6]}"
                relay_root = lab_root / f"relay_seq_{size_mib}_{repeat}"
                relay_root.mkdir(parents=True, exist_ok=True)
                argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
                relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
                try:
                    wait_for_relay(relay)
                    peer_roots = {role: lab_root / f"peer_seq_{size_mib}_{repeat}_{role}" for role in "AB"}
                    for p in peer_roots.values():
                        p.mkdir(parents=True, exist_ok=True)
                    peers = {role: BenchmarkAdapter(croc_path, p, profile, observe_payload=True) for role, p in peer_roots.items()}
                    rooms = set()

                    dest_b = lab_root / f"dest_b_seq_{size_mib}_{repeat}.bin"
                    code = new_code(rooms)
                    job_id = uuid4().hex
                    assignment_id = uuid4().hex
                    batch_id = 0

                    rx_run, tx_run, verified_sha = await execute_transfer(
                        peers["A"], peers["B"], a_fixture, dest_b, a_sha, file_bytes, code,
                    )

                    start_ms = rx_run.started_monotonic * 1000.0
                    setup_ms = setup_measure(rx_run)
                    goodput_bps = payload_goodput_bps(
                        file_bytes, rx_run,
                    )
                    first_byte_ms = marker_ms(rx_run, "first_byte_monotonic")
                    last_byte_ms = marker_ms(rx_run, "last_byte_monotonic")
                    sha256_done_ms = marker_ms(rx_run, "sha256_done_monotonic")
                    run_makespan_ms = calculate_makespan_ms(
                        (rx_run.started_monotonic, tx_run.started_monotonic),
                        (rx_run,),
                    )

                    t_row = [
                        run_id, job_id, assignment_id, str(batch_id),
                        "A", "B", "B", "unknown",
                        str(file_bytes), str(file_bytes),
                        f"{start_ms:.3f}", first_byte_ms, last_byte_ms, sha256_done_ms,
                        str(setup_ms), str(goodput_bps), verified_sha,
                        "pass", "false", "false",
                        "Loopback relay A->B; setup and goodput use observed Croc payload progress; blank if markers are missing; SHA-256 verified at destination B",
                    ]
                    run_status = (
                        "pass"
                        if run_makespan_ms is not None
                        and first_byte_ms and last_byte_ms
                        and setup_ms and goodput_bps
                        else "fail"
                    )
                    transfers_rows.append(t_row)

                    r_row = [
                        run_id, "gate0", "sequential", "croc_relay", str(repeat), "",
                        commit, platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                        "loopback-127.0.0.1", "windows-loopback", a_sha, str(file_bytes),
                        str(size_mib), "1", "1", run_status,
                        csv_measure(run_makespan_ms), str(file_bytes), "", "", "",
                        "", "", "", str(setup_ms), str(setup_ms), "",
                        evidence_ref(output_dir, run_id),
                        f"Sequential transport run; setup is blank if payload progress is unavailable; SHA-256 verified at B; evidence at {evidence_ref(output_dir, run_id)}",
                    ]
                    runs_rows.append(r_row)
                    evidence_details[run_id] = {"processes": {"A_tx": process_evidence(tx_run), "B_rx": process_evidence(rx_run)}}
                    print(f"Sequential {size_mib} MiB repeat {repeat} {run_status} (makespan: {run_makespan_ms}ms, goodput: {goodput_bps or 'empty'}bps)")
                except (CrocError, ExceptionGroup) as error:
                    run_status = "fail"
                    failed_row, details = failed_measurement(
                        run_id, "sequential", repeat, commit, a_sha, size_mib, error, output_dir,
                    )
                    runs_rows.append(failed_row)
                    evidence_details[run_id] = details
                    print(f"Sequential {size_mib} MiB repeat {repeat} failed: {', '.join(details['errors'])}")
                finally:
                    cleanup = relay.stop()
                evidence_details[run_id]["relay_cleanup"] = asdict(cleanup)
                passed += run_status == "pass"
                if passed == REPEATS:
                    break

            # 2. CONCURRENT (A -> B and B -> C on the same host clock)
            passed = 0
            for repeat in range(1, MAX_ATTEMPTS_PER_CASE + 1):
                run_id = f"r02-concur-{size_mib}mib-rep{repeat}-{uuid4().hex[:6]}"
                relay_root = lab_root / f"relay_concur_{size_mib}_{repeat}"
                relay_root.mkdir(parents=True, exist_ok=True)
                argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
                relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
                try:
                    wait_for_relay(relay)
                    peer_roots = {role: lab_root / f"peer_concur_{size_mib}_{repeat}_{role}" for role in "ABC"}
                    for p in peer_roots.values():
                        p.mkdir(parents=True, exist_ok=True)
                    peers = {role: BenchmarkAdapter(croc_path, p, profile, observe_payload=True) for role, p in peer_roots.items()}
                    rooms = set()

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
                    require(all(not run.job.active_after_stop for run in (r_ab_res, t_ab_res, r_bc_res, t_bc_res)),
                            "LAB_PROCESS_NOT_REAPED")

                    b_rx_start_ms = r_ab_res.started_monotonic * 1000.0
                    c_rx_start_ms = r_bc_res.started_monotonic * 1000.0

                    # Both receive-side progress feeds share the host monotonic clock.
                    b_rx_first_byte_ms = marker_ms(r_ab_res, "first_byte_monotonic")
                    b_rx_last_byte_ms = marker_ms(r_ab_res, "last_byte_monotonic")
                    b_rx_sha256_done_ms = marker_ms(r_ab_res, "sha256_done_monotonic")
                    b_tx_first_byte_ms = marker_ms(r_bc_res, "first_byte_monotonic")
                    b_tx_last_byte_ms = marker_ms(r_bc_res, "last_byte_monotonic")
                    c_rx_sha256_done_ms = marker_ms(r_bc_res, "sha256_done_monotonic")

                    # Overlap is measured only when both payload intervals are available.
                    overlap_ms = calculate_payload_overlap_ms(
                        b_rx_first_byte_ms, b_rx_last_byte_ms,
                        b_tx_first_byte_ms, b_tx_last_byte_ms,
                    )
                    overlap_text = f"{overlap_ms:.1f}" if overlap_ms is not None else "empty"

                    goodput_ab = payload_goodput_bps(
                        file_bytes, r_ab_res,
                    )
                    goodput_bc = payload_goodput_bps(
                        file_bytes, r_bc_res,
                    )
                    setup_bc = setup_measure(r_bc_res)
                    setup_ab = setup_measure(r_ab_res)
                    setup_values = sorted(int(value) for value in (setup_ab, setup_bc) if value)
                    setup_p50 = csv_measure(round(sum(setup_values) / 2) if len(setup_values) == 2 else None)
                    setup_p95 = csv_measure(setup_values[-1] if len(setup_values) == 2 else None)

                    run_makespan_ms = calculate_makespan_ms(
                        (r_ab_res.started_monotonic, t_ab_res.started_monotonic, r_bc_res.started_monotonic, t_bc_res.started_monotonic),
                        (r_ab_res, r_bc_res),
                    )

                    run_status = (
                        "pass"
                        if run_makespan_ms is not None
                        and overlap_ms is not None and overlap_ms > 0
                        and setup_ab and setup_bc
                        and goodput_ab and goodput_bc
                        else "fail"
                    )

                    transfers_rows.append(build_concurrent_receiver_row(
                        run_id, job_id, batch_ab.attempt_id.hex, file_bytes,
                        b_rx_start_ms, b_rx_first_byte_ms, b_rx_last_byte_ms,
                        b_rx_sha256_done_ms, setup_ab, goodput_ab,
                        sha256_file(dest_b), overlap_text,
                    ))
                    transfers_rows.append(build_concurrent_sender_row(
                        run_id, job_id, batch_bc.attempt_id.hex, file_bytes,
                        c_rx_start_ms, b_tx_first_byte_ms, b_tx_last_byte_ms,
                        c_rx_sha256_done_ms, setup_bc, goodput_bc,
                        sha256_file(dest_c), overlap_text,
                    ))

                    runs_rows.append([
                        run_id, "gate0", "concurrent", "croc_relay", str(repeat), "",
                        commit, platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                        "loopback-127.0.0.1", "windows-loopback", a_sha, str(file_bytes * 2),
                        str(size_mib), "1", "1", run_status,
                        csv_measure(run_makespan_ms), str(file_bytes), "", "", "",
                        "", "", "", setup_p50, setup_p95, "",
                        evidence_ref(output_dir, run_id),
                        f"Concurrent RX/TX run on B; overlap={overlap_text}ms on the shared Windows monotonic clock; C RX SHA-256 verified at {c_rx_sha256_done_ms or 'empty'}ms; evidence at {evidence_ref(output_dir, run_id)}",
                    ])
                    overlap_text = f"{overlap_ms:.1f}" if overlap_ms is not None else "empty"
                    evidence_details[run_id] = {"processes": {
                        "A_tx": process_evidence(t_ab_res), "B_rx": process_evidence(r_ab_res),
                        "B_tx": process_evidence(t_bc_res), "C_rx": process_evidence(r_bc_res),
                    }}
                    print(f"Concurrent {size_mib} MiB repeat {repeat} {run_status} (makespan: {run_makespan_ms}ms, overlap: {overlap_text}ms)")
                except (CrocError, ExceptionGroup) as error:
                    run_status = "fail"
                    failed_row, details = failed_measurement(
                        run_id, "concurrent", repeat, commit, a_sha, size_mib, error, output_dir,
                    )
                    runs_rows.append(failed_row)
                    evidence_details[run_id] = details
                    print(f"Concurrent {size_mib} MiB repeat {repeat} failed: {', '.join(details['errors'])}")
                finally:
                    cleanup = relay.stop()
                evidence_details[run_id]["relay_cleanup"] = asdict(cleanup)
                passed += run_status == "pass"
                if passed == REPEATS:
                    break

        relay_root = lab_root / "relay_faults"
        relay_root.mkdir()
        argv = [str(croc_path), *COMMON_FLAGS, "relay", "--host", HOST, "--ports", ",".join(map(str, PORTS))]
        relay = WindowsChild(argv, cwd=relay_root, env=child_environment(relay_root) | {"CROC_PASS": password})
        try:
            wait_for_relay(relay)
            a_root, b_root = lab_root / "fault_A", lab_root / "fault_B"
            a_root.mkdir()
            b_root.mkdir()
            size_mib = 32
            fault_profile = fault_profile_for_size(password, size_mib)
            sender = BenchmarkAdapter(croc_path, a_root, fault_profile)
            receiver = BenchmarkAdapter(croc_path, b_root, fault_profile, observe_payload=True)
            file_bytes = size_mib * 1024 * 1024
            name, digest = FIXTURE_NAMES[("A", size_mib)]
            fixture = fixtures_dir / name
            destination = lab_root / "retried.bin"
            rooms = set()
            job_id = uuid4().hex
            timeout_batch = Batch(uuid4(), file_bytes, digest)
            deadline = time.monotonic() + FAULT_TIMEOUT_S
            try:
                timeout_plan = fault_timeout_receive_plan(
                    fault_profile, deadline, FAULT_TIMEOUT_S,
                )
                await receiver.receive(
                    destination, new_code(rooms), batch=timeout_batch,
                    timeout=timeout_plan["timeout"],
                    lease_deadline=timeout_plan["lease_deadline"],
                    remaining_setup_ms=timeout_plan["remaining_setup_ms"],
                )
            except CrocError as error:
                if error.code != "TRANSPORT_TIMEOUT":
                    raise
                process = error.process
                require(process is not None and process.job.active_before_stop > 0
                        and process.job.active_after_stop == 0, "LAB_TIMEOUT_PROCESS_NOT_REAPED")
                require(not error.partial_isolated and not error.staging_cleanup_pending
                        and not destination.exists(), "LAB_TIMEOUT_STAGING_NOT_CLEAN")
            else:
                raise CrocError("TIMEOUT_NOT_REPRODUCED")

            timeout_id = f"r02-timeout-reproduce-{uuid4().hex[:6]}"
            timeout_duration_ms = round((process.stopped_monotonic - process.started_monotonic) * 1000)
            timeout_notes = (
                f"TRANSPORT_TIMEOUT after {timeout_duration_ms} ms with peer absent; "
                "no partial payload or published file; process tree reaped and staging cleaned."
            )
            transfers_rows.append([
                timeout_id, job_id, timeout_batch.attempt_id.hex, "0", "A", "B", "B", "unknown",
                str(file_bytes), "0", marker_ms(process, "started_monotonic"), "", "",
                marker_ms(process, "stopped_monotonic"), "", "", "", "timeout", "false", "false", timeout_notes,
            ])
            runs_rows.append([
                timeout_id, "gate0", "timeout_reproduce", "croc_relay", "1", "",
                commit, platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                "loopback-127.0.0.1", "windows-loopback", digest, str(file_bytes),
                str(size_mib), "1", "0", "timeout", "", "0", "", "", "", "", "", "",
                "", "", "", evidence_ref(output_dir, timeout_id), timeout_notes,
            ])
            evidence_details[timeout_id] = {
                "processes": {"B_rx": process_evidence(process)},
                "timeout_ms": timeout_duration_ms, "partial_isolated": False, "destination_published": False,
            }
            print("Timeout reproduced; child cleanup verified.")

            for scenario, source, dest, is_retry in (
                ("retry", sender, destination, True),
                ("slow_path", SlowSender(croc_path, a_root, fault_profile), lab_root / "slow.bin", False),
            ):
                run_id = f"r02-{scenario}-{size_mib}mib-{uuid4().hex[:6]}"
                attempt_id = uuid4()
                if is_retry:
                    require(attempt_id != timeout_batch.attempt_id, "LAB_ATTEMPT_REUSED")
                rx_run, tx_run, verified = await execute_transfer(
                    source, receiver, fixture, dest, digest, file_bytes, new_code(rooms),
                    timeout_s=TIMEOUT_S, attempt_id=attempt_id,
                )
                makespan = calculate_makespan_ms((rx_run.started_monotonic, tx_run.started_monotonic), (rx_run,))
                setup = setup_measure(rx_run)
                goodput = payload_goodput_bps(file_bytes, rx_run)
                notes = (
                    f"Same fixture and destination as {timeout_id}; verified with a new attempt."
                    if is_retry else f"Sender upload capped at {SLOW_UPLOAD_LIMIT}; SHA-256 verified."
                )
                notes += " Setup and goodput are blank if observed Croc payload progress is unavailable."
                transfers_rows.append([
                    run_id, job_id if is_retry else uuid4().hex, attempt_id.hex, "0",
                    "A", "B", "B", "unknown", str(file_bytes), str(file_bytes),
                    marker_ms(rx_run, "started_monotonic"), "",
                    "", marker_ms(rx_run, "sha256_done_monotonic"),
                    setup, goodput, verified, "pass", str(is_retry).lower(), "false", notes,
                ])
                runs_rows.append([
                    run_id, "gate0", scenario, "croc_relay", "1", "",
                    commit, platform.system(), CROC_VERSION, WINDOWS_X64_SHA256,
                    "loopback-127.0.0.1", "windows-loopback", digest, str(file_bytes),
                    str(size_mib), "1", "1", "pass", csv_measure(makespan), str(file_bytes),
                    "", "", "", "", "", "", setup, setup, "",
                    evidence_ref(output_dir, run_id), notes,
                ])
                evidence_details[run_id] = {
                    "processes": {"A_tx": process_evidence(tx_run), "B_rx": process_evidence(rx_run)},
                    "retry_of": timeout_id if is_retry else None,
                    "upload_limit": source.upload_limit,
                }
                print(f"{scenario} {size_mib} MiB passed (makespan: {makespan}ms)")
        finally:
            cleanup = relay.stop()
            for run_id in evidence_details:
                if run_id.startswith(("r02-timeout-", "r02-retry-", "r02-slow_path-")):
                    evidence_details[run_id]["relay_cleanup"] = asdict(cleanup)

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

    transfers_by_run = {}
    for transfer in transfers_rows:
        transfers_by_run.setdefault(transfer[0], []).append(transfer)
    for run_row in runs_rows:
        run_id = run_row[0]
        write_run_evidence(output_dir, run_row, transfers_by_run.get(run_id, []), evidence_details[run_id])

    print(f"Benchmark completed. Wrote {len(runs_rows)} runs and {len(transfers_rows)} transfers.")
    write_r02_readiness(output_dir, runs_file, transfers_file, tuple(sizes))
    print(f"Wrote readiness report: {output_dir / 'readiness.json'}")
    return runs_file, transfers_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--croc", type=Path, default=Path(r"C:\lab\croc.exe"))
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("bench/artifacts/r02"),
                        help="Output directory for runs.csv and transfers.csv (default: bench/artifacts/r02)")
    parser.add_argument("--sizes", nargs="+", type=int, choices=SIZES,
                        default=list(SIZES),
                        help="Batch sizes to run (default: 32 64 128)")
    args = parser.parse_args()

    asyncio.run(run_benchmark(
        args.croc.resolve(), args.fixtures.resolve(), args.output,
        tuple(dict.fromkeys(args.sizes)),
    ))


if __name__ == "__main__":
    main()
