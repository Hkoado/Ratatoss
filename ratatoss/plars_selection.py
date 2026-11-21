"""Choose one round of PLARS assignments from an immutable resource snapshot.

The function is pure: it reads a snapshot and returns the assignments to grant
now, plus the targets that should wait. The caller supplies measured setup,
goodput, target ETA, held load and tolerance values. The controller still
checks consent and leases inside its own transaction when it grants work.

All times are integer milliseconds relative to the snapshot instant. Rates are
payload bits per second. Iteration follows sorted identifiers, so the result
does not depend on the order of the input collections.
"""

from dataclasses import dataclass
from typing import Iterable

WAIT_FOR_SLOT = "WAIT_FOR_SLOT"
NO_CANDIDATE = "NO_CANDIDATE"


@dataclass(frozen=True, slots=True)
class Batch:
    batch_id: int
    size: int


@dataclass(frozen=True, slots=True)
class Device:
    """One job member as seen by the scheduler.

    Each slot tuple holds one entry per configured slot with the milliseconds
    until that slot is free, so 0 means free now and held load is positive.
    An empty tuple disables the direction.
    """

    device_id: str
    online: bool
    reconciled: bool
    verified_batches: frozenset[int]
    rx_slot_free_in_ms: tuple[int, ...] = ()
    tx_slot_free_in_ms: tuple[int, ...] = ()
    is_target: bool = False
    can_transmit: bool = False
    is_origin: bool = False
    eta_ms: int = 0
    verify_ms: int = 0


@dataclass(frozen=True, slots=True)
class Route:
    """A permitted directed path with its measured or configured estimates."""

    source_id: str
    target_id: str
    goodput_bps: int
    setup_ms: int
    wan: bool = False
    resources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SharedResource:
    """A shared bottleneck such as an uplink, branch WAN, access point or relay."""

    resource_id: str
    available_bps: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    batches: tuple[Batch, ...]
    devices: tuple[Device, ...]
    routes: tuple[Route, ...]
    resources: tuple[SharedResource, ...] = ()
    leased: frozenset[tuple[str, int]] = frozenset()
    tolerance_ms: int = 0


@dataclass(frozen=True, slots=True)
class Selection:
    source_id: str
    target_id: str
    batch_id: int
    goodput_bps: int
    finish_in_ms: int
    wan_bytes: int
    origin_bytes: int


@dataclass(frozen=True, slots=True)
class Waiting:
    target_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class SelectionRound:
    selections: tuple[Selection, ...]
    waiting: tuple[Waiting, ...]


@dataclass(frozen=True, slots=True)
class _Option:
    source_id: str
    batch_id: int
    wait_ms: int
    transfer_end_ms: int
    finish_ms: int
    goodput_bps: int
    wan_bytes: int
    origin_bytes: int
    resources: tuple[str, ...]


def select_assignments(snapshot: Snapshot) -> SelectionRound:
    """Return the assignments to grant now for one scheduling round.

    Targets are visited in passes by descending ETA, then device ID. Each pass
    gives a target at most one assignment. For the visited target, the option
    with the earliest finish wins, where finish adds slot wait, setup,
    transfer at the usable goodput and verification. Options within the
    tolerance of the earliest finish are ranked by fewer WAN bytes, fewer
    origin bytes, then batch ID and source ID. If the winning option must wait
    for a slot, the target waits for this round instead of taking a slower
    path. Every selection reserves its slots, shared bandwidth and key before
    the next choice.
    """
    _validate(snapshot)
    sizes = {batch.batch_id: batch.size for batch in snapshot.batches}
    devices = {device.device_id: device for device in snapshot.devices}
    routes = {(route.source_id, route.target_id): route for route in snapshot.routes}
    available = {resource.resource_id: resource.available_bps for resource in snapshot.resources}
    rx_slots = {key: list(device.rx_slot_free_in_ms) for key, device in devices.items()}
    tx_slots = {key: list(device.tx_slot_free_in_ms) for key, device in devices.items()}
    reserved = set(snapshot.leased)

    targets = sorted(
        (device for device in devices.values()
         if device.is_target and device.online and device.reconciled and device.rx_slot_free_in_ms),
        key=lambda device: (-device.eta_ms, device.device_id),
    )
    sources = sorted(
        (device for device in devices.values()
         if device.can_transmit and device.online and device.reconciled and device.tx_slot_free_in_ms),
        key=lambda device: device.device_id,
    )

    selections: list[Selection] = []
    waiting: dict[str, str] = {}
    granted: set[str] = set()
    progress = True
    while progress:
        progress = False
        for target in targets:
            if target.device_id in waiting:
                continue
            missing = sorted(
                batch_id for batch_id in sizes
                if batch_id not in target.verified_batches
                and (target.device_id, batch_id) not in reserved
            )
            if not missing:
                continue
            options = list(_options(target, missing, sources, sizes, routes, available,
                                    rx_slots, tx_slots))
            if not options:
                if target.device_id not in granted:
                    waiting[target.device_id] = NO_CANDIDATE
                continue
            choice = _choose(options, snapshot.tolerance_ms)
            if choice.wait_ms:
                waiting[target.device_id] = WAIT_FOR_SLOT
                continue

            _reserve_slot(tx_slots[choice.source_id], choice.transfer_end_ms)
            _reserve_slot(rx_slots[target.device_id], choice.finish_ms)
            for resource_id in choice.resources:
                available[resource_id] -= choice.goodput_bps
            reserved.add((target.device_id, choice.batch_id))
            granted.add(target.device_id)
            selections.append(Selection(
                source_id=choice.source_id,
                target_id=target.device_id,
                batch_id=choice.batch_id,
                goodput_bps=choice.goodput_bps,
                finish_in_ms=choice.finish_ms,
                wan_bytes=choice.wan_bytes,
                origin_bytes=choice.origin_bytes,
            ))
            progress = True

    return SelectionRound(
        selections=tuple(selections),
        waiting=tuple(Waiting(target_id, reason) for target_id, reason in sorted(waiting.items())),
    )


def _options(target: Device, missing: list[int], sources: list[Device], sizes: dict[int, int],
             routes: dict[tuple[str, str], Route], available: dict[str, int],
             rx_slots: dict[str, list[int]], tx_slots: dict[str, list[int]]) -> Iterable[_Option]:
    rx_wait = min(rx_slots[target.device_id])
    for source in sources:
        if source.device_id == target.device_id:
            continue
        route = routes.get((source.device_id, target.device_id))
        if route is None:
            continue
        goodput = min([route.goodput_bps, *(available[key] for key in route.resources)])
        if goodput <= 0:
            continue
        wait = max(rx_wait, min(tx_slots[source.device_id]))
        for batch_id in missing:
            if batch_id not in source.verified_batches:
                continue
            size = sizes[batch_id]
            transfer_end = wait + route.setup_ms + _transfer_ms(size, goodput)
            yield _Option(
                source_id=source.device_id,
                batch_id=batch_id,
                wait_ms=wait,
                transfer_end_ms=transfer_end,
                finish_ms=transfer_end + target.verify_ms,
                goodput_bps=goodput,
                wan_bytes=size if route.wan else 0,
                origin_bytes=size if source.is_origin else 0,
                resources=route.resources,
            )


def _choose(options: list[_Option], tolerance_ms: int) -> _Option:
    earliest = min(option.finish_ms for option in options)
    tied = (option for option in options if option.finish_ms <= earliest + tolerance_ms)
    return min(tied, key=lambda option: (
        option.wan_bytes, option.origin_bytes, option.batch_id, option.source_id,
    ))


def _reserve_slot(slots: list[int], busy_until_ms: int) -> None:
    slots[slots.index(min(slots))] = busy_until_ms


def _transfer_ms(size: int, goodput_bps: int) -> int:
    return (size * 8 * 1000 + goodput_bps - 1) // goodput_bps


def _validate(snapshot: Snapshot) -> None:
    if not isinstance(snapshot, Snapshot):
        raise ValueError("Expected a Snapshot")
    _integer("tolerance_ms", snapshot.tolerance_ms, 0)

    batch_ids = set()
    for batch in snapshot.batches:
        _integer("batch_id", batch.batch_id, 0)
        _integer("batch size", batch.size, 1)
        if batch.batch_id in batch_ids:
            raise ValueError(f"Duplicate batch {batch.batch_id}")
        batch_ids.add(batch.batch_id)

    device_ids = set()
    for device in snapshot.devices:
        _identifier("device_id", device.device_id)
        if device.device_id in device_ids:
            raise ValueError(f"Duplicate device {device.device_id}")
        device_ids.add(device.device_id)
        for name in ("online", "reconciled", "is_target", "can_transmit", "is_origin"):
            if type(getattr(device, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        _integer("eta_ms", device.eta_ms, 0)
        _integer("verify_ms", device.verify_ms, 0)
        for name in ("rx_slot_free_in_ms", "tx_slot_free_in_ms"):
            slots = getattr(device, name)
            if not isinstance(slots, tuple):
                raise ValueError(f"{name} must be a tuple")
            for value in slots:
                _integer(name, value, 0)
        if not isinstance(device.verified_batches, frozenset):
            raise ValueError("verified_batches must be a frozenset")
        if not device.verified_batches <= batch_ids:
            raise ValueError(f"Device {device.device_id} reports an unknown batch")

    resource_ids = set()
    for resource in snapshot.resources:
        _identifier("resource_id", resource.resource_id)
        _integer("available_bps", resource.available_bps, 0)
        if resource.resource_id in resource_ids:
            raise ValueError(f"Duplicate resource {resource.resource_id}")
        resource_ids.add(resource.resource_id)

    route_keys = set()
    for route in snapshot.routes:
        key = (route.source_id, route.target_id)
        if not set(key) <= device_ids or route.source_id == route.target_id:
            raise ValueError(f"Invalid route {route.source_id} -> {route.target_id}")
        if key in route_keys:
            raise ValueError(f"Duplicate route {route.source_id} -> {route.target_id}")
        route_keys.add(key)
        _integer("goodput_bps", route.goodput_bps, 1)
        _integer("setup_ms", route.setup_ms, 0)
        if type(route.wan) is not bool:
            raise ValueError("wan must be a boolean")
        if not isinstance(route.resources, tuple) or not set(route.resources) <= resource_ids:
            raise ValueError(f"Route {route.source_id} -> {route.target_id} uses an unknown resource")
        if len(set(route.resources)) != len(route.resources):
            raise ValueError(f"Route {route.source_id} -> {route.target_id} repeats a resource")

    if not isinstance(snapshot.leased, frozenset):
        raise ValueError("leased must be a frozenset")
    for target_id, batch_id in snapshot.leased:
        if target_id not in device_ids or batch_id not in batch_ids:
            raise ValueError("Lease key refers to an unknown device or batch")


def _integer(name: str, value: object, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
