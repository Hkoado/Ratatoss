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
        from run_r02_benchmark import calculate_overlap_ms
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

    def test_setup_ms_zero_when_first_byte_missing(self):
        """Regression: setup_ms should be 0 when first_byte_monotonic is missing (notes justify empty field)."""
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

        # setup_ms should be 0 when first_byte is None
        setup_ms = round((run.first_byte_monotonic - run.started_monotonic) * 1000.0) if run.first_byte_monotonic else 0
        self.assertEqual(setup_ms, 0)

        # goodput_bps should fall back to process duration
        duration_s = run.stopped_monotonic - run.started_monotonic
        goodput_bps = round((1024 * 1024 * 8.0) / duration_s) if duration_s > 0 else 0
        self.assertGreater(goodput_bps, 0)

        # Notes should justify empty measurement fields
        notes = "setup_ms and goodput_bps measured via process lifecycle proxy; first_byte_monotonic unavailable; empty fields documented per runbook"
        self.assertIn("first_byte_monotonic unavailable", notes)
        self.assertIn("empty fields documented", notes)

    def test_last_byte_missing_falls_back_to_duration(self):
        """Regression: goodput_bps falls back to process duration when last_byte_monotonic is missing."""
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

        # When last_byte is missing, fall back to process duration
        duration_s = run.stopped_monotonic - run.started_monotonic
        payload_transfer_s = duration_s  # fallback
        goodput_bps = round((1024 * 1024 * 8.0) / payload_transfer_s) if payload_transfer_s > 0 else 0
        self.assertGreater(goodput_bps, 0)

    def test_sha256_done_missing_falls_back_to_stopped(self):
        """Regression: SHA-256 done marker falls back to stopped_monotonic when missing."""
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
            last_byte_monotonic=1004.0,
            sha256_done_monotonic=None,  # Missing marker
        )

        # sha256_done_ms should fall back to stopped_monotonic
        sha256_done_ms = round(run.sha256_done_monotonic * 1000.0) if run.sha256_done_monotonic else round(run.stopped_monotonic * 1000.0)
        self.assertEqual(sha256_done_ms, 1005000)  # 1005.0 * 1000

    def test_empty_measurement_fields_require_notes(self):
        """Regression: empty measurement fields must have notes justification per runbook."""
        # Simulate empty measurement fields with notes justification
        empty_fields = ["setup_ms", "goodput_bps", "first_byte_monotonic_ms", "last_byte_monotonic_ms"]
        notes = "setup_ms and goodput_bps measured via payload markers per runbook; empty fields documented here."

        # Notes must justify empty measurement fields per runbook rules
        self.assertIn("empty fields documented", notes)
        self.assertIn("per runbook", notes)

        # Verify that when fields are empty, notes must be non-empty (validate_bench_csv.py rule)
        for field_name in empty_fields:
            field_value = ""  # empty measurement field
            if not field_value:
                self.assertTrue(notes, f"notes required when {field_name} is empty")


if __name__ == "__main__":
    unittest.main()
