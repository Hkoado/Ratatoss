import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def _resolve_repo_root() -> Path | None:
    # 1. Môi trường checkout thông thường
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "scripts" / "validate_bench_csv.py").is_file():
        return candidate
    # 2. Môi trường GitHub Actions CI (bước smoke test chạy ngoài checkout)
    if "GITHUB_WORKSPACE" in os.environ:
        workspace = Path(os.environ["GITHUB_WORKSPACE"]).resolve()
        if (workspace / "scripts" / "validate_bench_csv.py").is_file():
            return workspace
    # 3. Tìm từ thư mục làm việc hiện tại hoặc các thư mục cha
    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        if (directory / "scripts" / "validate_bench_csv.py").is_file():
            return directory
    return None


REPO_ROOT = _resolve_repo_root()
if REPO_ROOT is not None:
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from validate_bench_csv import RUNS_HEADER, TRANSFERS_HEADER, validate_csv
    except ImportError:
        validate_csv = None
        RUNS_HEADER = []
        TRANSFERS_HEADER = []
else:
    validate_csv = None
    RUNS_HEADER = []
    TRANSFERS_HEADER = []


class TestValidateBenchCsv(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if validate_csv is None or REPO_ROOT is None:
            raise unittest.SkipTest("scripts/validate_bench_csv.py not found outside repository")

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.runs_file = self.tmp_path / "runs.csv"
        self.transfers_file = self.tmp_path / "transfers.csv"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def write_csvs(self, runs_rows, transfers_rows):
        with self.runs_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(RUNS_HEADER)
            for row in runs_rows:
                writer.writerow(row)

        with self.transfers_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TRANSFERS_HEADER)
            for row in transfers_rows:
                writer.writerow(row)

    def test_valid_empty_runs(self):
        self.write_csvs([], [])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertEqual(errors, [])

    def test_valid_data(self):
        run_row = [""] * len(RUNS_HEADER)
        run_row[0] = "run_001"
        run_row[17] = "pass"
        run_row[-1] = "notes explaining empty measures"

        transfer_row = [""] * len(TRANSFERS_HEADER)
        transfer_row[0] = "run_001"
        transfer_row[17] = "pass"
        transfer_row[-1] = "notes present"

        self.write_csvs([run_row], [transfer_row])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertEqual(errors, [])

    def test_empty_measure_without_notes_fails(self):
        run_row = [""] * len(RUNS_HEADER)
        run_row[0] = "run_001"
        run_row[17] = "pass"
        run_row[-1] = ""

        transfer_row = [""] * len(TRANSFERS_HEADER)
        transfer_row[0] = "run_001"
        transfer_row[17] = "pass"
        transfer_row[-1] = ""

        self.write_csvs([run_row], [transfer_row])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("measurement fields are empty without notes justification" in err for err in errors))

    def test_invalid_header(self):
        with self.runs_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wrong", "header"])
        with self.transfers_file.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TRANSFERS_HEADER)

        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("invalid runs header" in err for err in errors))

    def test_duplicate_run_id(self):
        run_row1 = [""] * len(RUNS_HEADER)
        run_row1[0] = "run_001"
        run_row1[17] = "pass"
        run_row1[-1] = "notes"

        run_row2 = list(run_row1)

        self.write_csvs([run_row1, run_row2], [])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("duplicate run_id" in err for err in errors))
        self.assertFalse(any("run_001" in err for err in errors))

    def test_invalid_status(self):
        run_row = [""] * len(RUNS_HEADER)
        run_row[0] = "run_001"
        run_row[17] = "unknown_status"
        run_row[-1] = "notes"

        self.write_csvs([run_row], [])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("invalid status" in err for err in errors))
        self.assertFalse(any("unknown_status" in err for err in errors))

    def test_missing_run_id_in_runs(self):
        run_row = [""] * len(RUNS_HEADER)
        run_row[0] = "run_001"
        run_row[17] = "pass"
        run_row[-1] = "notes"

        transfer_row = [""] * len(TRANSFERS_HEADER)
        transfer_row[0] = "run_999"
        transfer_row[17] = "pass"
        transfer_row[-1] = "notes"

        self.write_csvs([run_row], [transfer_row])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("not found in runs.csv" in err for err in errors))
        self.assertFalse(any("run_999" in err for err in errors))

    def test_subprocess_with_templates(self):
        bench_runs = REPO_ROOT / "bench" / "runs.csv"
        bench_transfers = REPO_ROOT / "bench" / "transfers.csv"
        script_path = REPO_ROOT / "scripts" / "validate_bench_csv.py"

        res = subprocess.run([sys.executable, str(script_path), str(bench_runs), str(bench_transfers)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 run(s)", res.stdout)

    def test_subprocess_with_invalid_copy(self):
        bench_transfers = REPO_ROOT / "bench" / "transfers.csv"
        script_path = REPO_ROOT / "scripts" / "validate_bench_csv.py"

        secret_status = "BAD_STATUS_SENSITIVE_XYZ"
        secret_run_id = "RUN_ID_SENSITIVE_123"
        invalid_runs = self.tmp_path / "invalid_runs.csv"
        with invalid_runs.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(RUNS_HEADER)
            bad_row = [""] * len(RUNS_HEADER)
            bad_row[0] = secret_run_id
            bad_row[17] = secret_status
            bad_row[-1] = "notes"
            writer.writerow(bad_row)

        res = subprocess.run([sys.executable, str(script_path), str(invalid_runs), str(bench_transfers)], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn(secret_status, res.stderr)
        self.assertNotIn(secret_run_id, res.stderr)
        self.assertIn("invalid status", res.stderr)


if __name__ == "__main__":
    unittest.main()