"""Evaluate offer decisions and expiry for the controller."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OfferTransition:
    state: Literal["ACCEPTED", "DECLINED", "EXPIRED"]
    accepted_at_ms: int | None = None
    allow_forward: bool = False


@dataclass(frozen=True)
class OfferDecisionResult:
    transition: OfferTransition | None = None
    error_code: Literal["INVALID_REQUEST", "STATE_CONFLICT", "EXPIRED"] | None = None


def expire_offer(
    *, state: str, expires_at_ms: int, now_ms: int
) -> OfferTransition | None:
    """Return the change to persist when a pending offer reaches its deadline."""
    if state == "PENDING" and now_ms >= expires_at_ms:
        return OfferTransition("EXPIRED")
    return None


def decide_offer(
    *,
    state: str,
    expires_at_ms: int,
    now_ms: int,
    expected_manifest_sha256: str,
    decision: str,
    manifest_sha256: str | None = None,
    allow_forward: bool | None = None,
) -> OfferDecisionResult:
    """Evaluate consent using the controller row and the parsed decision fields.

    The caller checks request shape, identity and idempotency. Apply any
    returned transition in the transaction, including expiry on a rejected
    decision. An already expired offer returns the error without a new change.
    """
    if decision == "ACCEPT":
        if (
            not isinstance(manifest_sha256, str)
            or not re.fullmatch("[0-9a-f]{64}", manifest_sha256)
            or not isinstance(allow_forward, bool)
        ):
            return OfferDecisionResult(error_code="INVALID_REQUEST")
    elif decision != "DECLINE" or manifest_sha256 is not None or allow_forward is not None:
        return OfferDecisionResult(error_code="INVALID_REQUEST")

    expiry = expire_offer(state=state, expires_at_ms=expires_at_ms, now_ms=now_ms)
    if state == "EXPIRED" or expiry is not None:
        return OfferDecisionResult(transition=expiry, error_code="EXPIRED")

    if state != "PENDING":
        return OfferDecisionResult(error_code="STATE_CONFLICT")

    if decision == "DECLINE":
        return OfferDecisionResult(transition=OfferTransition("DECLINED"))

    if manifest_sha256 != expected_manifest_sha256:
        return OfferDecisionResult(error_code="STATE_CONFLICT")

    return OfferDecisionResult(
        transition=OfferTransition(
            "ACCEPTED", accepted_at_ms=now_ms, allow_forward=allow_forward is True
        )
    )
