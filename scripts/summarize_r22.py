#!/usr/bin/env python3
"""Summarize a measured R2.2 runs.csv/transfers.csv pair as JSON.

Pass a third JSON file mapping caller-defined configuration names to objects
with a run_ids array and an optional matched_controls array. For example:

    {"wan-64": {"run_ids": ["r1", "r2"], "matched_controls": ["plars_static"]}}

Each runs.csv ID belongs to exactly one configuration. A matched_controls
entry attests that the named baseline and plars used matching conditions in
each scenario in this configuration, including conditions outside the CSV
such as topology, allowed routes, bottlenecks, and resource budgets. Use
separate configurations when the comparison conditions differ.

Comparisons also require identical populated CSV condition fields on the
passing runs used for both makespan medians. Each side needs at least one
passing run with makespan. The report includes the sample counts and retains
the notes, missing measurements, and source references for every run.
"""

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

if __package__:
    from .validate_bench_csv import RUNS_MEASURE_FIELDS, validate_csv
else:
    from validate_bench_csv import RUNS_MEASURE_FIELDS, validate_csv


MEASUREMENTS = sorted(RUNS_MEASURE_FIELDS)
CONDITION_FIELDS = (
    "gate", "commit", "os", "croc_version", "croc_sha256", "relay_config",
    "network_profile", "fixture_sha256", "file_bytes", "batch_mib",
    "rx_slots", "tx_slots",
)


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def index_configurations(configurations, expected_ids):
    if not isinstance(configurations, dict):
        raise ValueError("The comparison configuration must be a JSON object")

    by_run = {}
    controls = {}
    for name, configuration in configurations.items():
        if not nonempty_string(name) or not isinstance(configuration, dict):
            raise ValueError("Each comparison configuration needs a nonempty name and an object")
        run_ids = configuration.get("run_ids")
        if not isinstance(run_ids, list) or not all(map(nonempty_string, run_ids)):
            raise ValueError(f"{name}: run_ids must be an array of nonempty run IDs")
        matched = configuration.get("matched_controls", [])
        if not isinstance(matched, list) or not all(map(nonempty_string, matched)):
            raise ValueError(f"{name}: matched_controls must be an array of baseline names")
        if "plars" in matched or len(set(matched)) != len(matched):
            raise ValueError(f"{name}: matched_controls must be distinct controls for PLARS")
        controls[name] = sorted(matched)

        for run_id in run_ids:
            if run_id in by_run:
                raise ValueError(f"Run {run_id!r} is assigned more than once")
            by_run[run_id] = name

    missing = expected_ids - by_run.keys()
    unknown = by_run.keys() - expected_ids
    if missing or unknown:
        raise ValueError(f"Missing run assignments: {sorted(missing)}. Unknown runs: {sorted(unknown)}.")
    return by_run, controls


def read_runs(path):
    runs = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        for row in reader:
            run_id = row["run_id"].strip()
            scenario = row["scenario"].strip()
            baseline = row["baseline"].strip()
            if not scenario or not baseline:
                raise ValueError(f"Run {run_id!r} needs a scenario and baseline")

            values = {}
            for field in MEASUREMENTS:
                cell = row[field].strip()
                if not cell:
                    values[field] = None
                    continue
                try:
                    value = int(cell)
                except ValueError:
                    try:
                        value = float(cell)
                    except ValueError:
                        value = None
                if value is None or value < 0 or (isinstance(value, float) and not math.isfinite(value)):
                    raise ValueError(f"Run {run_id!r}: {field} must be a finite nonnegative number")
                values[field] = value

            runs.append({
                "run_id": run_id,
                "scenario": scenario,
                "baseline": baseline,
                "status": row["status"],
                "evidence_ref": row["evidence_ref"].strip(),
                "source_csv_line": reader.line_num,
                "notes": row["notes"],
                "measurements": values,
                "conditions": {key: row[key].strip() for key in CONDITION_FIELDS},
            })
    return runs


def summarize_group(runs):
    status_counts = Counter(run["status"] for run in runs)
    passing = [run for run in runs if run["status"] == "pass"]
    stats = {}
    for field in MEASUREMENTS:
        values = [
            run["measurements"][field] for run in passing
            if run["measurements"][field] is not None
        ]
        stats[field] = {
            "count": len(values),
            "median": median(values) if values else None,
            "min": min(values, default=None),
            "max": max(values, default=None),
        }
    return {
        "passed": status_counts["pass"],
        "total": len(runs),
        "status_counts": dict(status_counts),
        "passing_measurement_stats": stats,
        "runs": runs,
    }


def compare_makespan(plars, control):
    samples = [
        [run for run in runs if run["status"] == "pass" and run["measurements"]["makespan_ms"] is not None]
        for runs in (plars, control)
    ]
    plars_samples, control_samples = samples
    counts = {"plars_count": len(plars_samples), "control_count": len(control_samples)}
    if not plars_samples or not control_samples:
        return {**counts, "status": "insufficient_makespan"}

    signatures = {tuple(run["conditions"].values()) for sample in samples for run in sample}
    if len(signatures) != 1 or not all(next(iter(signatures))):
        return {**counts, "status": "unmatched_csv_conditions"}

    plars_median, control_median = (
        median(run["measurements"]["makespan_ms"] for run in sample) for sample in samples
    )
    return {
        **counts,
        "status": "compared",
        "plars_median_ms": plars_median,
        "control_median_ms": control_median,
        "plars_slower": plars_median > control_median,
    }


def summarize_runs(runs_path, transfers_path, configurations):
    errors = validate_csv(runs_path, transfers_path)
    if errors:
        raise ValueError("\n".join(errors))

    runs = read_runs(runs_path)
    by_run, controls = index_configurations(configurations, {run["run_id"] for run in runs})
    grouped = defaultdict(list)
    for run in runs:
        key = (run["scenario"], by_run[run["run_id"]], run["baseline"])
        grouped[key].append(run)

    groups = []
    comparisons = []
    for (scenario, configuration, baseline), members in sorted(grouped.items()):
        groups.append({
            "scenario": scenario,
            "configuration": configuration,
            "baseline": baseline,
            **summarize_group(members),
        })
        if baseline == "plars":
            for control in controls[configuration]:
                comparisons.append({
                    "scenario": scenario,
                    "configuration": configuration,
                    "control": control,
                    **compare_makespan(members, grouped.get((scenario, configuration, control), [])),
                })

    return {"source_runs_csv": str(runs_path), "groups": groups, "comparisons": comparisons}


def main():
    parser = argparse.ArgumentParser(
        description="Summarize R2.2 benchmark CSVs and confirmed PLARS comparisons.",
        epilog="\n".join(__doc__.splitlines()[2:]),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("runs", type=Path, help="Path to runs.csv")
    parser.add_argument("transfers", type=Path, help="Path to transfers.csv")
    parser.add_argument("configurations", type=Path, help="Path to the comparison configuration JSON")
    args = parser.parse_args()
    try:
        with args.configurations.open(encoding="utf-8-sig") as source:
            configurations = json.load(source)
        summary = summarize_runs(args.runs, args.transfers, configurations)
        output = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)
    except (csv.Error, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
