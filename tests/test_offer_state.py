import unittest

from ratatoss.offer_state import (
    OfferDecisionResult,
    OfferTransition,
    decide_offer,
    expire_offer,
)


DEADLINE_MS = 1_700_000_001_000
MANIFEST_SHA256 = "a" * 64  # Synthetic digest for decision tests.


class OfferDecisionTests(unittest.TestCase):
    def decide(self, **overrides):
        fields = {
            "state": "PENDING",
            "expires_at_ms": DEADLINE_MS,
            "now_ms": DEADLINE_MS - 1,
            "expected_manifest_sha256": MANIFEST_SHA256,
            "decision": "ACCEPT",
            "manifest_sha256": MANIFEST_SHA256,
            "allow_forward": False,
        }
        return decide_offer(**(fields | overrides))

    def test_accept_preserves_forward_choice_and_records_time(self):
        for allow_forward in (False, True):
            with self.subTest(allow_forward=allow_forward):
                result = self.decide(allow_forward=allow_forward)
                self.assertEqual(
                    result,
                    OfferDecisionResult(
                        OfferTransition("ACCEPTED", DEADLINE_MS - 1, allow_forward)
                    ),
                )
                self.assertIsNotNone(result.transition)
                self.assertIs(result.transition.allow_forward, allow_forward)

    def test_accept_wrong_digest_is_a_conflict(self):
        self.assertEqual(
            self.decide(manifest_sha256="b" * 64),
            OfferDecisionResult(error_code="STATE_CONFLICT"),
        )

    def test_malformed_decision_fields_are_invalid(self):
        for overrides in (
            {"decision": "UNKNOWN"},
            {"manifest_sha256": None},
            {"manifest_sha256": "short"},
            {"manifest_sha256": MANIFEST_SHA256.upper()},
            {"allow_forward": None},
            {"allow_forward": 0},
            {"decision": "DECLINE", "manifest_sha256": None, "allow_forward": False},
            {"decision": "DECLINE", "allow_forward": None},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(
                    self.decide(**overrides),
                    OfferDecisionResult(error_code="INVALID_REQUEST"),
                )

    def test_decline_before_deadline(self):
        self.assertEqual(
            self.decide(decision="DECLINE", manifest_sha256=None, allow_forward=None),
            OfferDecisionResult(OfferTransition("DECLINED")),
        )

    def test_decision_at_or_after_deadline_expires_pending_offer(self):
        for now_ms in (DEADLINE_MS, DEADLINE_MS + 1):
            for fields in (
                {},
                {"decision": "DECLINE", "manifest_sha256": None, "allow_forward": None},
            ):
                with self.subTest(now_ms=now_ms, decision=fields.get("decision", "ACCEPT")):
                    self.assertEqual(
                        self.decide(now_ms=now_ms, **fields),
                        OfferDecisionResult(OfferTransition("EXPIRED"), "EXPIRED"),
                    )

    def test_decisions_conflict_with_other_states_even_after_deadline(self):
        for state in ("ACCEPTED", "DECLINED", "REVOKED", "WITHDRAWN", "VERIFIED", "CANCELED"):
            with self.subTest(state=state):
                expected = OfferDecisionResult(error_code="STATE_CONFLICT")
                self.assertEqual(self.decide(state=state, now_ms=DEADLINE_MS), expected)
                self.assertEqual(
                    self.decide(
                        state=state,
                        decision="DECLINE",
                        manifest_sha256=None,
                        allow_forward=None,
                    ),
                    expected,
                )

    def test_already_expired_offer_returns_error_without_transition(self):
        self.assertEqual(
            self.decide(state="EXPIRED", now_ms=DEADLINE_MS + 1),
            OfferDecisionResult(error_code="EXPIRED"),
        )


class OfferExpiryTests(unittest.TestCase):
    def test_pending_offer_expires_at_inclusive_deadline(self):
        expired = OfferTransition("EXPIRED")
        for offset, expected in ((-1, None), (0, expired), (1, expired)):
            with self.subTest(offset=offset):
                self.assertEqual(
                    expire_offer(
                        state="PENDING",
                        expires_at_ms=DEADLINE_MS,
                        now_ms=DEADLINE_MS + offset,
                    ),
                    expected,
                )

    def test_expiry_does_not_change_other_states(self):
        for state in (
            "ACCEPTED", "DECLINED", "EXPIRED", "REVOKED", "WITHDRAWN", "VERIFIED", "CANCELED"
        ):
            with self.subTest(state=state):
                self.assertIsNone(
                    expire_offer(state=state, expires_at_ms=DEADLINE_MS, now_ms=DEADLINE_MS)
                )
