import subprocess
import sys
import unittest

from ratatoss.lease_profile import evaluate_lease_budget



class LeaseBudgetTests(unittest.TestCase):
    def test_grant_and_spawn_use_only_remaining_setup_and_time(self):
        common = dict(batch_bytes=1, min_goodput_bps=8000, verify_commit_ms=1, margin_ms=1)
        grant = evaluate_lease_budget(
            **common, remaining_lease_ms=6, remaining_adapter_ms=8, remaining_setup_ms=3
        )
        spawn = evaluate_lease_budget(
            **common, remaining_lease_ms=3, remaining_adapter_ms=5, remaining_setup_ms=0
        )
        self.assertEqual((grant.required_ms, grant.available_ms, grant.fits), (6, 6, True))
        self.assertEqual((spawn.required_ms, spawn.available_ms, spawn.fits), (3, 3, True))

    def test_exhausted_adapter_deadline_is_infeasible(self):
        budget = evaluate_lease_budget(
            batch_bytes=1, min_goodput_bps=8000, remaining_lease_ms=100,
            remaining_adapter_ms=0, remaining_setup_ms=0, verify_commit_ms=0, margin_ms=0,
        )
        self.assertEqual(budget.available_ms, 0)
        self.assertFalse(budget.fits)

    def test_api_rejects_boolean_and_float(self):
        valid = dict(
            batch_bytes=1, min_goodput_bps=8000, remaining_lease_ms=10,
            remaining_adapter_ms=10, remaining_setup_ms=0, verify_commit_ms=0, margin_ms=0,
        )
        for field in valid:
            for value in (True, 1.0):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        evaluate_lease_budget(**(valid | {field: value}))



class CrocLeasePreflightTests(unittest.TestCase):
    def preflight(self, **overrides):
        args = {
            "batch-bytes": 67108864,
            "min-goodput-bps": 2000000,
            "remaining-lease-ms": 180000,
            "adapter-timeout-ms": 300000,
            "setup-ms": 5000,
            "verify-commit-ms": 2000,
            "margin-ms": 3000,
        }
        args.update(overrides)
        return subprocess.run(
            [sys.executable, "-m", "ratatoss.lease_profile", *(f"--{key}={value}" for key, value in args.items())],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_64_mib_at_2_mbps_cannot_fit_180_seconds(self):
        result = self.preflight()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stdout.strip(),
            "infeasible transfer_ms=268436 required_ms=278436 available_ms=180000",
        )

    def test_exact_boundary_and_one_millisecond_short(self):
        for remaining_ms, exit_code in [(278436, 0), (278435, 1)]:
            with self.subTest(remaining_ms=remaining_ms):
                result = self.preflight(**{"remaining-lease-ms": remaining_ms})
                self.assertEqual(result.returncode, exit_code)
                self.assertIn("required_ms=278436", result.stdout)

    def test_adapter_timeout_limits_available_time(self):
        result = self.preflight(**{"remaining-lease-ms": 300000, "adapter-timeout-ms": 270000})
        self.assertEqual(result.returncode, 1)
        self.assertIn("available_ms=270000", result.stdout)

    def test_smaller_batch_fits_the_original_budget(self):
        result = self.preflight(**{"batch-bytes": 33554432})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout.strip(),
            "feasible transfer_ms=134218 required_ms=144218 available_ms=180000",
        )

    def test_expired_lease_has_no_available_time(self):
        result = self.preflight(**{"remaining-lease-ms": 0})
        self.assertEqual(result.returncode, 1)
        self.assertIn("available_ms=0", result.stdout)

    def test_invalid_inputs(self):
        for flag, value in [
            ("batch-bytes", 0),
            ("min-goodput-bps", 0),
            ("remaining-lease-ms", -1),
            ("adapter-timeout-ms", -1),
            ("setup-ms", -1),
            ("verify-commit-ms", "abc"),
            ("margin-ms", "0.5"),
        ]:
            with self.subTest(flag=flag, value=value):
                result = self.preflight(**{flag: value})
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"--{flag}", result.stderr)
