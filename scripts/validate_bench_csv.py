#!/usr/bin/env python3
"""Validate benchmark CSV files (runs.csv and transfers.csv)."""

import argparse
import csv
from pathlib import Path
import sys

RUNS_HEADER = [
    "run_id", "gate", "scenario", "baseline", "repeat", "seed", "commit",
    "os", "croc_version", "croc_sha256", "relay_config", "network_profile",
    "fixture_sha256", "file_bytes", "batch_mib", "rx_slots", "tx_slots",
    "status", "makespan_ms", "source_payload_bytes", "source_wire_bytes",
    "wan_wire_bytes", "wan_measurement_scope", "retry_payload_bytes",
    "recovery_ms", "optional_replication_bytes", "setup_p50_ms",
    "setup_p95_ms", "peer_utilization_ref", "evidence_ref", "notes"
]

TRANSFERS_HEADER = [
    "run_id", "job_id", "assignment_id", "batch_id", "source_peer",
    "target_peer", "observer_peer", "path_kind", "payload_bytes",
    "payload_sent_bytes", "start_monotonic_ms", "first_byte_monotonic_ms",
    "last_byte_monotonic_ms", "end_monotonic_ms", "setup_ms",
    "goodput_bps", "verified_sha256", "status", "is_retry",
    "is_replication", "notes"
]

VALID_STATUSES = {"pass", "fail", "timeout", "blocked", "not_run"}

RUNS_MEASURE_FIELDS = {
    "makespan_ms", "source_payload_bytes", "source_wire_bytes",
    "wan_wire_bytes", "retry_payload_bytes", "recovery_ms",
    "optional_replication_bytes", "setup_p50_ms", "setup_p95_ms"
}

TRANSFERS_MEASURE_FIELDS = {
    "payload_bytes", "payload_sent_bytes", "start_monotonic_ms",
    "first_byte_monotonic_ms", "last_byte_monotonic_ms",
    "end_monotonic_ms", "setup_ms", "goodput_bps"
}


def validate_csv(runs_path: Path, transfers_path: Path) -> list[str]:
    errors = []

    if not runs_path.exists():
        return [f"Runs file not found: {runs_path}"]
    if not transfers_path.exists():
        return [f"Transfers file not found: {transfers_path}"]

    run_ids = set()

    # Validate runs.csv
    try:
        with runs_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                return [f"{runs_path.name}: file is empty"]

            if header != RUNS_HEADER:
                return [f"{runs_path.name} line 1: field 'header': invalid runs header"]

            row_idx = 1
            for row in reader:
                row_idx += 1
                if len(row) != len(RUNS_HEADER):
                    errors.append(f"{runs_path.name} line {row_idx}: field 'columns': expected {len(RUNS_HEADER)} columns, got {len(row)}")
                    continue

                row_dict = dict(zip(RUNS_HEADER, row))
                run_id = row_dict["run_id"].strip()
                if not run_id:
                    errors.append(f"{runs_path.name} line {row_idx}: field 'run_id': empty run_id")
                elif run_id in run_ids:
                    errors.append(f"{runs_path.name} line {row_idx}: field 'run_id': duplicate run_id")
                else:
                    run_ids.add(run_id)

                # Kiểm tra status CHÍNH XÁC, không dùng .strip()
                status = row_dict["status"]
                if status not in VALID_STATUSES:
                    errors.append(f"{runs_path.name} line {row_idx}: field 'status': invalid status")

                notes = row_dict["notes"].strip()
                has_empty_measure = any(not row_dict[field].strip() for field in RUNS_MEASURE_FIELDS)
                if has_empty_measure and not notes:
                    errors.append(f"{runs_path.name} line {row_idx}: field 'notes': measurement fields are empty without notes justification")

    except csv.Error:
        line_num = getattr(reader, "line_num", 1) if "reader" in locals() else 1
        errors.append(f"{runs_path.name} line {line_num}: CSV syntax error")
    except Exception as e:
        return [f"{runs_path.name}: error reading file: {e}"]

    # Validate transfers.csv
    try:
        with transfers_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                return [f"{transfers_path.name}: file is empty"]

            if header != TRANSFERS_HEADER:
                return [f"{transfers_path.name} line 1: field 'header': invalid transfers header"]

            transfer_row_idx = 1
            for row in reader:
                transfer_row_idx += 1
                if len(row) != len(TRANSFERS_HEADER):
                    errors.append(f"{transfers_path.name} line {transfer_row_idx}: field 'columns': expected {len(TRANSFERS_HEADER)} columns, got {len(row)}")
                    continue

                row_dict = dict(zip(TRANSFERS_HEADER, row))
                t_run_id = row_dict["run_id"].strip()
                if not t_run_id:
                    errors.append(f"{transfers_path.name} line {transfer_row_idx}: field 'run_id': empty run_id")
                elif t_run_id not in run_ids:
                    errors.append(f"{transfers_path.name} line {transfer_row_idx}: field 'run_id': run_id not found in runs.csv")

                # Kiểm tra status CHÍNH XÁC, không dùng .strip()
                t_status = row_dict["status"]
                if t_status not in VALID_STATUSES:
                    errors.append(f"{transfers_path.name} line {transfer_row_idx}: field 'status': invalid status")

                t_notes = row_dict["notes"].strip()
                t_has_empty_measure = any(not row_dict[field].strip() for field in TRANSFERS_MEASURE_FIELDS)
                if t_has_empty_measure and not t_notes:
                    errors.append(f"{transfers_path.name} line {transfer_row_idx}: field 'notes': measurement fields are empty without notes justification")

    except csv.Error:
        line_num = getattr(reader, "line_num", 1) if "reader" in locals() else 1
        errors.append(f"{transfers_path.name} line {line_num}: CSV syntax error")
    except Exception as e:
        errors.append(f"{transfers_path.name}: error reading file: {e}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate benchmark runs and transfers CSV files.")
    parser.add_argument("runs", type=Path, help="Path to runs.csv")
    parser.add_argument("transfers", type=Path, help="Path to transfers.csv")
    args = parser.parse_args()

    runs_path = args.runs
    transfers_path = args.transfers

    errors = validate_csv(runs_path, transfers_path)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    run_ids = set()
    try:
        with runs_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            next(reader, None)
            for row in reader:
                if row:
                    run_ids.add(row[0].strip())
    except Exception:
        pass

    print(f"Benchmark CSV files are valid ({len(run_ids)} run(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())