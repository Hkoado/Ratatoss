import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate_bench_csv import RUNS_HEADER, TRANSFERS_HEADER, validate_csv


class TestValidateBenchCsv(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        self.runs_file = self.tmp_path / "runs.csv"
        self.transfers_file = self.tmp_path / "transfers.csv"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def write_csvs(self, runs_rows, transfers_rows):
        with self.runs_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(RUNS_HEADER)
            for row in runs_rows:
                writer.writerow(row)

        with self.transfers_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TRANSFERS_HEADER)
            for row in transfers_rows:
                writer.writerow(row)

    def test_valid_empty_runs(self):
        # Hai mẫu chỉ có tiêu đề (0 lượt chạy)
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
        run_row[-1] = ""  # notes bị bỏ trống

        transfer_row = [""] * len(TRANSFERS_HEADER)
        transfer_row[0] = "run_001"
        transfer_row[17] = "pass"
        transfer_row[-1] = ""

        self.write_csvs([run_row], [transfer_row])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("measurement fields are empty without notes justification" in err for err in errors))

    def test_invalid_header(self):
        with self.runs_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wrong", "header"])
        with self.transfers_file.open("w", encoding="utf-8", newline="") as f:
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
        # Xác minh không in giá trị bản ghi (run_001) ra chẩn đoán lỗi
        self.assertFalse(any("run_001" in err for err in errors))

    def test_invalid_status(self):
        run_row = [""] * len(RUNS_HEADER)
        run_row[0] = "run_001"
        run_row[17] = "unknown_status"
        run_row[-1] = "notes"

        self.write_csvs([run_row], [])
        errors = validate_csv(self.runs_file, self.transfers_file)
        self.assertTrue(any("invalid status" in err for err in errors))
        # Xác minh không in giá trị bản ghi (unknown_status) ra chẩn đoán lỗi
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
        # Xác minh không in giá trị bản ghi (run_999) ra chẩn đoán lỗi
        self.assertFalse(any("run_999" in err for err in errors))

    def test_subprocess_with_templates(self):
        # Chạy subprocess với 2 mẫu gốc trong bench/
        repo_root = Path(__file__).resolve().parent.parent
        bench_runs = repo_root / "bench" / "runs.csv"
        bench_transfers = repo_root / "bench" / "transfers.csv"
        script_path = repo_root / "scripts" / "validate_bench_csv.py"

        res = subprocess.run([sys.executable, str(script_path), str(bench_runs), str(bench_transfers)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 run(s)", res.stdout)

    def test_subprocess_with_invalid_copy(self):
        # Chạy subprocess với bản sao có lỗi và kiểm tra không in nội dung bản ghi
        repo_root = Path(__file__).resolve().parent.parent
        bench_transfers = repo_root / "bench" / "transfers.csv"
        script_path = repo_root / "scripts" / "validate_bench_csv.py"

        secret_status = "BAD_STATUS_SENSITIVE_XYZ"
        secret_run_id = "RUN_ID_SENSITIVE_123"
        invalid_runs = self.tmp_path / "invalid_runs.csv"
        with invalid_runs.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(RUNS_HEADER)
            bad_row = [""] * len(RUNS_HEADER)
            bad_row[0] = secret_run_id
            bad_row[17] = secret_status
            bad_row[-1] = "notes"
            writer.writerow(bad_row)

        res = subprocess.run([sys.executable, str(script_path), str(invalid_runs), str(bench_transfers)], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        # Khẳng định không in nội dung bản ghi nhạy cảm
        self.assertNotIn(secret_status, res.stderr)
        self.assertNotIn(secret_run_id, res.stderr)
        self.assertIn("invalid status", res.stderr)


if __name__ == "__main__":
    unittest.main()