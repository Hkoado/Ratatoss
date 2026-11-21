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


if __name__ == "__main__":
    unittest.main()
