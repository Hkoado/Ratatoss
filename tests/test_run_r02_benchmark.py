"""Unit tests for R0.2 benchmark runner logic."""

import os
from pathlib import Path
import sys
import unittest


def _resolve_repo_root() -> Path | None:
    if "GITHUB_WORKSPACE" in os.environ:
        workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        if (workspace / "scripts" / "run_r02_benchmark.py").is_file():
            return workspace

    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "scripts" / "run_r02_benchmark.py").is_file():
        return candidate

    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        if (directory / "scripts" / "run_r02_benchmark.py").is_file():
            return directory

    return None


REPO_ROOT = _resolve_repo_root()
calculate_overlap_ms = None
_import_error: Exception | None = None

if REPO_ROOT is None:
    pass  # will SkipTest in setUpClass
else:
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from run_r02_benchmark import (
            build_concurrent_receiver_row,
            build_concurrent_sender_row,
            calculate_makespan_ms,
            calculate_overlap_ms,
            BenchmarkAdapter,
            FAULT_TIMEOUT_S,
            fault_profile_for_size,
            fault_timeout_receive_plan,
            evidence_ref,
            normalize_evidence_transfer,
            transport_run_status,
            validate_selected_fixtures,
            verified_transfers_status,
        )
    except ImportError as exc:
        # ImportError inside a checkout is a real failure, not a skip.
        _import_error = exc


class TestR02BenchmarkLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if REPO_ROOT is None:
            raise unittest.SkipTest("scripts/run_r02_benchmark.py not found outside repository")
        if _import_error is not None:
            raise ImportError(
                f"Failed to import calculate_overlap_ms from run_r02_benchmark.py: {_import_error}"
            ) from _import_error

    def test_positive_overlap(self):
        # RX runs from 1000 to 2000
        # TX runs from 1500 to 2500
        # Overlap should be from 1500 to 2000 -> 500 ms
        overlap = calculate_overlap_ms(1000.0, 2000.0, 1500.0, 2500.0)
        self.assertEqual(overlap, 500.0)

    def test_complete_containment_overlap(self):
        # RX contains TX completely
        overlap = calculate_overlap_ms(1000.0, 3000.0, 1200.0, 1800.0)
        self.assertEqual(overlap, 600.0)

        # TX contains RX completely
        overlap2 = calculate_overlap_ms(1200.0, 1800.0, 1000.0, 3000.0)
        self.assertEqual(overlap2, 600.0)

    def test_no_overlap_sequential(self):
        # TX starts after RX finishes
        overlap = calculate_overlap_ms(1000.0, 2000.0, 2500.0, 3500.0)
        self.assertEqual(overlap, 0.0)

    def test_touching_boundary_no_overlap(self):
        # TX starts exactly when RX ends
        overlap = calculate_overlap_ms(1000.0, 2000.0, 2000.0, 3000.0)
        self.assertEqual(overlap, 0.0)

    def test_transport_status_does_not_depend_on_payload_measurements(self):
        from unittest.mock import MagicMock
        from ratatoss.transport import ProcessRun

        rx = ProcessRun(
            pid=1, started_at="", stopped_at="", started_monotonic=100.0,
            stopped_monotonic=105.0, deadline_monotonic=110.0, exit_code=0,
            job=MagicMock(),
        )
        tx = ProcessRun(
            pid=2, started_at="", stopped_at="", started_monotonic=101.0,
            stopped_monotonic=104.0, deadline_monotonic=110.0, exit_code=0,
            job=MagicMock(),
        )
        self.assertEqual(
            transport_run_status("4000", "a" * 64, "a" * 64, rx, tx),
            "pass",
        )
        self.assertEqual(
            transport_run_status("4000", "b" * 64, "a" * 64, rx, tx),
            "fail",
        )

    def test_payload_makespan_uses_sha256_completion(self):
        from unittest.mock import MagicMock
        from ratatoss.transport import ProcessRun

        rx = ProcessRun(
            pid=1, started_at="", stopped_at="", started_monotonic=100.0,
            stopped_monotonic=105.0, deadline_monotonic=110.0, exit_code=0,
            job=MagicMock(), sha256_done_monotonic=106.0,
        )
        tx = ProcessRun(
            pid=2, started_at="", stopped_at="", started_monotonic=101.0,
            stopped_monotonic=104.0, deadline_monotonic=110.0, exit_code=0,
            job=MagicMock(), sha256_done_monotonic=105.0,
        )
        self.assertEqual(calculate_makespan_ms((100.0, 101.0), (rx, tx)), 6000)

    def test_concurrent_rows_keep_sha_marker_as_string(self):
        receiver = build_concurrent_receiver_row(
            "run", "job", "attempt", 1024,
            1000.0, "1300", "a" * 64,
        )
        sender = build_concurrent_sender_row(
            "run", "job", "attempt-bc", 1024,
            1050.0, "1300", "b" * 64,
        )
        for row in (receiver, sender):
            self.assertEqual(row[11:16], ["", "", "1300", "", ""])

    def test_progress_observer_ignores_unrelated_and_incomplete_frames(self):
        from ratatoss.transport import _PayloadProgress

        progress = _PayloadProgress()
        progress.feed(b"Hashing batch-test 50% |", 1.0)
        progress.feed(b"batch-test   0% |", 2.0)
        progress.feed(b"batch-test 100% |", 3.0)
        self.assertIsNone(progress.first)
        self.assertIsNone(progress.last)
        progress.feed(b"batch-test  25% |", 4.0)
        progress.feed(b"batch-test  50% |", 5.0)
        progress.feed(b"batch-test 100% |", 6.0)
        self.assertEqual((progress.first, progress.first_percent, progress.last), (4.0, 25, 6.0))

    def test_selected_sizes_skip_unselected_fixture_validation(self):
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            for name, digest in (
                ("a-32mib.bin", "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a"),
                ("b-to-c-32mib.bin", "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679"),
            ):
                (root / name).write_bytes(b"x" * (32 * 1024 * 1024))

            croc = root / "croc.exe"
            croc.write_bytes(b"croc")
            with patch(
                "run_r02_benchmark.sha256_file",
                side_effect=lambda path: (
                    "25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a"
                    if path.name == "a-32mib.bin"
                    else "7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679"
                    if path.name == "b-to-c-32mib.bin"
                    else "1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e"
                ),
            ):
                validate_selected_fixtures(root, (32,), croc)

    def test_selected_sizes_require_32_mib_fault_fixture_during_preflight(self):
        import tempfile
        from unittest.mock import patch
        from ratatoss.transport import CrocError
        from run_r02_benchmark import FIXTURE_NAMES, WINDOWS_X64_SHA256

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "croc.exe"
            binary.touch()
            hashes = {binary: WINDOWS_X64_SHA256}
            for role in ("A", "B"):
                name, digest = FIXTURE_NAMES[(role, 64)]
                fixture = root / name
                with fixture.open("wb") as stream:
                    stream.truncate(64 * 1024 * 1024)
                hashes[fixture] = digest

            with patch("run_r02_benchmark.sha256_file", side_effect=hashes.__getitem__):
                with self.assertRaisesRegex(CrocError, "LAB_FIXTURE_MISSING: a-32mib.bin"):
                    validate_selected_fixtures(root, (64,), binary)

                name, digest = FIXTURE_NAMES[("A", 32)]
                fault_fixture = root / name
                with fault_fixture.open("wb") as stream:
                    stream.truncate(32 * 1024 * 1024)
                hashes[fault_fixture] = digest
                validate_selected_fixtures(root, (64,), binary)

    def test_verified_transfers_status_accepts_selected_size_only(self):
        import csv
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_file = root / "runs.csv"
            transfers_file = root / "transfers.csv"
            run_rows = []
            transfer_rows = []
            for scenario in ("sequential", "concurrent"):
                for repeat in range(1, 4):
                    run_id = f"32-{scenario}-{repeat}"
                    run_rows.append({
                        "run_id": run_id, "batch_mib": "32",
                        "scenario": scenario, "status": "pass",
                    })
                    for _ in range(1 if scenario == "sequential" else 2):
                        transfer_rows.append({
                            "run_id": run_id, "status": "pass",
                            "verified_sha256": "a" * 64,
                        })

            with runs_file.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=("run_id", "batch_mib", "scenario", "status"))
                writer.writeheader()
                writer.writerows(run_rows)
            with transfers_file.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=("run_id", "status", "verified_sha256"))
                writer.writeheader()
                writer.writerows(transfer_rows)

            status, reason = verified_transfers_status(
                runs_file, transfers_file, selected_sizes=(32,),
            )
            self.assertEqual(status, "pass")
            self.assertEqual(reason, "")

    def test_fault_profile_uses_32_mib_budget(self):
        profile = fault_profile_for_size("test-password", 32)
        self.assertEqual(profile.setup_ms, 1400)
        self.assertEqual(profile.verify_commit_ms, 200)
        self.assertEqual(profile.margin_ms, 200)

        from ratatoss.lease_profile import evaluate_lease_budget

        budget = evaluate_lease_budget(
            batch_bytes=32 * 1024 * 1024,
            min_goodput_bps=100_000_000,
            remaining_lease_ms=4500,
            remaining_adapter_ms=4500,
            remaining_setup_ms=profile.setup_ms,
            verify_commit_ms=profile.verify_commit_ms,
            margin_ms=profile.margin_ms,
        )
        self.assertTrue(budget.fits)

    def test_timeout_receive_plan_uses_fault_profile_not_last_size_profile(self):
        profile = fault_profile_for_size("test-password", 32)
        plan = fault_timeout_receive_plan(profile, 4500.0, 4.5)
        self.assertEqual(plan["remaining_setup_ms"], 1400)
        self.assertEqual(plan["timeout"], 4.5)
        self.assertEqual(plan["lease_deadline"], 4500.0)

    def test_32_mib_fault_profile_passes_timeout_preflight_through_receive(self):
        import asyncio
        import tempfile
        import time
        import unittest.mock
        from pathlib import Path
        from unittest.mock import patch
        from uuid import uuid4

        from ratatoss.transport import Batch, CrocAdapter, CrocError

        class TimedOutChild:
            pid = 456

            def __init__(self):
                self.stopped = False

            def poll(self):
                return None

            def stop(self):
                self.stopped = True
                from ratatoss._croc_process import JobCleanup
                return JobCleanup(1, 0, 1, 0)

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                binary = root / "croc.exe"
                staging = root / "staging"
                staging.mkdir()
                destination = root / "destination.bin"
                profile = fault_profile_for_size("fault-password", 32)
                batch = Batch(uuid4(), 32 * 1024 * 1024, "0" * 64)

                with patch.object(CrocAdapter, "_verify_binary", autospec=True):
                    adapter = BenchmarkAdapter(
                        binary, staging, profile, observe_payload=True,
                    )

                deadline = time.monotonic() + FAULT_TIMEOUT_S
                plan = fault_timeout_receive_plan(profile, deadline, FAULT_TIMEOUT_S)
                child = TimedOutChild()

                with patch("ratatoss.transport.WindowsChild", return_value=child):
                    with self.assertRaisesRegex(CrocError, "^TRANSPORT_TIMEOUT$") as failure:
                        await adapter.receive(
                            destination,
                            "fault-session-code",
                            batch=batch,
                            timeout=plan["timeout"],
                            lease_deadline=plan["lease_deadline"],
                            remaining_setup_ms=plan["remaining_setup_ms"],
                        )

                self.assertTrue(child.stopped)
                self.assertEqual(failure.exception.process.job.active_after_stop, 0)
                self.assertFalse(destination.exists())

        asyncio.run(exercise())

    def test_evidence_ref_uses_repo_relative_r02_path(self):
        from pathlib import Path
        root = REPO_ROOT or Path(__file__).resolve().parents[1]
        output_dir = root / "bench" / "artifacts" / "r02"
        self.assertEqual(
            evidence_ref(output_dir, "r02-seq-32mib-rep1-test"),
            "bench/artifacts/r02/r02-seq-32mib-rep1-test/evidence.json",
        )

    def test_evidence_standard_transfer_fields_match_csv_values(self):
        transfer = {
            "run_id": "run",
            "target_peer": "B",
            "first_byte_monotonic_ms": "100",
            "last_byte_monotonic_ms": "200",
            "setup_ms": "50",
            "goodput_bps": "123",
        }
        details = {"processes": {"B_rx": {
            "first_progress_monotonic_s": 1.25,
            "first_progress_percent": 82,
            "full_progress_monotonic_s": 1.75,
        }}}
        normalized = normalize_evidence_transfer(transfer, details)
        self.assertEqual(normalized["first_byte_monotonic_ms"], "100")
        self.assertEqual(normalized["last_byte_monotonic_ms"], "200")
        self.assertEqual(normalized["setup_ms"], "50")
        self.assertEqual(normalized["goodput_bps"], "123")
        self.assertEqual(normalized["progress_estimate"]["first_progress_percent"], 82)

    def test_verified_transfers_status_requires_all_sizes_scenarios(self):
        import csv
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs_file = root / "runs.csv"
            transfers_file = root / "transfers.csv"

            run_rows = []
            transfer_rows = []
            for size_mib in (32, 64, 128):
                for scenario in ("sequential", "concurrent"):
                    for repeat in range(1, 4):
                        run_id = f"{size_mib}-{scenario}-{repeat}"
                        run_rows.append({
                            "run_id": run_id,
                            "batch_mib": str(size_mib),
                            "scenario": scenario,
                            "status": "pass",
                        })
                        for batch in range(1 if scenario == "sequential" else 2):
                            transfer_rows.append({
                                "run_id": run_id,
                                "status": "pass",
                                "verified_sha256": "a" * 64,
                            })

            with runs_file.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=("run_id", "batch_mib", "scenario", "status"))
                writer.writeheader()
                writer.writerows(run_rows)
            with transfers_file.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=("run_id", "status", "verified_sha256"))
                writer.writeheader()
                writer.writerows(transfer_rows)

            status, reason = verified_transfers_status(runs_file, transfers_file)
            self.assertEqual(status, "pass")
            self.assertEqual(reason, "")

            run_rows[-1]["status"] = "fail"
            with runs_file.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=("run_id", "batch_mib", "scenario", "status"))
                writer.writeheader()
                writer.writerows(run_rows)
            status, reason = verified_transfers_status(runs_file, transfers_file)
            self.assertEqual(status, "blocked")
            self.assertIn("128 MiB concurrent", reason)


if __name__ == "__main__":
    unittest.main()
