#!/usr/bin/env python3
"""Đếm lượt chạy R0.2 theo batch_mib, scenario và status."""

import argparse
import csv
from collections import Counter
from pathlib import Path
import sys

try:
    from .validate_bench_csv import validate_csv
except ImportError:
    from validate_bench_csv import validate_csv


def summarize_runs(runs_path: Path) -> list[tuple[str, str, str, int]]:
    counts: Counter[tuple[str, str, str]] = Counter()

    with runs_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (
                row["batch_mib"].strip(),
                row["scenario"].strip(),
                row["status"].strip(),
            )
            counts[key] += 1

    return [
        (batch_mib, scenario, status, count)
        for (batch_mib, scenario, status), count in sorted(counts.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rà cặp CSV benchmark và đếm lượt chạy R0.2."
    )
    parser.add_argument("runs", type=Path, help="Path to runs.csv")
    parser.add_argument("transfers", type=Path, help="Path to transfers.csv")
    args = parser.parse_args()

    errors = validate_csv(args.runs, args.transfers)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    try:
        rows = summarize_runs(args.runs)
    except (csv.Error, KeyError, OSError) as error:
        print(f"Could not summarize runs.csv: {error}", file=sys.stderr)
        return 1

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["batch_mib", "scenario", "status", "count"])

    for batch_mib, scenario, status, count in rows:
        writer.writerow([batch_mib, scenario, status, count])

    if not rows:
        print("0 run(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())