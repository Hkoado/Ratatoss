"""Cooldown tests using synthetic assignments and explicit clock values."""

import unittest
from dataclasses import FrozenInstanceError, asdict, replace

from ratatoss.plars_cooldown import (
    COMPLETED,
    COOLDOWN_BELOW_ABSOLUTE,
    COOLDOWN_BELOW_RELATIVE,
    COOLDOWN_EXPIRED,
    COOLDOWN_NO_GAIN,
    FAILED,
    GAIN_ABOVE_THRESHOLDS,
    KEEP,
    KEEP_RUNNING,
    LEASE_EXPIRED,
    NO_CANDIDATE,
    NO_GAIN,
    NOT_STARTED,
    RELEASE,
    ROUTE_LOST,
    RUNNING,
    SAME_PLAN,
    SESSION_COMPLETED,
    SESSION_FAILED,
    SWITCH,
    CooldownConfig,
    CooldownDecision,
    CurrentPlan,
    PlanOption,
    decide,
)

CONFIG = CooldownConfig(10_000, 2_000, 100)
ADOPTED = 5_000
NOW = ADOPTED + 1_000
CURRENT = CurrentPlan(PlanOption("A", "B", 1, 40_000), ADOPTED, NOT_STARTED)
CANDIDATE = PlanOption("C", "B", 1, 10_000)


class CooldownTests(unittest.TestCase):
    def test_running_plan_is_kept_even_after_cooldown_and_route_loss(self):
        current = replace(CURRENT, session=RUNNING,
                          option=replace(CURRENT.option, route_available=False))
        for candidate in (CANDIDATE, None):
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    decide(current, candidate, now_ms=ADOPTED + 11_000, config=CONFIG),
                    CooldownDecision(KEEP, KEEP_RUNNING, None, None, 0),
                )

    def test_ended_session_or_route_loss_replaces_or_releases_the_plan(self):
        lost_route = replace(CURRENT.option, route_available=False)
        cases = (
            (COMPLETED, SESSION_COMPLETED),
            (FAILED, SESSION_FAILED),
            (LEASE_EXPIRED, LEASE_EXPIRED),
            (NOT_STARTED, ROUTE_LOST),
        )
        for session, reason in cases:
            current = replace(CURRENT, session=session, option=lost_route)
            for candidate, action in ((replace(lost_route, route_available=True), SWITCH),
                                      (None, RELEASE)):
                with self.subTest(session=session, action=action):
                    self.assertEqual(
                        decide(current, candidate, now_ms=NOW, config=CONFIG),
                        CooldownDecision(action, reason, None, None, 9_000),
                    )

    def test_unsuitable_or_unchanged_candidate_does_not_compute_gain(self):
        for candidate, reason in ((None, NO_CANDIDATE),
                                  (replace(CURRENT.option, eta_ms=1), SAME_PLAN)):
            with self.subTest(reason=reason):
                self.assertEqual(
                    decide(CURRENT, candidate, now_ms=NOW, config=CONFIG),
                    CooldownDecision(KEEP, reason, None, None, 9_000),
                )

    def test_gain_thresholds_during_cooldown(self):
        cases = (
            (60_000, 57_000, KEEP, COOLDOWN_BELOW_RELATIVE, 3_000, 50),
            (10_000, 8_500, KEEP, COOLDOWN_BELOW_ABSOLUTE, 1_500, 150),
            (30_000, 20_000, SWITCH, GAIN_ABOVE_THRESHOLDS, 10_000, 333),
            (20_000, 18_000, SWITCH, GAIN_ABOVE_THRESHOLDS, 2_000, 100),
            (20_001, 18_001, KEEP, COOLDOWN_BELOW_RELATIVE, 2_000, 99),
            (30_000, 29_000, KEEP, COOLDOWN_NO_GAIN, 1_000, 33),
            (30_000, 30_000, KEEP, COOLDOWN_NO_GAIN, 0, 0),
            (30_000, 30_001, KEEP, COOLDOWN_NO_GAIN, -1, -1),
            (0, 0, KEEP, COOLDOWN_NO_GAIN, 0, None),
        )
        for current_eta, candidate_eta, action, reason, gain, permille in cases:
            with self.subTest(current_eta=current_eta, candidate_eta=candidate_eta):
                current = replace(CURRENT, option=replace(CURRENT.option, eta_ms=current_eta))
                candidate = replace(CANDIDATE, eta_ms=candidate_eta)
                self.assertEqual(
                    decide(current, candidate, now_ms=NOW, config=CONFIG),
                    CooldownDecision(action, reason, gain, permille, 9_000),
                )

    def test_cooldown_boundary_and_zero_duration(self):
        cases = (
            (CONFIG, 9_999, 39_999, KEEP, COOLDOWN_NO_GAIN, 1, 0, 1),
            (CONFIG, 10_000, 39_999, SWITCH, COOLDOWN_EXPIRED, 1, 0, 0),
            (CONFIG, 10_001, 40_000, KEEP, NO_GAIN, 0, 0, 0),
            (CONFIG, 10_001, 40_001, KEEP, NO_GAIN, -1, -1, 0),
            (CooldownConfig(0, 2_000, 100), 0, 39_999, SWITCH, COOLDOWN_EXPIRED, 1, 0, 0),
        )
        for config, elapsed, eta, action, reason, gain, permille, remaining in cases:
            with self.subTest(elapsed=elapsed, eta=eta):
                self.assertEqual(
                    decide(CURRENT, replace(CANDIDATE, eta_ms=eta),
                           now_ms=ADOPTED + elapsed, config=config),
                    CooldownDecision(action, reason, gain, permille, remaining),
                )

    def test_zero_gain_is_kept_even_when_both_thresholds_are_zero(self):
        result = decide(CURRENT, replace(CANDIDATE, eta_ms=CURRENT.option.eta_ms),
                        now_ms=NOW, config=CooldownConfig(10_000, 0, 0))
        self.assertEqual(result, CooldownDecision(KEEP, COOLDOWN_NO_GAIN, 0, 0, 9_000))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            decide(replace(CURRENT, session=RUNNING), CANDIDATE,
                   now_ms=ADOPTED - 1, config=CONFIG)
        for session in ("unknown", None, []):
            with self.subTest(session=session), self.assertRaises(ValueError):
                replace(CURRENT, session=session)

        invalid_configs = (
            (-1, 0, 0), (0, -1, 0), (0, 0, -1), (0, 0, 1001),
            (True, 0, 0), (0, 2.0, 0), (0, 0, "100"),
        )
        for values in invalid_configs:
            with self.subTest(values=values), self.assertRaises(ValueError):
                CooldownConfig(*values)

    def test_results_are_deterministic_and_data_objects_are_frozen(self):
        result = decide(CURRENT, CANDIDATE, now_ms=NOW, config=CONFIG)
        replay = decide(CURRENT, CANDIDATE, now_ms=NOW, config=CONFIG)
        self.assertEqual(result, replay)
        self.assertEqual(asdict(replay), asdict(result))
        self.assertEqual(asdict(result), {
            "action": "SWITCH",
            "reason": "GAIN_ABOVE_THRESHOLDS",
            "gain_ms": 30_000,
            "gain_permille": 750,
            "cooldown_left_ms": 9_000,
        })
        for obj, field in ((CONFIG, "cooldown_ms"), (CURRENT, "session"),
                           (CANDIDATE, "eta_ms"), (result, "action")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(obj, field, None)
