"""Tests for per-route EWMA telemetry. All samples are synthetic examples."""

import unittest

from ratatoss.plars_selection import Route
from ratatoss.plars_telemetry import (
    RouteEstimate,
    RouteKey,
    RouteTelemetry,
    TelemetryConfig,
    TransferSample,
    measure,
)

MIB = 1024 * 1024
INITIAL = RouteEstimate(setup_ms=5_000, goodput_bps=2_000_000)


def sample(source="A", target="B", kind="direct", *, verified=True, size=8 * MIB,
           start=1_000, first=1_400, last=2_400):
    return TransferSample(source, target, kind, verified, size, start, first, last)


def telemetry(alpha=0.25):
    return RouteTelemetry(TelemetryConfig(alpha, INITIAL))


class InitialEstimateTests(unittest.TestCase):
    def test_route_without_samples_uses_the_configured_initial_estimate(self):
        state = telemetry()
        self.assertEqual(state.estimate("A", "B", "direct"), INITIAL)
        self.assertEqual(state.sample_counts("A", "B", "direct"), (0, 0))

    def test_per_route_initial_estimate_overrides_the_default(self):
        probe = RouteEstimate(300, 90_000_000)
        state = RouteTelemetry(TelemetryConfig(0.25, INITIAL, {RouteKey("B", "C", "direct"): probe}))
        self.assertEqual(state.estimate("B", "C", "direct"), probe)
        self.assertEqual(state.estimate("C", "B", "direct"), INITIAL)


class EwmaTests(unittest.TestCase):
    def test_measure_uses_setup_and_first_to_last_byte_goodput(self):
        measured = measure(sample())
        self.assertEqual(measured.setup_ms, 400)
        self.assertEqual(measured.goodput_bps, 8 * MIB * 8 * 1000 / 1_000)

    def test_update_follows_the_ewma_formula(self):
        state = telemetry(alpha=0.25).observe(sample())
        goodput = 8 * MIB * 8
        self.assertEqual(state.estimate("A", "B", "direct"),
                         RouteEstimate(0.25 * 400 + 0.75 * 5_000, 0.25 * goodput + 0.75 * 2_000_000))
        self.assertEqual(state.sample_counts("A", "B", "direct"), (1, 1))

    def test_alpha_one_tracks_the_latest_sample(self):
        state = telemetry(alpha=1).observe(sample()).observe(sample(first=1_100, last=3_100))
        self.assertEqual(state.estimate("A", "B", "direct"), RouteEstimate(100, 8 * MIB * 8 / 2))

    def test_replaying_the_same_samples_reproduces_the_estimates(self):
        samples = [sample(first=1_000 + step * 37, last=2_000 + step * 113) for step in range(25)]

        def replay():
            state = telemetry(alpha=0.25)
            for item in samples:
                state = state.observe(item)
            return state.estimate("A", "B", "direct")

        self.assertEqual(replay(), replay())

    def test_observe_does_not_change_the_previous_state(self):
        before = telemetry()
        after = before.observe(sample())
        self.assertEqual(before.estimate("A", "B", "direct"), INITIAL)
        self.assertNotEqual(after.estimate("A", "B", "direct"), INITIAL)


class RouteSeparationTests(unittest.TestCase):
    def test_reverse_direction_is_a_separate_route(self):
        state = telemetry().observe(sample("A", "B"))
        self.assertNotEqual(state.estimate("A", "B", "direct"), INITIAL)
        self.assertEqual(state.estimate("B", "A", "direct"), INITIAL)

        reverse = telemetry().observe(sample("B", "A"))
        self.assertNotEqual(reverse.estimate("B", "A", "direct"), INITIAL)
        self.assertEqual(reverse.estimate("A", "B", "direct"), INITIAL)

    def test_direct_relay_and_unknown_paths_are_separate(self):
        state = telemetry().observe(sample(kind="relay", first=2_000, last=6_000))
        relay = state.estimate("A", "B", "relay")
        self.assertNotEqual(relay, INITIAL)
        self.assertEqual(state.estimate("A", "B", "direct"), INITIAL)
        self.assertEqual(state.estimate("A", "B", "unknown"), INITIAL)

        state = state.observe(sample(kind="unknown"))
        self.assertEqual(state.estimate("A", "B", "relay"), relay)
        self.assertEqual(state.estimate("A", "B", "direct"), INITIAL)


class UntrustedSampleTests(unittest.TestCase):
    def test_unverified_payload_is_ignored(self):
        before = telemetry()
        self.assertIs(before.observe(sample(verified=False)), before)
        self.assertEqual(measure(sample(verified=False)).goodput_bps, None)

    def test_missing_markers_never_become_zero_goodput(self):
        cases = {
            "no first byte": dict(first=None),
            "no last byte": dict(last=None),
            "no payload size": dict(size=None),
            "empty payload": dict(size=0),
            "last before first": dict(last=1_300),
            "same first and last": dict(last=1_400),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.assertIsNone(measure(sample(**change)).goodput_bps)
                state = telemetry().observe(sample(**change))
                self.assertEqual(state.estimate("A", "B", "direct").goodput_bps, INITIAL.goodput_bps)
                self.assertEqual(state.sample_counts("A", "B", "direct")[1], 0)

    def test_setup_and_goodput_update_independently(self):
        no_start = telemetry().observe(sample(start=None))
        self.assertEqual(no_start.estimate("A", "B", "direct").setup_ms, INITIAL.setup_ms)
        self.assertEqual(no_start.sample_counts("A", "B", "direct"), (0, 1))

        first_before_start = telemetry().observe(sample(start=1_500))
        self.assertEqual(first_before_start.sample_counts("A", "B", "direct"), (0, 1))

        no_last = telemetry().observe(sample(last=None))
        self.assertEqual(no_last.estimate("A", "B", "direct").goodput_bps, INITIAL.goodput_bps)
        self.assertEqual(no_last.sample_counts("A", "B", "direct"), (1, 0))

    def test_rejects_malformed_samples(self):
        bad = {
            "float marker": TransferSample("A", "B", "direct", True, 1, 0.0, 1, 2),
            "negative bytes": TransferSample("A", "B", "direct", True, -1, 0, 1, 2),
            "boolean bytes": TransferSample("A", "B", "direct", True, True, 0, 1, 2),
            "string verified": TransferSample("A", "B", "direct", "yes", 1, 0, 1, 2),
            "unknown path kind": TransferSample("A", "B", "lan", True, 1, 0, 1, 2),
            "same device": TransferSample("A", "A", "direct", True, 1, 0, 1, 2),
            "empty source": TransferSample("", "B", "direct", True, 1, 0, 1, 2),
        }
        for name, item in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                telemetry().observe(item)


class ConfigTests(unittest.TestCase):
    def test_rejects_alpha_outside_the_valid_range(self):
        for alpha in (0, -0.1, 1.01, float("nan"), float("inf"), True, "0.25", None):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError):
                TelemetryConfig(alpha, INITIAL)
        for alpha in (0.25, 1, 1e-9):
            with self.subTest(alpha=alpha):
                TelemetryConfig(alpha, INITIAL)

    def test_rejects_invalid_initial_estimates(self):
        for estimate in (RouteEstimate(-1, 1), RouteEstimate(0, 0), RouteEstimate(0, -5),
                         RouteEstimate(float("nan"), 1), RouteEstimate(0, float("inf")),
                         RouteEstimate(True, 1), (0, 1)):
            with self.subTest(estimate=estimate), self.assertRaises(ValueError):
                TelemetryConfig(0.25, estimate)
        with self.assertRaises(ValueError):
            TelemetryConfig(0.25, INITIAL, {RouteKey("A", "B", "wifi"): INITIAL})


class RouteHandoffTests(unittest.TestCase):
    def test_route_rounds_toward_caution_for_plars_selection(self):
        config = TelemetryConfig(1, RouteEstimate(10.2, 1_000_000.9))
        route = RouteTelemetry(config).route("A", "B", "relay", wan=True, resources=("wan",))
        self.assertEqual(route, Route("A", "B", 1_000_000, 11, wan=True, resources=("wan",)))

    def test_route_keeps_goodput_at_least_one_bit_per_second(self):
        config = TelemetryConfig(1, RouteEstimate(0, 0.4))
        self.assertEqual(RouteTelemetry(config).route("A", "B", "direct").goodput_bps, 1)


if __name__ == "__main__":
    unittest.main()
