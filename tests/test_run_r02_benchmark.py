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
            calculate_payload_overlap_ms,
            payload_goodput_bps,
            setup_measure,
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

    def test_missing_payload_marker_returns_empty_overlap(self):
        overlap = calculate_payload_overlap_ms("", "2000", "1500", "2500")
        self.assertIsNone(overlap)

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
            1000.0, "1100", "1200", "1300",
            "100", "800000", "a" * 64, "50.0",
        )
        sender = build_concurrent_sender_row(
            "run", "job", "attempt-bc", 1024,
            1050.0, "1150", "1250", "1300",
            "100", "800000", "b" * 64, "50.0",
        )
        self.assertEqual(receiver[13], "1300")
        self.assertEqual(sender[13], "1300")
        self.assertNotIn("e: ", receiver)

    def test_setup_ms_empty_when_first_byte_missing(self):
        """Missing payload markers must produce empty CSV measurements, not a proxy."""
        from dataclasses import replace
        from ratatoss.transport import ProcessRun
        from unittest.mock import MagicMock

        # Create a ProcessRun without first_byte_monotonic
        run = ProcessRun(
            pid=1234,
            started_at="2026-01-01T00:00:00Z",
            stopped_at="2026-01-01T00:00:05Z",
            started_monotonic=1000.0,
            stopped_monotonic=1005.0,
            deadline_monotonic=1045.0,
            exit_code=0,
            job=MagicMock(),
            first_byte_monotonic=None,  # Missing marker
            last_byte_monotonic=None,
            sha256_done_monotonic=None,
        )

        self.assertEqual(setup_measure(run), "")
        self.assertEqual(payload_goodput_bps(1024, run), "")

    def test_last_byte_missing_produces_empty_goodput(self):
        """Missing last-byte payload marker must not substitute process duration."""
        from unittest.mock import MagicMock
        from ratatoss.transport import ProcessRun

        run = ProcessRun(
            pid=1234,
            started_at="2026-01-01T00:00:00Z",
            stopped_at="2026-01-01T00:00:05Z",
            started_monotonic=1000.0,
            stopped_monotonic=1005.0,
            deadline_monotonic=1045.0,
            exit_code=0,
            job=MagicMock(),
            first_byte_monotonic=1001.0,
            last_byte_monotonic=None,  # Missing marker
            sha256_done_monotonic=None,
        )

        self.assertEqual(payload_goodput_bps(1024, run), "")
        self.assertIsNone(calculate_makespan_ms((run.started_monotonic,), (run,)))

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

    def test_goodput_excludes_payload_already_received_at_first_sample(self):
        from types import SimpleNamespace

        run = SimpleNamespace(
            first_byte_monotonic=4.0, first_progress_percent=25, last_byte_monotonic=6.0,
        )
        self.assertEqual(payload_goodput_bps(1024, run), "3072")


if __name__ == "__main__":
    unittest.main()
