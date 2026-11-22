"""Summarize validated R0.2 benchmark CSV artifacts."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def summarize(runs_path: Path) -> dict:
    with runs_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))

    scenarios = defaultdict(list)
    for row in rows:
        if row["status"] == "pass":
            scenarios[(row["batch_mib"], row["scenario"])].append(row)

    summary = []
    for (size_mib, scenario), rows_in_group in sorted(
        scenarios.items(), key=lambda item: (int(item[0][0]), item[0][1])
    ):
        makespans = [int(row["makespan_ms"]) for row in rows_in_group if row["makespan_ms"]]
        summary.append({
            "size_mib": int(size_mib),
            "scenario": scenario,
            "passes": len(rows_in_group),
            "makespan_ms_avg": round(sum(makespans) / len(makespans)) if makespans else None,
        })
    return {"passes": sum(item["passes"] for item in summary), "scenarios": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs_csv", type=Path)
    args = parser.parse_args()
    print(summarize(args.runs_csv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
