"""Controller assignment lifecycle and process-local Croc session codes."""

import secrets
import sqlite3
from dataclasses import dataclass
from string import ascii_letters, digits
from threading import Lock

from ..lease_profile import evaluate_lease_budget
from .registry import HEARTBEAT_TIMEOUT_MS, Registry, RegistryError, online, utc

LIVE_STATES = ("OFFERED", "RUNNING")


@dataclass(frozen=True)
class LeaseProfile:
    min_goodput_bps: int
    setup_budget_ms: int
    verify_commit_ms: int
    margin_ms: int
    lease_ms: int
    adapter_timeout_ms: int

    def __post_init__(self):
        if type(self.lease_ms) is not int or self.lease_ms <= 0:
            raise ValueError("lease_ms must be a positive integer")
        self.fits(1)

    def fits(self, batch_bytes: int) -> bool:
        return evaluate_lease_budget(
            batch_bytes=batch_bytes, min_goodput_bps=self.min_goodput_bps,
            remaining_lease_ms=self.lease_ms, remaining_adapter_ms=self.adapter_timeout_ms,
            remaining_setup_ms=self.setup_budget_ms, verify_commit_ms=self.verify_commit_ms,
            margin_ms=self.margin_ms,
        ).fits


class SessionCodes:
    def __init__(self):
        self._entries: dict[str, tuple[int, str]] = {}
        self._lock = Lock()

    def issue(self, assignment_id: str, expires_at_ms: int) -> str:
        with self._lock:
            # Croc's legacy format uses the first four bytes as the relay room.
            used_rooms = {code[:4] for _, code in self._entries.values()}
            room = self._new_room()
            while room in used_rooms:
                room = self._new_room()
            code = f"{room}-{secrets.token_hex(16)}"
            self._entries[assignment_id] = expires_at_ms, code
        return code

    @staticmethod
    def _new_room() -> str:
        return "".join(secrets.choice(ascii_letters + digits) for _ in range(4))

    def get(self, assignment_id: str, now_ms: int) -> str | None:
        with self._lock:
            entry = self._entries.get(assignment_id)
            return entry[1] if entry is not None and entry[0] > now_ms else None

    def discard_expired(self, now_ms: int) -> None:
        with self._lock:
            self._entries = {key: entry for key, entry in self._entries.items() if entry[0] > now_ms}


def maintain_leases(registry: Registry) -> None:
    registry.db.execute(
        "UPDATE assignments SET state = 'EXPIRED', closed_at_ms = max(created_at_ms, ?) "
        "WHERE state IN ('OFFERED', 'RUNNING') AND expires_at_ms <= ?",
        (registry.now_ms, registry.now_ms),
    )
    registry.db.execute(
        "UPDATE assignments AS a SET state = 'CANCELED', closed_at_ms = max(created_at_ms, ?) "
        "WHERE a.state IN ('OFFERED', 'RUNNING') AND EXISTS (SELECT 1 FROM devices d "
        "WHERE (d.device_id = a.source_device_id OR d.device_id = a.target_device_id) AND "
        "(d.revoked_at_ms IS NOT NULL OR d.heartbeat_at_ms IS NULL OR d.heartbeat_at_ms <= ? "
        "OR d.heartbeat_at_ms > ? OR d.connection_epoch <> CASE WHEN d.device_id = a.source_device_id "
        "THEN a.source_epoch ELSE a.target_epoch END))",
        (registry.now_ms, registry.now_ms - HEARTBEAT_TIMEOUT_MS, registry.now_ms),
    )


def reset_connections(registry: Registry) -> None:
    """Invalidate process-local leases before this controller starts serving."""
    registry.db.execute(
        "UPDATE assignments SET state = 'CANCELED', closed_at_ms = max(created_at_ms, ?) "
        "WHERE state IN ('OFFERED', 'RUNNING')", (registry.now_ms,),
    )
    registry.db.execute(
        "UPDATE devices SET boot_id = NULL, heartbeat_at_ms = NULL, rx_free = 0, tx_free = 0 "
        "WHERE heartbeat_at_ms IS NOT NULL"
    )


def _assignment(registry: Registry, device_id: str, assignment_id: str, *,
                rx_only: bool = False) -> sqlite3.Row:
    row = registry.row(
        "SELECT a.*, j.manifest_sha256, j.state AS job_state, b.sha256 AS batch_sha256, "
        "b.size_bytes, o.state AS consent, d.connection_epoch, m.reconciled_epoch, "
        "d.heartbeat_at_ms, d.revoked_at_ms "
        "FROM assignments a JOIN jobs j USING (job_id) JOIN job_batches b USING (job_id, batch_id) "
        "JOIN offers o USING (job_id, target_device_id) "
        "JOIN devices d ON d.device_id = a.target_device_id "
        "JOIN job_members m ON m.job_id = a.job_id AND m.device_id = a.target_device_id "
        "WHERE a.assignment_id = ? AND (a.target_device_id = ? OR "
        "(NOT ? AND a.source_device_id = ?))",
        (assignment_id, device_id, rx_only, device_id),
    )
    if row is None:
        raise RegistryError(404)
    return row


def _view(row, role: str, now_ms: int, *, code: str | None = None) -> dict:
    result = {key: row[key] for key in (
        "assignment_id", "job_id", "batch_id", "source_device_id", "target_device_id",
        "relay_profile", "state",
    )}
    result.update(role=role, manifest_sha256=row["manifest_sha256"].hex(),
                  lease_expires_at=utc(row["expires_at_ms"]),
                  lease_remaining_ms=row["expires_at_ms"] - now_ms)
    if code is not None:
        result["croc_code"] = code
    return result


def list_assignments(registry: Registry, device_id: str, codes: SessionCodes) -> dict:
    maintain_leases(registry)
    codes.discard_expired(registry.now_ms)
    rows = registry.rows(
        "SELECT a.*, j.manifest_sha256 FROM assignments a JOIN jobs j USING (job_id) "
        "WHERE a.state IN ('OFFERED', 'RUNNING') AND a.expires_at_ms > ? "
        "AND (a.source_device_id = ? OR a.target_device_id = ?) ORDER BY a.created_at_ms, a.rowid",
        (registry.now_ms, device_id, device_id),
    )
    assignments = []
    for row in rows:
        role = "RX" if row["target_device_id"] == device_id else "TX"
        code = None
        if row["state"] == "RUNNING":
            session_code = codes.get(row["assignment_id"], registry.now_ms)
            if session_code is None:
                continue
            if role == "TX":
                code = session_code
        assignments.append(_view(row, role, registry.now_ms, code=code))
    return {"server_time": utc(registry.now_ms), "assignments": assignments}


def ready(registry: Registry, device_id: str, assignment_id: str, codes: SessionCodes,
          profile: LeaseProfile | None, *, replay: bool = False) -> dict:
    maintain_leases(registry)
    codes.discard_expired(registry.now_ms)
    row = _assignment(registry, device_id, assignment_id, rx_only=True)
    if row["expires_at_ms"] <= registry.now_ms:
        raise RegistryError(410)
    if replay and row["state"] == "RUNNING":
        code = codes.get(assignment_id, registry.now_ms)
        if code is None:
            raise RegistryError(409)
        return _view(row, "RX", registry.now_ms, code=code)
    if replay or row["state"] != "OFFERED" or profile is None or not profile.fits(row["size_bytes"]):
        raise RegistryError(409)
    expires = registry.now_ms + profile.lease_ms
    registry.db.execute(
        "UPDATE assignments SET state = 'RUNNING', expires_at_ms = ? WHERE assignment_id = ?",
        (expires, assignment_id),
    )
    code = codes.issue(assignment_id, expires)
    return _view(dict(row, state="RUNNING", expires_at_ms=expires), "RX", registry.now_ms, code=code)


def _audit(registry: Registry, row, result: str) -> None:
    registry.db.execute(
        "INSERT INTO audit (job_id, batch_id, source_device_id, target_device_id, assignment_id, "
        "result_code, occurred_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row["job_id"], row["batch_id"], row["source_device_id"], row["target_device_id"],
         row["assignment_id"], result, registry.now_ms),
    )


def ack(registry: Registry, device_id: str, assignment_id: str, batch_sha256: str) -> dict:
    maintain_leases(registry)
    row = _assignment(registry, device_id, assignment_id, rx_only=True)
    if batch_sha256 != row["batch_sha256"].hex() or row["consent"] not in {"ACCEPTED", "VERIFIED"}:
        raise RegistryError(409)
    outcome = "ACKED" if row["state"] in {"RUNNING", "ACKED"} else "LATE_ACKNOWLEDGED"
    if row["ack_processed_at_ms"] is not None:
        return {"assignment_id": assignment_id, "outcome": outcome}
    if (
        row["state"] == "OFFERED" or row["job_state"] != "OPEN"
        or not online(row, registry.now_ms) or row["reconciled_epoch"] != row["connection_epoch"]
    ):
        raise RegistryError(409)
    key = (row["job_id"], device_id, row["batch_id"])
    if row["target_epoch"] != row["connection_epoch"] and not registry.row(
        "SELECT 1 FROM inventory WHERE job_id = ? AND device_id = ? AND batch_id = ?", key,
    ):
        raise RegistryError(409)
    recorded = registry.db.execute(
        "INSERT INTO inventory VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
        (*key, registry.now_ms),
    )
    if recorded.rowcount:
        _audit(registry, row, outcome)
    registry.db.execute(
        "UPDATE assignments SET ack_processed_at_ms = max(created_at_ms, ?), "
        "state = CASE WHEN state = 'RUNNING' THEN 'ACKED' ELSE state END, "
        "closed_at_ms = CASE WHEN state = 'RUNNING' THEN max(created_at_ms, ?) ELSE closed_at_ms END "
        "WHERE assignment_id = ?", (registry.now_ms, registry.now_ms, assignment_id),
    )
    return {"assignment_id": assignment_id, "outcome": outcome}


def fail(registry: Registry, device_id: str, assignment_id: str, code: str) -> dict:
    maintain_leases(registry)
    row = _assignment(registry, device_id, assignment_id)
    if row["expires_at_ms"] <= registry.now_ms:
        raise RegistryError(410)
    if row["state"] not in LIVE_STATES:
        raise RegistryError(409)
    registry.db.execute(
        "UPDATE assignments SET state = 'FAILED', closed_at_ms = max(created_at_ms, ?) "
        "WHERE assignment_id = ?", (registry.now_ms, assignment_id),
    )
    _audit(registry, row, code)
    return {"assignment_id": assignment_id, "state": "FAILED"}
