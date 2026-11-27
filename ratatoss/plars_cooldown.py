"""Decide whether to keep an assignment between PLARS scheduling ticks.

The caller supplies monotonic timestamps and both ETAs in integer milliseconds.
Measure the ETAs from the same snapshot, for example using a candidate's
Selection.finish_in_ms. The caller also supplies the cooldown and gain thresholds.

Usage::

    config = CooldownConfig(10_000, 2_000, 100)
    current = CurrentPlan(PlanOption("A", "B", 0, 20_000), 5_000, NOT_STARTED)
    candidate = PlanOption("C", "B", 0, 18_000)
    decision = decide(current, candidate, now_ms=6_000, config=config)
    assert decision.action == SWITCH
    assert decision.reason == GAIN_ABOVE_THRESHOLDS
"""

from dataclasses import dataclass

NOT_STARTED = "NOT_STARTED"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
LEASE_EXPIRED = "LEASE_EXPIRED"

KEEP = "KEEP"
SWITCH = "SWITCH"
RELEASE = "RELEASE"

KEEP_RUNNING = "KEEP_RUNNING"
SESSION_COMPLETED = "SESSION_COMPLETED"
SESSION_FAILED = "SESSION_FAILED"
ROUTE_LOST = "ROUTE_LOST"
NO_CANDIDATE = "NO_CANDIDATE"
SAME_PLAN = "SAME_PLAN"
COOLDOWN_NO_GAIN = "COOLDOWN_NO_GAIN"
GAIN_ABOVE_THRESHOLDS = "GAIN_ABOVE_THRESHOLDS"
COOLDOWN_BELOW_RELATIVE = "COOLDOWN_BELOW_RELATIVE"
COOLDOWN_BELOW_ABSOLUTE = "COOLDOWN_BELOW_ABSOLUTE"
COOLDOWN_EXPIRED = "COOLDOWN_EXPIRED"
NO_GAIN = "NO_GAIN"

_ENDED_SESSION_REASONS = {
    COMPLETED: SESSION_COMPLETED,
    FAILED: SESSION_FAILED,
    LEASE_EXPIRED: LEASE_EXPIRED,
}


@dataclass(frozen=True, slots=True)
class CooldownConfig:
    cooldown_ms: int
    min_gain_ms: int
    min_gain_permille: int

    def __post_init__(self) -> None:
        for name in ("cooldown_ms", "min_gain_ms"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if type(self.min_gain_permille) is not int or not 0 <= self.min_gain_permille <= 1000:
            raise ValueError("min_gain_permille must be an integer from 0 to 1000")


@dataclass(frozen=True, slots=True)
class PlanOption:
    source_id: str
    target_id: str
    batch_id: int
    eta_ms: int
    route_available: bool = True


@dataclass(frozen=True, slots=True)
class CurrentPlan:
    option: PlanOption
    adopted_at_ms: int
    session: str

    def __post_init__(self) -> None:
        if not isinstance(self.session, str) or self.session not in (
            NOT_STARTED, RUNNING, *_ENDED_SESSION_REASONS
        ):
            raise ValueError(f"Unknown session state: {self.session!r}")


@dataclass(frozen=True, slots=True)
class CooldownDecision:
    action: str
    reason: str
    gain_ms: int | None
    gain_permille: int | None
    cooldown_left_ms: int


def decide(current: CurrentPlan, candidate: PlanOption | None, *,
           now_ms: int, config: CooldownConfig) -> CooldownDecision:
    """Apply the cooldown rules, treating an unavailable candidate route as absent."""
    elapsed_ms = now_ms - current.adopted_at_ms
    if elapsed_ms < 0:
        raise ValueError("now_ms must be at or after adopted_at_ms")
    cooldown_left_ms = max(0, config.cooldown_ms - elapsed_ms)

    if current.session == RUNNING:
        return CooldownDecision(KEEP, KEEP_RUNNING, None, None, cooldown_left_ms)

    if candidate is not None and not candidate.route_available:
        candidate = None
    replacement_action = SWITCH if candidate is not None else RELEASE
    if current.session in _ENDED_SESSION_REASONS:
        return CooldownDecision(replacement_action, _ENDED_SESSION_REASONS[current.session],
                                None, None, cooldown_left_ms)

    option = current.option
    if not option.route_available:
        return CooldownDecision(replacement_action, ROUTE_LOST, None, None, cooldown_left_ms)
    if candidate is None:
        return CooldownDecision(KEEP, NO_CANDIDATE, None, None, cooldown_left_ms)
    if (option.source_id, option.target_id, option.batch_id) == (
        candidate.source_id, candidate.target_id, candidate.batch_id
    ):
        return CooldownDecision(KEEP, SAME_PLAN, None, None, cooldown_left_ms)

    gain_ms = option.eta_ms - candidate.eta_ms
    scaled_gain = gain_ms * 1000
    gain_permille = scaled_gain // option.eta_ms if option.eta_ms > 0 else None
    abs_ok = gain_ms >= config.min_gain_ms
    rel_ok = scaled_gain >= config.min_gain_permille * option.eta_ms

    if cooldown_left_ms == 0:
        action, reason = (SWITCH, COOLDOWN_EXPIRED) if gain_ms > 0 else (KEEP, NO_GAIN)
    elif gain_ms <= 0 or not (abs_ok or rel_ok):
        action, reason = KEEP, COOLDOWN_NO_GAIN
    elif abs_ok and rel_ok:
        action, reason = SWITCH, GAIN_ABOVE_THRESHOLDS
    elif abs_ok:
        action, reason = KEEP, COOLDOWN_BELOW_RELATIVE
    else:
        action, reason = KEEP, COOLDOWN_BELOW_ABSOLUTE
    return CooldownDecision(action, reason, gain_ms, gain_permille, cooldown_left_ms)
