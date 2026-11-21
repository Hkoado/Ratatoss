"""Track per-route setup and goodput estimates with an EWMA.

Each estimate belongs to one directed source/target pair and one path kind,
so A->B is separate from B->A and a relay path is separate from a direct one.
The caller supplies alpha and the initial estimates, typically a probe result
or a conservative configured value, until #6 measures real parameters.

Units follow the benchmark rules in docs/experiments.md:

* Timestamps are integer milliseconds on one observer's monotonic clock.
* Setup is milliseconds from session start to the first payload byte.
* Goodput is verified payload bits per second from first to last byte.

Usage::

    config = TelemetryConfig(alpha=0.25, initial=RouteEstimate(5_000, 2_000_000))
    telemetry = RouteTelemetry(config).observe(sample)
    route = telemetry.route("A", "B", "direct", wan=False)

``observe`` returns a new object and never changes the receiver. Replaying the
same samples in the same order gives the same estimates.
"""

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Mapping

from .plars_selection import Route

PATH_KINDS = frozenset({"direct", "relay", "unknown"})


@dataclass(frozen=True, slots=True)
class RouteKey:
    source_id: str
    target_id: str
    path_kind: str


@dataclass(frozen=True, slots=True)
class RouteEstimate:
    """Setup in milliseconds and payload goodput in bits per second."""

    setup_ms: float
    goodput_bps: float


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    alpha: float
    initial: RouteEstimate
    initial_by_route: Mapping[RouteKey, RouteEstimate] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (type(self.alpha) not in (int, float) or not math.isfinite(self.alpha)
                or not 0 < self.alpha <= 1):
            raise ValueError("alpha must be a finite number in (0, 1]")
        if not isinstance(self.initial_by_route, Mapping):
            raise ValueError("initial_by_route must be a mapping")
        for key, estimate in self.initial_by_route.items():
            _check_key(key)
            _check_estimate(estimate)
        _check_estimate(self.initial)
        object.__setattr__(self, "initial_by_route", MappingProxyType(dict(self.initial_by_route)))


@dataclass(frozen=True, slots=True)
class TransferSample:
    """One attempt as recorded in bench/transfers.csv.

    Use None for a missing marker. ``verified`` is true only after the
    received payload matched its SHA-256.
    """

    source_id: str
    target_id: str
    path_kind: str
    verified: bool
    payload_bytes: int | None = None
    start_ms: int | None = None
    first_byte_ms: int | None = None
    last_byte_ms: int | None = None


@dataclass(frozen=True, slots=True)
class Measurement:
    setup_ms: int | None
    goodput_bps: float | None


@dataclass(frozen=True, slots=True)
class _State:
    setup_ms: float
    goodput_bps: float
    setup_samples: int = 0
    goodput_samples: int = 0


def measure(sample: TransferSample) -> Measurement:
    """Return the trustworthy setup and goodput of one sample.

    Unverified payloads and missing or inconsistent markers yield None, never
    zero. Malformed values raise ValueError.
    """
    _check_key(RouteKey(sample.source_id, sample.target_id, sample.path_kind))
    if type(sample.verified) is not bool:
        raise ValueError("verified must be a boolean")
    for name in ("payload_bytes", "start_ms", "first_byte_ms", "last_byte_ms"):
        value = getattr(sample, name)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"{name} must be a non-negative integer or None")
    if not sample.verified:
        return Measurement(None, None)

    setup = None
    if sample.start_ms is not None and sample.first_byte_ms is not None:
        if sample.first_byte_ms >= sample.start_ms:
            setup = sample.first_byte_ms - sample.start_ms

    goodput = None
    if (sample.payload_bytes and sample.first_byte_ms is not None
            and sample.last_byte_ms is not None and sample.last_byte_ms > sample.first_byte_ms):
        goodput = sample.payload_bytes * 8 * 1000 / (sample.last_byte_ms - sample.first_byte_ms)
    return Measurement(setup, goodput)


class RouteTelemetry:
    """Immutable EWMA estimates keyed by directed pair and path kind."""

    __slots__ = ("config", "_states")

    def __init__(self, config: TelemetryConfig, _states: Mapping[RouteKey, _State] | None = None):
        if not isinstance(config, TelemetryConfig):
            raise ValueError("Expected a TelemetryConfig")
        self.config = config
        self._states = MappingProxyType(dict(_states or {}))

    def observe(self, sample: TransferSample) -> "RouteTelemetry":
        measured = measure(sample)
        if measured.setup_ms is None and measured.goodput_bps is None:
            return self
        key = RouteKey(sample.source_id, sample.target_id, sample.path_kind)
        state = self._state(key)
        alpha = self.config.alpha
        if measured.setup_ms is not None:
            state = _State(alpha * measured.setup_ms + (1 - alpha) * state.setup_ms,
                           state.goodput_bps, state.setup_samples + 1, state.goodput_samples)
        if measured.goodput_bps is not None:
            state = _State(state.setup_ms, alpha * measured.goodput_bps + (1 - alpha) * state.goodput_bps,
                           state.setup_samples, state.goodput_samples + 1)
        return RouteTelemetry(self.config, {**self._states, key: state})

    def estimate(self, source_id: str, target_id: str, path_kind: str) -> RouteEstimate:
        state = self._state(_check_key(RouteKey(source_id, target_id, path_kind)))
        return RouteEstimate(state.setup_ms, state.goodput_bps)

    def sample_counts(self, source_id: str, target_id: str, path_kind: str) -> tuple[int, int]:
        """Return how many setup and goodput samples the estimate absorbed."""
        state = self._state(_check_key(RouteKey(source_id, target_id, path_kind)))
        return state.setup_samples, state.goodput_samples

    def route(self, source_id: str, target_id: str, path_kind: str, *,
              wan: bool = False, resources: tuple[str, ...] = ()) -> Route:
        """Hand the estimate to PLARS selection, rounding toward caution.

        Setup rounds up to whole milliseconds and goodput rounds down to whole
        bits per second, with a floor of 1 bit/s that Route requires.
        """
        estimate = self.estimate(source_id, target_id, path_kind)
        return Route(
            source_id=source_id,
            target_id=target_id,
            goodput_bps=max(1, math.floor(estimate.goodput_bps)),
            setup_ms=math.ceil(estimate.setup_ms),
            wan=wan,
            resources=resources,
        )

    def _state(self, key: RouteKey) -> _State:
        if key in self._states:
            return self._states[key]
        initial = self.config.initial_by_route.get(key, self.config.initial)
        return _State(initial.setup_ms, initial.goodput_bps)


def _check_key(key: RouteKey) -> RouteKey:
    if not isinstance(key, RouteKey):
        raise ValueError("Expected a RouteKey")
    for name in ("source_id", "target_id"):
        value = getattr(key, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    if key.source_id == key.target_id:
        raise ValueError("A route needs two different devices")
    if key.path_kind not in PATH_KINDS:
        raise ValueError(f"path_kind must be one of {sorted(PATH_KINDS)}")
    return key


def _check_estimate(estimate: RouteEstimate) -> None:
    if not isinstance(estimate, RouteEstimate):
        raise ValueError("Expected a RouteEstimate")
    for name, minimum_exclusive in (("setup_ms", None), ("goodput_bps", 0)):
        value = getattr(estimate, name)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if value < 0 or (minimum_exclusive is not None and value <= minimum_exclusive):
            raise ValueError(f"{name} is out of range")
