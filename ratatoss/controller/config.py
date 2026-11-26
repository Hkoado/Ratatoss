"""Load controller topology and lease budgets from an operator-owned TOML file."""

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ..manifest import decode_manifest_object
from .leases import LeaseProfile
from .registry import is_uuid4
from .schedule import FixedSchedule

DEFAULT_MAX_MANIFEST_BYTES = 4 * 1024**2
DEFAULT_MAX_TARGETS = 32


@dataclass(frozen=True)
class ControllerConfig:
    schedule: FixedSchedule
    lease_profiles: Mapping[str, LeaseProfile]
    max_manifest_bytes: int = DEFAULT_MAX_MANIFEST_BYTES
    max_targets: int = DEFAULT_MAX_TARGETS

    @classmethod
    def load(cls, path: Path) -> "ControllerConfig":
        with path.open("rb") as stream:
            config = tomllib.load(stream)
        _fields(
            config, {"max_sessions", "links", "routes"},
            {"max_manifest_bytes", "max_targets", "lan_peers", "fallbacks"},
            "controller",
        )
        slots, profiles = _links(config["links"], path.parent)
        routes = _routes(config["routes"], slots)
        lan = _ids(config["lan_peers"], "lan_peers") if "lan_peers" in config else None
        if lan is not None and len(lan) != 2:
            raise ValueError("lan_peers must contain two distinct device IDs")
        raw_fallbacks = config.get("fallbacks", {})
        _fields(raw_fallbacks, set(), None, "fallbacks")
        fallbacks = {}
        for target, raw_devices in raw_fallbacks.items():
            if not is_uuid4(target):
                raise ValueError("fallbacks must use device UUIDs as keys")
            devices = _ids(raw_devices, "fallbacks")
            if target in devices or any((device, target) not in routes for device in devices):
                raise ValueError("Each fallback must have a configured route to its target")
            fallbacks[target] = devices

        schedule = FixedSchedule(
            routes=MappingProxyType(routes),
            link_slots=MappingProxyType(slots),
            max_sessions=_positive(config["max_sessions"], "max_sessions"),
            lan_peers=(lan[0], lan[1]) if lan else None,
            fallbacks=MappingProxyType(fallbacks),
        )
        return cls(
            schedule, MappingProxyType(profiles),
            _positive(config.get("max_manifest_bytes", DEFAULT_MAX_MANIFEST_BYTES), "max_manifest_bytes"),
            _positive(config.get("max_targets", DEFAULT_MAX_TARGETS), "max_targets"),
        )


def _fields(value: object, required: set[str], optional: set[str] | None, name: str) -> None:
    if not isinstance(value, dict) or not required <= value.keys() or (
        optional is not None and not value.keys() <= required | optional
    ):
        raise ValueError(f"Invalid fields in {name}")


def _positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _ids(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(is_uuid4(item) for item in value) or len(set(value)) != len(value):
        raise ValueError(f"{name} must contain distinct device UUIDs")
    return tuple(value)


def _links(links: object, parent: Path) -> tuple[dict[str, int], dict[str, LeaseProfile]]:
    _fields(links, set(), None, "links")
    slots, profiles = {}, {}
    for name, link in links.items():
        if not name or not name.isascii() or not all(char.isalnum() or char in "-_" for char in name):
            raise ValueError("Link names must consist of ASCII letters, digits, hyphens or underscores")
        _fields(link, {"max_sessions"}, {"budget", "benchmark"}, "link")
        slots[name] = _positive(link["max_sessions"], "link max_sessions")
        if "budget" in link and "benchmark" in link:
            raise ValueError("Specify a single budget source per link")
        if "budget" in link:
            profiles[name] = _budget(link["budget"])
        if "benchmark" in link:
            reference = link["benchmark"]
            _fields(reference, {"path", "profile"}, set(), "benchmark")
            if not isinstance(reference["path"], str) or not isinstance(reference["profile"], str):
                raise ValueError("Benchmark path and profile must be strings")
            benchmark = decode_manifest_object((parent / reference["path"]).read_bytes())
            available = benchmark.get("profiles")
            if not isinstance(available, dict) or reference["profile"] not in available:
                raise ValueError("Benchmark profile is unavailable")
            profiles[name] = _budget(available[reference["profile"]], measured=True)
    return slots, profiles


def _budget(value: object, *, measured: bool = False) -> LeaseProfile:
    fields = {"min_goodput_bps", "setup_budget_ms", "verify_commit_ms", "margin_ms",
              "lease_ms", "adapter_timeout_ms"}
    _fields(value, fields, {"basis"} if measured else set(), "lease budget")
    return LeaseProfile(**{field: value[field] for field in fields})


def _routes(entries: object, slots: Mapping[str, int]) -> dict[tuple[str, str], str]:
    if not isinstance(entries, list):
        raise ValueError("routes must be an array of tables")
    result = {}
    for route in entries:
        _fields(route, {"source", "target", "link"}, set(), "route")
        source, target = _ids([route["source"], route["target"]], "route")
        link = route["link"]
        if not isinstance(link, str) or link not in slots:
            raise ValueError("Route refers to an unknown link")
        if (source, target) in result:
            raise ValueError("Duplicate route")
        result[source, target] = link
    return result
