"""Fixed, topology-aware scheduling of missing verified batches."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from .leases import LeaseProfile, maintain_dispatchable_leases
from .registry import HEARTBEAT_TIMEOUT_MS, Registry

PREPARE_LEASE_MS = 30_000


@dataclass(frozen=True)
class FixedSchedule:
    # A route maps its device pair to a configured relay or link budget.
    routes: Mapping[tuple[str, str], str]
    link_slots: Mapping[str, int]
    max_sessions: int
    # Optional (B, C) demo peers on a measured LAN.
    lan_peers: tuple[str, str] | None = None
    # Per-target alternatives in order of preference, after the primary path.
    fallbacks: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def sources(self, origin: str, target: str, batch_id: int) -> tuple[str, ...]:
        preferred = origin
        if self.lan_peers and origin not in self.lan_peers and target in self.lan_peers:
            first = self.lan_peers[batch_id % 2]
            if first != target:
                preferred = first
        choices = (preferred, *self.fallbacks.get(target, ()), origin)
        return tuple(source for source in dict.fromkeys(choices) if source != target)


def issue_assignments(registry: Registry, schedule: FixedSchedule,
                      profiles: Mapping[str, LeaseProfile]) -> list[str]:
    """Reserve available slots and create leases in the caller's write transaction."""
    registry.expire_offers()
    maintain_dispatchable_leases(registry)
    live = registry.rows(
        "SELECT relay_profile FROM assignments WHERE state IN ('OFFERED', 'RUNNING')"
    )
    remaining = schedule.max_sessions - len(live)
    if remaining <= 0:
        return []
    link_usage = Counter(row["relay_profile"] for row in live)
    online_devices = registry.rows(
        "SELECT device_id, connection_epoch, rx_free, tx_free FROM devices WHERE revoked_at_ms IS NULL "
        "AND heartbeat_at_ms > ? AND heartbeat_at_ms <= ?",
        (registry.now_ms - HEARTBEAT_TIMEOUT_MS, registry.now_ms),
    )
    devices = {row["device_id"]: dict(row) for row in online_devices}
    targets = registry.rows(
        "SELECT j.job_id, j.source_device_id AS origin, o.target_device_id AS target, b.batch_id, b.size_bytes "
        "FROM jobs j JOIN offers o USING (job_id) JOIN job_batches b USING (job_id) "
        "JOIN job_members m ON m.job_id = j.job_id AND m.device_id = o.target_device_id "
        "JOIN devices d ON d.device_id = m.device_id "
        "WHERE j.state = 'OPEN' AND o.state = 'ACCEPTED' "
        "AND m.reconciled_epoch = d.connection_epoch AND d.rx_free > 0 "
        "AND NOT EXISTS (SELECT 1 FROM inventory i WHERE i.job_id = j.job_id "
        "AND i.device_id = o.target_device_id AND i.batch_id = b.batch_id) "
        "AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.job_id = j.job_id "
        "AND a.target_device_id = o.target_device_id AND a.batch_id = b.batch_id "
        "AND a.state IN ('OFFERED', 'RUNNING')) "
        "ORDER BY j.created_at_ms, j.job_id, b.batch_id, o.rowid"
    )
    issued = []
    for target in targets:
        receiver = devices.get(target["target"])
        if receiver is None or receiver["rx_free"] == 0:
            continue
        job_id, batch_id = target["job_id"], target["batch_id"]
        choices = schedule.sources(target["origin"], target["target"], batch_id)
        if choices and _wait_for_forwarder(
            registry, schedule, profiles, devices, link_usage, target, choices[0],
        ):
            continue
        previous = registry.row(
            "SELECT source_device_id FROM assignments WHERE job_id = ? AND target_device_id = ? "
            "AND batch_id = ? ORDER BY rowid DESC LIMIT 1", (job_id, target["target"], batch_id),
        )
        if previous and previous["source_device_id"] in choices:
            previous_source = previous["source_device_id"]
            choices = tuple(source for source in choices if source != previous_source) + (previous_source,)
        for source in choices:
            route = _usable_route(schedule, profiles, source, target["target"], target["size_bytes"])
            sender = devices.get(source)
            if (
                sender is None or sender["tx_free"] == 0 or route is None
                or link_usage[route] >= schedule.link_slots.get(route, 0)
                or not _can_send(registry, job_id, source, batch_id, sender["connection_epoch"])
            ):
                continue
            assignment_id = str(uuid4())
            registry.db.execute(
                "INSERT INTO assignments (assignment_id, job_id, batch_id, source_device_id, "
                "target_device_id, source_epoch, target_epoch, relay_profile, created_at_ms, "
                "expires_at_ms, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OFFERED')",
                (assignment_id, job_id, batch_id, source, target["target"], sender["connection_epoch"],
                 receiver["connection_epoch"], route, registry.now_ms, registry.now_ms + PREPARE_LEASE_MS),
            )
            registry.db.execute("UPDATE devices SET rx_free = rx_free - 1 WHERE device_id = ?",
                                (target["target"],))
            registry.db.execute("UPDATE devices SET tx_free = tx_free - 1 WHERE device_id = ?", (source,))
            receiver["rx_free"] -= 1
            sender["tx_free"] -= 1
            link_usage[route] += 1
            issued.append(assignment_id)
            remaining -= 1
            break
        if remaining == 0:
            break
    return issued


def _usable_route(schedule: FixedSchedule, profiles: Mapping[str, LeaseProfile],
                  source: str, target: str, batch_bytes: int) -> str | None:
    link = schedule.routes.get((source, target))
    if link is None or not schedule.link_slots.get(link, 0):
        return None
    profile = profiles.get(link)
    return link if profile is not None and profile.fits(batch_bytes) else None


def _wait_for_forwarder(registry: Registry, schedule: FixedSchedule,
                        profiles: Mapping[str, LeaseProfile], devices: dict,
                        link_usage: Counter, target, preferred: str) -> bool:
    """Wait for a viable first hop that is already live or can be offered now."""
    origin = target["origin"]
    if preferred == origin or origin not in devices or preferred not in devices:
        return False
    job_id, batch_id = target["job_id"], target["batch_id"]
    batch_bytes = target["size_bytes"]
    first_link = _usable_route(schedule, profiles, origin, preferred, batch_bytes)
    if first_link is None or _usable_route(
        schedule, profiles, preferred, target["target"], batch_bytes,
    ) is None:
        return False
    if not _can_send(registry, job_id, origin, batch_id, devices[origin]["connection_epoch"]):
        return False
    first_hop = registry.row(
        "SELECT EXISTS (SELECT 1 FROM assignments a WHERE a.job_id = o.job_id "
        "AND a.target_device_id = o.target_device_id AND a.batch_id = ? "
        "AND a.state IN ('OFFERED', 'RUNNING')) AS live "
        "FROM offers o JOIN job_members m ON m.job_id = o.job_id "
        "AND m.device_id = o.target_device_id "
        "WHERE o.job_id = ? AND o.target_device_id = ? AND o.state = 'ACCEPTED' "
        "AND o.allow_forward = 1 AND m.reconciled_epoch = ? "
        "AND NOT EXISTS (SELECT 1 FROM inventory i WHERE i.job_id = o.job_id "
        "AND i.device_id = o.target_device_id AND i.batch_id = ?) "
        "AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.job_id = o.job_id "
        "AND a.target_device_id = o.target_device_id AND a.batch_id = ? "
        "AND a.state IN ('FAILED', 'EXPIRED', 'CANCELED'))",
        (batch_id, job_id, preferred, devices[preferred]["connection_epoch"], batch_id, batch_id),
    )
    return first_hop is not None and (
        first_hop["live"] or (
            devices[preferred]["rx_free"] > 0 and devices[origin]["tx_free"] > 0
            and link_usage[first_link] < schedule.link_slots[first_link]
        )
    )


def _can_send(registry: Registry, job_id: str, source: str, batch_id: int, epoch: int) -> bool:
    return registry.row(
        "SELECT 1 FROM inventory i JOIN job_members m USING (job_id, device_id) "
        "JOIN jobs j USING (job_id) LEFT JOIN offers o ON o.job_id = i.job_id "
        "AND o.target_device_id = i.device_id "
        "WHERE i.job_id = ? AND i.device_id = ? AND i.batch_id = ? AND m.reconciled_epoch = ? "
        "AND (j.source_device_id = i.device_id OR "
        "(o.state IN ('ACCEPTED', 'VERIFIED') AND o.allow_forward = 1))",
        (job_id, source, batch_id, epoch),
    ) is not None
