import copy
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


BASELINES = (
    "direct", "gateway_whole_file", "fixed_split", "gateway_pipeline",
    "plars", "plars_static",
)


def synthetic_configuration(configuration_id, batch_mib):
    return {
        "id": configuration_id,
        "conditions": {
            "topology": "synthetic-a-b-c-d",
            "allowed_routes": ["A-B", "A-C", "A-D", "B-C", "B-D"],
            "bottlenecks": {"wan": ["A-B", "A-C"]},
            "batch_mib": batch_mib,
            "rx_slots": {"B": 2, "C": 1, "D": 1},
            "tx_slots": {"A": 2, "B": 1},
            "budget": {"max_active": 3},
        },
        "policies": {
            baseline: {"schedule": "synthetic-fixed-routes"} if baseline == "plars_static" else {}
            for baseline in BASELINES
        },
    }


class TestPlanR22Runs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots = [Path(__file__).resolve().parent.parent]
        if "GITHUB_WORKSPACE" in os.environ:
            roots.append(Path(os.environ["GITHUB_WORKSPACE"]))
        for root in roots:
            script = root / "scripts" / "plan_r22_runs.py"
            if script.is_file():
                cls.script = script
                cls.plan_runs = staticmethod(runpy.run_path(str(script))["plan_runs"])
                return
        raise unittest.SkipTest("scripts/plan_r22_runs.py not found outside repository")

    def setUp(self):
        self.specification = {
            "seed": 71,
            "repeats": 5,
            "scenarios": [
                {"id": "shared-wan", "configurations": [
                    synthetic_configuration("slot-budget", 64),
                    synthetic_configuration("small-batches", 32),
                ]},
                {"id": "c-offline", "configurations": [
                    synthetic_configuration("slot-budget", 64),
                ]},
            ],
        }

    def test_coverage_and_run_counts(self):
        plan = self.plan_runs(self.specification)
        self.assertEqual(plan["schema_version"], 1)
        self.assertEqual(plan["seed"], 71)
        self.assertEqual(plan["repeats"], 5)
        self.assertEqual(plan["scenarios"], self.specification["scenarios"])
        runs = plan["runs"]
        self.assertEqual(len(runs), 108)
        self.assertEqual(len({run["run_id"] for run in runs}), len(runs))
        expected = Counter({
            (scenario, configuration, baseline): 5
            for scenario, configuration in (
                ("shared-wan", "slot-budget"),
                ("shared-wan", "small-batches"),
                ("c-offline", "slot-budget"),
            )
            for baseline in BASELINES
        })
        counts = Counter(
            (run["scenario"], run["configuration"], run["baseline"])
            for run in runs if not run["warmup"]
        )
        self.assertEqual(counts, expected)
        self.assertTrue(all(run["seed"] == 71 for run in runs))

    def test_warmups_are_distinct_and_precede_measurements_in_each_configuration(self):
        runs = self.plan_runs(self.specification)["runs"]
        for offset in range(0, len(runs), 36):
            block = runs[offset:offset + 36]
            self.assertEqual(len({(run["scenario"], run["configuration"]) for run in block}), 1)
            for repeat in range(6):
                group = block[repeat * 6:(repeat + 1) * 6]
                self.assertCountEqual([run["baseline"] for run in group], BASELINES)
                self.assertTrue(all(run["repeat"] == repeat for run in group))
                self.assertTrue(all(run["warmup"] == (repeat == 0) for run in group))

    def test_seeded_order_is_reproducible_and_changes_with_seed(self):
        original = self.plan_runs(self.specification)
        reordered = json.loads(json.dumps(self.specification, sort_keys=True))
        self.assertEqual(self.plan_runs(reordered), original)
        self.assertEqual(self.plan_runs(copy.deepcopy(self.specification)), original)

        self.specification["seed"] = 99
        changed = self.plan_runs(self.specification)
        self.assertNotEqual(
            [run["baseline"] for run in original["runs"]],
            [run["baseline"] for run in changed["runs"]],
        )
        self.assertTrue(
            {run["run_id"] for run in original["runs"]}.isdisjoint(
                run["run_id"] for run in changed["runs"]
            )
        )

    def test_matched_static_policy_requires_a_schedule_and_shared_conditions(self):
        config = self.specification["scenarios"][0]["configurations"][0]
        static = config["policies"]["plars_static"]
        static["rx_slots"] = {"B": 9}
        with self.assertRaisesRegex(ValueError, "overrides shared conditions: rx_slots"):
            self.plan_runs(self.specification)
        del static["rx_slots"]
        del static["schedule"]
        with self.assertRaisesRegex(ValueError, "needs a fixed schedule"):
            self.plan_runs(self.specification)
        static["schedule"] = "synthetic-fixed-routes"
        del config["conditions"]["topology"]
        with self.assertRaisesRegex(ValueError, "missing shared conditions: topology"):
            self.plan_runs(self.specification)

    def test_rejects_underfilled_or_ambiguous_plans(self):
        for key, value, message in (
            ("seed", True, "seed must be an integer"),
            ("repeats", 4, "at least 5"),
            ("scenarios", [], "nonempty array"),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                self.plan_runs({**self.specification, key: value})
        scenarios = self.specification["scenarios"]
        with self.assertRaisesRegex(ValueError, "Duplicate id in scenarios"):
            self.plan_runs({**self.specification, "scenarios": [scenarios[0], scenarios[0]]})
        del scenarios[0]["configurations"][0]["policies"]["direct"]
        with self.assertRaisesRegex(ValueError, "must define exactly these policies"):
            self.plan_runs(self.specification)

    def test_cli_emits_runner_json_from_caller_input(self):
        self.specification["repeats"] = 6
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            source = json.dumps(self.specification)
            path.write_text(source, encoding="utf-8-sig")
            result = subprocess.run([sys.executable, str(self.script), str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), self.plan_runs(self.specification))
            self.assertEqual(path.read_text(encoding="utf-8-sig"), source)

            path.write_text("{", encoding="utf-8")
            result = subprocess.run([sys.executable, str(self.script), str(path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn("error:", result.stderr)

    def assert_cli_rejects_condition(self, field, value, message):
        specification = copy.deepcopy(self.specification)
        conditions = specification["scenarios"][0]["configurations"][0]["conditions"]
        conditions[field] = value
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(specification), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(self.script), str(path)], capture_output=True, text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(message, result.stderr)

    def test_cli_rejects_nonpositive_batch_sizes(self):
        for value in (0, -32):
            with self.subTest(value=value):
                self.assert_cli_rejects_condition("batch_mib", value, "/batch_mib must be a positive number")

    def test_cli_rejects_negative_slot_limits(self):
        for field, value, expected in (
            ("rx_slots", {"B": -1}, "/rx_slots.B must be a nonnegative integer"),
            ("tx_slots", {"A": -1}, "/tx_slots.A must be a nonnegative integer"),
            ("tx_slots", -1, "/tx_slots must be a nonnegative integer"),
        ):
            with self.subTest(field=field, value=value):
                self.assert_cli_rejects_condition(field, value, expected)

    def test_zero_slot_limits_are_allowed(self):
        conditions = self.specification["scenarios"][0]["configurations"][0]["conditions"]
        conditions["rx_slots"] = {"B": 0, "C": 1, "D": 1}
        conditions["tx_slots"] = 0
        self.assertEqual(len(self.plan_runs(self.specification)["runs"]), 108)
