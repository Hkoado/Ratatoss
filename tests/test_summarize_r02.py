import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.summarize_r02 import summarize_runs
from scripts.validate_bench_csv import RUNS_HEADER, TRANSFERS_HEADER


class TestSummarizeR02(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = self.root / "runs.csv"
        self.transfers = self.root / "transfers.csv"
        self.script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "summarize_r02.py"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def write_csv(self, path, header, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    def make_run_row(self, run_id, batch_mib, scenario, status):
        row = [""] * len(RUNS_HEADER)
        row[RUNS_HEADER.index("run_id")] = run_id
        row[RUNS_HEADER.index("batch_mib")] = batch_mib
        row[RUNS_HEADER.index("scenario")] = scenario
        row[RUNS_HEADER.index("status")] = status
        row[RUNS_HEADER.index("notes")] = "test data"
        return row

    def test_empty_templates_report_zero(self):
        self.write_csv(self.runs, RUNS_HEADER, [])
        self.write_csv(self.transfers, TRANSFERS_HEADER, [])

        result = subprocess.run(
            [sys.executable, str(self.script), str(self.runs), str(self.transfers)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("0 run(s).", result.stdout)

    def test_counts_by_batch_scenario_status(self):
        rows = [
            self.make_run_row("run-1", "32", "serial", "pass"),
            self.make_run_row("run-2", "32", "serial", "pass"),
            self.make_run_row("run-3", "64", "concurrent", "timeout"),
            self.make_run_row("run-4", "64", "concurrent", "fail"),
            self.make_run_row("run-5", "32", "serial", "blocked"),
            self.make_run_row("run-6", "32", "serial", "not_run"),
        ]

        self.write_csv(self.runs, RUNS_HEADER, rows)
        self.write_csv(self.transfers, TRANSFERS_HEADER, [])

        counts = summarize_runs(self.runs)

        self.assertEqual(
            counts,
            [
                ("32", "serial", "blocked", 1),
                ("32", "serial", "not_run", 1),
                ("32", "serial", "pass", 2),
                ("64", "concurrent", "fail", 1),
                ("64", "concurrent", "timeout", 1),
            ],
        )

    def test_cli_counts_valid_data(self):
        rows = [
            self.make_run_row("run-1", "32", "serial", "pass"),
            self.make_run_row("run-2", "32", "serial", "pass"),
            self.make_run_row("run-3", "64", "concurrent", "timeout"),
        ]

        self.write_csv(self.runs, RUNS_HEADER, rows)
        self.write_csv(self.transfers, TRANSFERS_HEADER, [])

        result = subprocess.run(
            [sys.executable, str(self.script), str(self.runs), str(self.transfers)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("32,serial,pass,2", result.stdout)
        self.assertIn("64,concurrent,timeout,1", result.stdout)

    def test_invalid_status_exits_nonzero(self):
        secret_status = "BAD_STATUS_SENSITIVE_XYZ"
        row = self.make_run_row("run-invalid", "32", "serial", secret_status)

        self.write_csv(self.runs, RUNS_HEADER, [row])
        self.write_csv(self.transfers, TRANSFERS_HEADER, [])

        result = subprocess.run(
            [sys.executable, str(self.script), str(self.runs), str(self.transfers)],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid status", result.stderr)
        self.assertNotIn(secret_status, result.stderr)
        self.assertNotIn("run-invalid", result.stderr)

    def test_invalid_header_exits_nonzero(self):
        self.write_csv(self.runs, ["wrong", "header"], [])
        self.write_csv(self.transfers, TRANSFERS_HEADER, [])

        result = subprocess.run(
            [sys.executable, str(self.script), str(self.runs), str(self.transfers)],
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid runs header", result.stderr)


if __name__ == "__main__":
    unittest.main()
