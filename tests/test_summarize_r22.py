import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestSummarizeR22(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots = [Path(__file__).resolve().parent.parent]
        if "GITHUB_WORKSPACE" in os.environ:
            roots.append(Path(os.environ["GITHUB_WORKSPACE"]))
        for root in roots:
            script = root / "scripts" / "summarize_r22.py"
            if script.is_file():
                cls.script = script
                cls.headers = {}
                for name in ("runs", "transfers"):
                    with (root / "bench" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as source:
                        cls.headers[name] = next(csv.reader(source))
                return
        raise unittest.SkipTest("scripts/summarize_r22.py not found outside repository")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.runs = root / "runs.csv"
        self.transfers = root / "transfers.csv"
        self.configurations = root / "configurations.json"
        self.write_csv(self.transfers, self.headers["transfers"], [])

    def write_csv(self, path, fields, rows):
        with path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def run_row(self, run_id, baseline="plars", status="pass", makespan="20", **overrides):
        return {
            "run_id": run_id,
            "gate": "gate2",
            "scenario": "shared-wan",
            "baseline": baseline,
            "repeat": "1",
            "seed": "75",
            "status": status,
            "makespan_ms": makespan,
            "source_payload_bytes": "100",
            "commit": "synthetic-revision",
            "os": "synthetic-os",
            "croc_version": "synthetic-version",
            "croc_sha256": "a" * 64,
            "relay_config": "synthetic-relay",
            "network_profile": "synthetic-network",
            "fixture_sha256": "b" * 64,
            "file_bytes": "100",
            "batch_mib": "64",
            "rx_slots": "2",
            "tx_slots": "1",
            "evidence_ref": f"evidence/{run_id}.json",
            "notes": "Synthetic fixture. Unused fields were not measured.",
            **overrides,
        }

    def invoke(self, rows, configurations):
        self.write_csv(self.runs, self.headers["runs"], rows)
        self.configurations.write_text(json.dumps(configurations), encoding="utf-8")
        paths = [self.runs, self.transfers, self.configurations]
        before = [path.read_bytes() for path in paths]
        result = subprocess.run(
            [sys.executable, str(self.script), *map(str, paths)], capture_output=True, text=True,
        )
        self.assertEqual([path.read_bytes() for path in paths], before)
        return result

    def summarize(self, rows, configurations):
        result = self.invoke(rows, configurations)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_header_only_csvs_return_an_empty_report(self):
        report = self.summarize([], {})
        self.assertEqual(report["groups"], [])
        self.assertEqual(report["comparisons"], [])

    def test_status_counts_raw_references_and_stats_from_passing_runs(self):
        rows = [
            self.run_row("first", makespan="10.5"),
            self.run_row("second", makespan="20.5"),
            self.run_row("unknown", makespan="", notes="Final receipt missing."),
            self.run_row("failed", "plars", "fail", "999"),
            self.run_row("timed-out", "plars", "timeout", "", notes="Timed out."),
        ]
        report = self.summarize(rows, {"wan": {"run_ids": [row["run_id"] for row in rows]}})
        group, = report["groups"]
        self.assertEqual((group["passed"], group["total"]), (3, 5))
        self.assertEqual(group["status_counts"], {"pass": 3, "fail": 1, "timeout": 1})
        self.assertEqual(group["passing_measurement_stats"]["makespan_ms"], {
            "count": 2, "median": 15.5, "min": 10.5, "max": 20.5,
        })
        self.assertEqual(group["passing_measurement_stats"]["source_payload_bytes"]["count"], 3)
        self.assertEqual(group["passing_measurement_stats"]["recovery_ms"], {
            "count": 0, "median": None, "min": None, "max": None,
        })
        run = group["runs"][2]
        self.assertEqual(run["evidence_ref"], "evidence/unknown.json")
        self.assertEqual(run["source_csv_line"], 4)
        self.assertIsNone(run["measurements"]["makespan_ms"])
        self.assertEqual(run["notes"], "Final receipt missing.")

    def test_groups_by_scenario_configuration_and_baseline(self):
        rows = [
            self.run_row("one"),
            self.run_row("two", baseline="direct"),
            self.run_row("three"),
            self.run_row("four", scenario="c-offline"),
        ]
        report = self.summarize(rows, {
            "small": {"run_ids": ["one", "two", "four"]},
            "large": {"run_ids": ["three"]},
        })
        self.assertCountEqual(
            [(group["scenario"], group["configuration"], group["baseline"]) for group in report["groups"]],
            [
                ("shared-wan", "small", "plars"), ("shared-wan", "small", "direct"),
                ("shared-wan", "large", "plars"), ("c-offline", "small", "plars"),
            ],
        )
        self.assertEqual(report["comparisons"], [])

    def test_flags_plars_loss_only_for_confirmed_matching_control(self):
        rows = [
            self.run_row("plars-a", makespan="100"),
            self.run_row("plars-b", makespan="140"),
            self.run_row("static", baseline="plars_static", makespan="90"),
            self.run_row("direct", baseline="direct", makespan="1"),
            *[self.run_row(f"plars-fail-{index}", status="fail", makespan="999") for index in range(3)],
            *[self.run_row(f"static-timeout-{index}", baseline="plars_static", status="timeout", makespan="")
              for index in range(4)],
        ]
        configurations = {
            "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
        }
        report = self.summarize(rows, configurations)
        comparison, = report["comparisons"]
        self.assertEqual(comparison, {
            "scenario": "shared-wan", "configuration": "wan", "control": "plars_static",
            "status": "compared", "plars_count": 2, "control_count": 1,
            "plars_performed": 5, "control_performed": 5,
            "plars_median_ms": 120, "control_median_ms": 90, "plars_slower": True,
        })

    def test_skips_heterogeneous_and_insufficient_comparisons(self):
        for overrides, expected in (
            ({"rx_slots": "8"}, "unmatched_csv_conditions"),
            ({"file_bytes": ""}, "unmatched_csv_conditions"),
            ({"makespan_ms": ""}, "insufficient_makespan"),
        ):
            with self.subTest(overrides=overrides):
                rows = [
                    *[self.run_row(f"p-{index}") for index in range(5)],
                    *[self.run_row(f"s-{index}", baseline="plars_static", **overrides) for index in range(5)],
                ]
                report = self.summarize(rows, {
                    "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
                })
                comparison, = report["comparisons"]
                self.assertEqual(comparison["status"], expected)
                self.assertNotIn("plars_slower", comparison)

    def test_wan_bytes_are_partitioned_by_scope(self):
        rows = [
            self.run_row("uplink-first", wan_wire_bytes="100", wan_measurement_scope="source uplink"),
            self.run_row("uplink-second", wan_wire_bytes="140", wan_measurement_scope="source uplink"),
            self.run_row("relay", wan_wire_bytes="900", wan_measurement_scope="relay legs"),
            self.run_row("unknown-scope", wan_wire_bytes="350"),
            self.run_row("failed", status="fail", wan_wire_bytes="99", wan_measurement_scope="source uplink"),
            self.run_row("missing-value", wan_measurement_scope="relay legs"),
        ]
        group, = self.summarize(rows, {"wan": {"run_ids": [row["run_id"] for row in rows]}})["groups"]
        self.assertNotIn("wan_wire_bytes", group["passing_measurement_stats"])
        self.assertEqual(group["passing_wan_wire_bytes_by_scope"], {
            "source uplink": {"count": 2, "median": 120, "min": 100, "max": 140},
            "relay legs": {"count": 1, "median": 900, "min": 900, "max": 900},
        })
        self.assertEqual(group["unscoped_passing_wan_wire_bytes_count"], 1)
        self.assertEqual(group["runs"][0]["wan_measurement_scope"], "source uplink")
        self.assertEqual(group["runs"][3]["measurements"]["wan_wire_bytes"], 350)
        self.assertIsNone(group["runs"][5]["measurements"]["wan_wire_bytes"])

    def test_warmups_and_unperformed_runs_cannot_satisfy_minimum(self):
        rows = [
            self.run_row("p", makespan="140"),
            self.run_row("s", baseline="plars_static", makespan="90"),
            self.run_row("warmup", makespan="999", repeat="0", rx_slots="8"),
            *[self.run_row(f"not-run-{index}", status="not_run", makespan="") for index in range(4)],
            *[self.run_row(f"blocked-{index}", baseline="plars_static", status="blocked", makespan="")
              for index in range(4)],
        ]
        report = self.summarize(rows, {
            "wan": {"run_ids": [row["run_id"] for row in rows if row["run_id"] != "warmup"],
                    "matched_controls": ["plars_static"]},
        })
        comparison, = report["comparisons"]
        self.assertEqual(comparison["status"], "insufficient_performed_runs")
        self.assertEqual((comparison["plars_performed"], comparison["control_performed"]), (1, 1))
        self.assertNotIn("plars_slower", comparison)
        plars = report["groups"][0]
        self.assertEqual((plars["passed"], plars["total"]), (1, 5))
        self.assertEqual(plars["passing_measurement_stats"]["makespan_ms"]["median"], 140)
        warmup, = report["excluded_warmups"]
        self.assertEqual(warmup["run_id"], "warmup")
        self.assertEqual(warmup["repeat"], 0)

    def test_failed_run_with_conflicting_conditions_invalidates_comparison(self):
        rows = [
            *[self.run_row(f"p-{index}") for index in range(4)],
            self.run_row("timeout", status="timeout", makespan="", rx_slots="8"),
            *[self.run_row(f"s-{index}", baseline="plars_static") for index in range(5)],
        ]
        report = self.summarize(rows, {
            "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
        })
        comparison, = report["comparisons"]
        self.assertEqual(comparison["status"], "unmatched_csv_conditions")
        self.assertNotIn("plars_slower", comparison)
        self.assertEqual(comparison["condition_conflicts"]["rx_slots"]["8"], ["timeout"])
        plars = report["groups"][0]
        self.assertEqual(plars["condition_conflicts"]["rx_slots"]["8"], ["timeout"])
        self.assertEqual(plars["runs"][-1]["evidence_ref"], "evidence/timeout.json")

    def test_missing_repeat_is_excluded_from_statistics_and_minimum(self):
        rows = [
            *[self.run_row(f"p-{index}", repeat=str(index), makespan=str(value))
              for index, value in enumerate((80, 80, 130, 130), 1)],
            self.run_row("unknown", repeat="", makespan="40"),
            *[self.run_row(f"s-{index}", baseline="plars_static", repeat=str(index), makespan="90")
              for index in range(1, 6)],
        ]
        report = self.summarize(rows, {
            "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
        })
        comparison, = report["comparisons"]
        self.assertEqual(comparison["status"], "insufficient_performed_runs")
        self.assertEqual((comparison["plars_performed"], comparison["control_performed"]), (4, 5))
        self.assertNotIn("plars_slower", comparison)
        plars = report["groups"][0]
        self.assertEqual(plars["passing_measurement_stats"]["makespan_ms"]["median"], 105)
        self.assertEqual(plars["runs"][-1]["measurement_identity"], "missing_identity")
        self.assertEqual(plars["runs"][-1]["evidence_ref"], "evidence/unknown.json")
        self.assertEqual(plars["runs"][-1]["source_csv_line"], 6)

    def test_copies_with_distinct_run_ids_do_not_count_as_distinct_measurements(self):
        rows = [
            *[self.run_row(f"copy-{index}", evidence_ref="evidence/same.json")
              for index in range(5)],
            *[self.run_row(f"s-{index}", baseline="plars_static", repeat=str(index))
              for index in range(1, 6)],
        ]
        report = self.summarize(rows, {
            "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
        })
        comparison, = report["comparisons"]
        self.assertEqual(comparison["status"], "insufficient_performed_runs")
        self.assertEqual((comparison["plars_performed"], comparison["control_performed"]), (0, 5))
        plars = report["groups"][0]
        self.assertEqual(plars["total"], 5)
        self.assertEqual(plars["passing_measurement_stats"]["makespan_ms"]["count"], 0)
        self.assertEqual([run["measurement_identity"] for run in plars["runs"]], ["duplicate_evidence"] * 5)
        self.assertEqual([run["source_csv_line"] for run in plars["runs"]], [2, 3, 4, 5, 6])

    def test_conflicting_passing_runs_have_no_pooled_statistics(self):
        rows = [
            self.run_row("p-one", makespan="140", rx_slots="2",
                         wan_wire_bytes="100", wan_measurement_scope="source uplink"),
            self.run_row("p-two", makespan="40", rx_slots="8",
                         wan_wire_bytes="900", wan_measurement_scope="source uplink"),
            self.run_row("static", baseline="plars_static", makespan="90"),
        ]
        report = self.summarize(rows, {
            "wan": {"run_ids": [row["run_id"] for row in rows], "matched_controls": ["plars_static"]},
        })
        plars = report["groups"][0]
        self.assertEqual(plars["statistics_status"], "conflicting_conditions")
        self.assertEqual(plars["condition_conflicts"]["rx_slots"], {"2": ["p-one"], "8": ["p-two"]})
        self.assertEqual(plars["passing_measurement_stats"], {})
        self.assertEqual(plars["passing_wan_wire_bytes_by_scope"], {})
        self.assertEqual([run["measurements"]["makespan_ms"] for run in plars["runs"]], [140, 40])
        comparison, = report["comparisons"]
        self.assertEqual(comparison["status"], "unmatched_csv_conditions")
        self.assertNotIn("plars_slower", comparison)

    def test_reuses_csv_validator_for_transfer_references_and_missing_notes(self):
        self.write_csv(self.transfers, self.headers["transfers"], [{
            "run_id": "unknown", "status": "pass", "notes": "Synthetic fixture.",
        }])
        configurations = {"wan": {"run_ids": ["known"]}}
        result = self.invoke([self.run_row("known", notes="")], configurations)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("measurement fields are empty without notes justification", result.stderr)
        self.assertIn("run_id not found in runs.csv", result.stderr)

    def test_rejects_invalid_measurements_and_ambiguous_assignments(self):
        result = self.invoke([self.run_row("one", makespan="NaN")], {"wan": {"run_ids": ["one"]}})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("makespan_ms must be a finite nonnegative number", result.stderr)
        for configurations, expected in (
            ({"wan": {"run_ids": ["two"]}}, "Missing run assignments"),
            ({"wan": {"run_ids": ["one"]}, "alt": {"run_ids": ["one"]}}, "assigned more than once"),
        ):
            with self.subTest(configurations=configurations):
                result = self.invoke([self.run_row("one")], configurations)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
