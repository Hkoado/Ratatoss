#!/usr/bin/env python3
"""Generate the ordered R2.2 run plan for the #12 benchmark runner.

Pass a UTF-8 JSON file with an integer seed, repeats (at least 5), and a
scenarios array. Each scenario has an id and a configurations array. Each
configuration has an id, a conditions object, and a policies object.
Conditions describe the shared topology, allowed_routes, bottlenecks,
batch_mib, rx_slots, tx_slots, and budget. The batch size must be positive.
RX and TX limits are nonnegative integers, either shared or keyed by node.
Conditions can also hold settings such as the fixture and network profile.
The policies object has one options object for each baseline:
direct, gateway_whole_file, fixed_split,
gateway_pipeline, plars, and plars_static. Use {} for a policy with no extra
options. All policies use the shared conditions. plars_static supplies its
fixed schedule (inline or as a reference) in its schedule option.

The output retains those configurations and adds a schema_version and an
ordered runs array. Resolve each run's scenario and configuration ids against
scenarios, then apply the options for its baseline. Process runs in array
order. Each round has one run per baseline in seeded order. Warmups have
warmup=true and repeat=0. Copy only measurement runs to the benchmark CSVs,
using run_id, scenario, baseline, repeat, and seed from the plan. The runner
records the actual results and evidence separately.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path


BASELINES = (
    "direct", "gateway_whole_file", "fixed_split", "gateway_pipeline",
    "plars", "plars_static",
)
MATCHED_CONDITIONS = (
    "topology", "allowed_routes", "bottlenecks", "batch_mib",
    "rx_slots", "tx_slots", "budget",
)
MIN_REPEATS = 5


def named_entries(entries, name):
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{name} must be a nonempty array")

    seen = set()
    for entry in entries:
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(entry_id, str) or not entry_id or entry_id != entry_id.strip():
            raise ValueError(f"Each entry in {name} needs a nonempty id without outer whitespace")
        if entry_id in seen:
            raise ValueError(f"Duplicate id in {name}: {entry_id}")
        seen.add(entry_id)
        yield entry_id, entry


def validate_configuration(configuration, name):
    conditions = configuration.get("conditions")
    if not isinstance(conditions, dict):
        raise ValueError(f"{name} needs a conditions object")
    missing = [key for key in MATCHED_CONDITIONS if conditions.get(key) is None]
    if missing:
        raise ValueError(f"{name} is missing shared conditions: {', '.join(missing)}")

    batch_mib = conditions["batch_mib"]
    if type(batch_mib) not in (int, float) or batch_mib <= 0:
        raise ValueError(f"{name}/batch_mib must be a positive number")
    for field in ("rx_slots", "tx_slots"):
        limits = conditions[field]
        if isinstance(limits, dict):
            entries = ((f"{field}.{node}", limit) for node, limit in limits.items())
        else:
            entries = ((field, limits),)
        for path, limit in entries:
            if type(limit) is not int or limit < 0:
                raise ValueError(f"{name}/{path} must be a nonnegative integer")

    policies = configuration.get("policies")
    if not isinstance(policies, dict) or policies.keys() != set(BASELINES):
        raise ValueError(f"{name} must define exactly these policies: {', '.join(BASELINES)}")
    for baseline, options in policies.items():
        if not isinstance(options, dict):
            raise ValueError(f"{name}/{baseline} options must be an object")
        overrides = options.keys() & conditions.keys()
        if overrides:
            raise ValueError(f"{name}/{baseline} overrides shared conditions: {', '.join(sorted(overrides))}")
    schedule = policies["plars_static"].get("schedule")
    if not isinstance(schedule, (str, list, dict)) or not schedule or (
        isinstance(schedule, str) and not schedule.strip()
    ):
        raise ValueError(f"{name}/plars_static needs a fixed schedule or schedule reference")


def plan_runs(specification):
    """Return a plan from the JSON input shape described above."""
    if not isinstance(specification, dict):
        raise ValueError("The input must be a JSON object")
    seed = specification.get("seed")
    repeats = specification.get("repeats")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(repeats) is not int or repeats < MIN_REPEATS:
        raise ValueError(f"repeats must be an integer of at least {MIN_REPEATS}")

    scenarios = specification.get("scenarios")
    # Include the ordered input arrays in the namespace and ignore object key
    # order so equivalent input objects produce the same identifiers.
    identity = json.dumps([seed, repeats, scenarios], sort_keys=True, separators=(",", ":"), allow_nan=False)
    plan_id = hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    rng = random.Random(seed)
    runs = []
    for scenario_id, scenario in named_entries(scenarios, "scenarios"):
        configurations = named_entries(scenario.get("configurations"), f"{scenario_id}/configurations")
        for configuration_id, configuration in configurations:
            validate_configuration(configuration, f"{scenario_id}/{configuration_id}")
            for repeat in range(repeats + 1):
                baselines = list(BASELINES)
                rng.shuffle(baselines)
                for baseline in baselines:
                    runs.append({
                        "run_id": f"r22-{plan_id}-{len(runs) + 1:06d}",
                        "scenario": scenario_id,
                        "configuration": configuration_id,
                        "baseline": baseline,
                        "repeat": repeat,
                        "warmup": repeat == 0,
                        "seed": seed,
                    })
    return {
        "schema_version": 1,
        "plan_id": plan_id,
        "seed": seed,
        "repeats": repeats,
        "scenarios": scenarios,
        "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate a seeded Ratatoss R2.2 run plan and write it as JSON to stdout.",
        epilog="\n".join(__doc__.splitlines()[2:]),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("specification", type=Path, help="Path to the JSON planning input")
    args = parser.parse_args()
    try:
        with args.specification.open(encoding="utf-8-sig") as source:
            plan = plan_runs(json.load(source))
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
