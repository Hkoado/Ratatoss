"""Controller job, consent, and inventory state on an initialized SQLite DB.

Call mutations inside BEGIN IMMEDIATE with a clock sampled after acquiring the
lock. RegistryError represents a request error; the caller may commit the
maintenance transitions made before returning that error.
"""

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from ..manifest import Manifest
from ..offer_state import decide_offer, expire_offer

OFFER_TTL_MS = 24 * 60 * 60 * 1000
HEARTBEAT_TIMEOUT_MS = 20_000
SQLITE_MAX_INTEGER = 2**63 - 1


class RegistryError(Exception):
    def __init__(self, status: int, message: str | None = None):
        super().__init__(status)
        self.status = status
        self.message = message


def utc(ms: int) -> str:
    time = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)
    return time.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def online(device: sqlite3.Row, now_ms: int) -> bool:
    heartbeat = device["heartbeat_at_ms"]
    return device["revoked_at_ms"] is None and heartbeat is not None and (
        0 <= now_ms - heartbeat < HEARTBEAT_TIMEOUT_MS
    )


def is_uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def validate_job(payload: dict, *, max_targets: int) -> tuple[Manifest, list[str]]:
    try:
        if payload.keys() != {"manifest", "target_device_ids"}:
            raise ValueError("Invalid job fields")
        targets = payload["target_device_ids"]
        if (
            not isinstance(targets, list)
            or not 1 <= len(targets) <= max_targets
            or not all(is_uuid4(target) for target in targets)
            or len(set(targets)) != len(targets)
        ):
            raise ValueError("Invalid target devices")
        manifest = Manifest.from_dict(payload["manifest"])
        if manifest.size > SQLITE_MAX_INTEGER:
            raise ValueError("File size exceeds storage limit")
    except ValueError as exc:
        raise RegistryError(400) from exc
    return manifest, targets


class Registry:
    """Operations for an authenticated controller request at one DB timestamp."""

    def __init__(self, connection: sqlite3.Connection, now_ms: int):
        self.db = connection
        self.now_ms = now_ms

    def rows(self, sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        cursor = self.db.cursor()
        cursor.row_factory = sqlite3.Row
        return cursor.execute(sql, parameters).fetchall()

    def row(self, sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
        cursor = self.db.cursor()
        cursor.row_factory = sqlite3.Row
        return cursor.execute(sql, parameters).fetchone()

    def create_job(self, source_id: str, manifest: Manifest, targets: list[str],
                   active_pair_id: Callable[[sqlite3.Connection, str, str], str | None]) -> dict:
        """Resolve every target using the identity module under the write lock."""
        if not targets or len(set(targets)) != len(targets) or source_id in targets:
            raise RegistryError(400)

        pairs = []
        for target_id in targets:
            pair_id = active_pair_id(self.db, source_id, target_id)
            target = self.row("SELECT revoked_at_ms FROM devices WHERE device_id = ?", (target_id,))
            if pair_id is None or target is None or target["revoked_at_ms"] is not None:
                raise RegistryError(404)
            pairs.append(pair_id)

        canonical = manifest.canonical_bytes()
        digest = sha256(canonical).digest()
        job_id = str(uuid4())
        self.db.execute(
            "INSERT INTO jobs (job_id, source_device_id, manifest_canonical, manifest_sha256, "
            "file_sha256, size_bytes, created_at_ms, state) VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')",
            (job_id, source_id, canonical, digest, bytes.fromhex(manifest.sha256),
             manifest.size, self.now_ms),
        )
        self.db.executemany(
            "INSERT INTO job_batches VALUES (?, ?, ?, ?, ?)",
            ((job_id, batch.index, batch.offset, batch.size, bytes.fromhex(batch.sha256))
             for batch in manifest.batches),
        )
        self.db.executemany(
            "INSERT INTO job_members (job_id, device_id) VALUES (?, ?)",
            ((job_id, device_id) for device_id in (source_id, *targets)),
        )
        expires = self.now_ms + OFFER_TTL_MS
        offers = []
        for target_id, pair_id in zip(targets, pairs, strict=True):
            offer_id = str(uuid4())
            self.db.execute(
                "INSERT INTO offers (offer_id, job_id, target_device_id, pair_id, expires_at_ms, state) "
                "VALUES (?, ?, ?, ?, ?, 'PENDING')",
                (offer_id, job_id, target_id, pair_id, expires),
            )
            offers.append({"offer_id": offer_id, "target_device_id": target_id,
                           "expires_at": utc(expires), "state": "PENDING"})
        return {"job_id": job_id, "manifest_sha256": digest.hex(),
                "created_at": utc(self.now_ms), "offers": offers}

    def _offers(self, device_id: str, offer_id: str | None = None) -> list[sqlite3.Row]:
        return self.rows(
            "SELECT o.*, j.source_device_id, j.manifest_canonical, j.manifest_sha256, "
            "j.file_sha256, j.size_bytes, d.display_name AS source_display_name "
            "FROM offers o JOIN jobs j USING (job_id) "
            "JOIN devices d ON d.device_id = j.source_device_id "
            "WHERE o.target_device_id = ? AND (? IS NULL OR o.offer_id = ?) ORDER BY o.rowid",
            (device_id, offer_id, offer_id),
        )

    def _offer(self, device_id: str, offer_id: str) -> sqlite3.Row:
        rows = self._offers(device_id, offer_id)
        if not rows:
            raise RegistryError(404)
        return rows[0]

    def _offer_view(self, offer: sqlite3.Row, *, detail: bool = False) -> dict:
        manifest = json.loads(offer["manifest_canonical"])
        expiry = expire_offer(
            state=offer["state"], expires_at_ms=offer["expires_at_ms"], now_ms=self.now_ms,
        )
        result = {
            "offer_id": offer["offer_id"], "job_id": offer["job_id"],
            "source_device_id": offer["source_device_id"],
            "source_display_name": offer["source_display_name"],
            "file_name": manifest["name"], "size": offer["size_bytes"],
            "expires_at": utc(offer["expires_at_ms"]),
            "state": expiry.state if expiry else offer["state"],
        }
        if detail:
            result.update(manifest=manifest, manifest_sha256=offer["manifest_sha256"].hex())
        return result

    def list_offers(self, device_id: str) -> dict:
        return {"offers": [self._offer_view(offer) for offer in self._offers(device_id)]}

    def get_offer(self, device_id: str, offer_id: str) -> dict:
        return self._offer_view(self._offer(device_id, offer_id), detail=True)

    def offer_decision(self, device_id: str, offer_id: str, payload: dict) -> dict:
        offer = self._offer(device_id, offer_id)
        decision = payload.get("decision")
        expected = {"decision", "manifest_sha256", "allow_forward"} if decision == "ACCEPT" else {
            "decision"
        }
        if payload.keys() != expected:
            raise RegistryError(400)
        result = decide_offer(
            state=offer["state"], expires_at_ms=offer["expires_at_ms"], now_ms=self.now_ms,
            expected_manifest_sha256=offer["manifest_sha256"].hex(), decision=decision,
            manifest_sha256=payload.get("manifest_sha256"), allow_forward=payload.get("allow_forward"),
        )
        transition = result.transition
        if transition is not None:
            self.db.execute(
                "UPDATE offers SET state = ?, accepted_at_ms = ?, allow_forward = ? WHERE offer_id = ?",
                (transition.state, transition.accepted_at_ms, transition.allow_forward, offer_id),
            )
            self.close_finished_job(offer["job_id"])
        if result.error_code:
            raise RegistryError({"INVALID_REQUEST": 400, "STATE_CONFLICT": 409,
                                 "EXPIRED": 410}[result.error_code])
        return {"offer_id": offer_id, "state": transition.state}

    def withdraw_offer(self, device_id: str, offer_id: str) -> dict:
        offer = self._offer(device_id, offer_id)
        if offer["state"] != "ACCEPTED":
            raise RegistryError(409)
        self.db.execute("UPDATE offers SET state = 'WITHDRAWN' WHERE offer_id = ?", (offer_id,))
        self.cancel_assignments(job_id=offer["job_id"], device_id=device_id)
        self.close_finished_job(offer["job_id"])
        return {"offer_id": offer_id, "state": "WITHDRAWN"}

    def revoke_pair(self, device_id: str, pair_id: str) -> dict:
        pair = self.row(
            "SELECT state FROM pairs WHERE pair_id = ? "
            "AND (opener_device_id = ? OR claimant_device_id = ?)",
            (pair_id, device_id, device_id),
        )
        if pair is None:
            raise RegistryError(404)
        if pair["state"] != "ACTIVE":
            raise RegistryError(409)
        self.db.execute("UPDATE pairs SET state = 'REVOKED' WHERE pair_id = ?", (pair_id,))
        self.expire_offers(pair_id=pair_id)
        changed = self.db.execute(
            "UPDATE offers SET state = 'REVOKED' WHERE pair_id = ? AND state = 'PENDING' "
            "RETURNING job_id", (pair_id,),
        ).fetchall()
        for (job_id,) in set(map(tuple, changed)):
            self.close_finished_job(job_id)
        return {"pair_id": pair_id, "state": "REVOKED"}

    def cancel_job(self, device_id: str, job_id: str) -> dict:
        job = self.row("SELECT * FROM jobs WHERE job_id = ? AND source_device_id = ?",
                       (job_id, device_id))
        if job is None:
            raise RegistryError(404)
        self.expire_offers(job_id)
        if self.row("SELECT state FROM jobs WHERE job_id = ?", (job_id,))["state"] != "OPEN":
            raise RegistryError(409)
        self.db.execute(
            "UPDATE offers SET state = CASE state WHEN 'PENDING' THEN 'REVOKED' ELSE 'CANCELED' END "
            "WHERE job_id = ? AND state IN ('PENDING', 'ACCEPTED')", (job_id,),
        )
        self.db.execute("UPDATE jobs SET state = 'CANCELED', closed_at_ms = max(created_at_ms, ?) WHERE job_id = ?",
                        (self.now_ms, job_id))
        self.cancel_assignments(job_id=job_id)
        return self.job_status(device_id, job_id)

    def expire_offers(self, job_id: str | None = None, *, pair_id: str | None = None) -> None:
        pending = self.rows(
            "SELECT offer_id, state, expires_at_ms, job_id FROM offers "
            "WHERE state = 'PENDING' AND expires_at_ms <= ? "
            "AND (? IS NULL OR job_id = ?) AND (? IS NULL OR pair_id = ?)",
            (self.now_ms, job_id, job_id, pair_id, pair_id),
        )
        jobs = set()
        for item in pending:
            transition = expire_offer(state=item["state"], expires_at_ms=item["expires_at_ms"],
                                      now_ms=self.now_ms)
            if transition:
                self.db.execute("UPDATE offers SET state = ? WHERE offer_id = ?",
                                (transition.state, item["offer_id"]))
                jobs.add(item["job_id"])
        for affected in jobs:
            self.close_finished_job(affected)

    def cancel_assignments(self, *, job_id: str | None = None, device_id: str | None = None) -> None:
        if job_id is None and device_id is None:
            raise ValueError("Specify a job or device to cancel")
        self.db.execute(
            "UPDATE assignments SET state = 'CANCELED', closed_at_ms = max(created_at_ms, ?) "
            "WHERE state IN ('OFFERED', 'RUNNING') AND (? IS NULL OR job_id = ?) "
            "AND (? IS NULL OR source_device_id = ? OR target_device_id = ?)",
            (self.now_ms, job_id, job_id, device_id, device_id, device_id),
        )

    def close_finished_job(self, job_id: str) -> None:
        count = self.row(
            "SELECT count(*) AS targets, count(*) FILTER (WHERE state = 'VERIFIED') AS verified, "
            "count(*) FILTER (WHERE state IN ('PENDING', 'ACCEPTED')) AS remaining "
            "FROM offers WHERE job_id = ?", (job_id,),
        )
        if not count["targets"] or count["remaining"]:
            return
        if count["verified"] == count["targets"]:
            state = "COMPLETE"
        elif count["verified"]:
            state = "PARTIAL"
        else:
            state = "NO_DELIVERY"
        updated = self.db.execute(
            "UPDATE jobs SET state = ?, closed_at_ms = max(created_at_ms, ?) "
            "WHERE job_id = ? AND state = 'OPEN'", (state, self.now_ms, job_id),
        )
        if updated.rowcount:
            self.cancel_assignments(job_id=job_id)

    def job_status(self, device_id: str, job_id: str) -> dict:
        job = self.row("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if job is None:
            raise RegistryError(404)
        source_view = job["source_device_id"] == device_id
        targets = self.rows(
            "SELECT o.*, d.display_name, d.heartbeat_at_ms, d.revoked_at_ms, r.verified_at_ms, "
            "coalesce((SELECT sum(b.size_bytes) FROM inventory i JOIN job_batches b "
            "USING (job_id, batch_id) WHERE i.job_id = o.job_id "
            "AND i.device_id = o.target_device_id), 0) AS verified_bytes "
            "FROM offers o JOIN devices d ON d.device_id = o.target_device_id "
            "LEFT JOIN receipts r USING (job_id, target_device_id) "
            "WHERE o.job_id = ? AND (? OR o.target_device_id = ?) ORDER BY o.rowid",
            (job_id, source_view, device_id),
        )
        if not targets:
            raise RegistryError(404)
        result = {
            "job_id": job_id, "source_device_id": job["source_device_id"],
            "manifest_sha256": job["manifest_sha256"].hex(), "size": job["size_bytes"],
            "file_name": json.loads(job["manifest_canonical"])["name"], "state": job["state"],
        }
        views = [{
            "offer_id": target["offer_id"], "device_id": target["target_device_id"],
            "display_name": target["display_name"], "state": target["state"],
            "connection": "ONLINE" if online(target, self.now_ms) else "OFFLINE",
            "verified_bytes": target["verified_bytes"],
            "receipt": self._receipt(job, target) if target["verified_at_ms"] is not None else None,
        } for target in targets]
        if source_view:
            return dict(result, view="SOURCE", targets=views)
        return dict(result, view="TARGET", target=views[0])

    @staticmethod
    def _receipt(job: sqlite3.Row, target: sqlite3.Row | Mapping) -> dict:
        return {
            "job_id": job["job_id"], "target_device_id": target["target_device_id"],
            "manifest_sha256": job["manifest_sha256"].hex(), "file_sha256": job["file_sha256"].hex(),
            "size": job["size_bytes"], "verified_at": utc(target["verified_at_ms"]),
        }

    def receipt(self, device_id: str, job_id: str, payload: dict) -> dict:
        offer = self.row(
            "SELECT o.*, j.manifest_sha256, j.file_sha256, j.size_bytes, r.verified_at_ms, "
            "m.reconciled_epoch, d.connection_epoch, d.heartbeat_at_ms, d.revoked_at_ms "
            "FROM offers o JOIN jobs j USING (job_id) "
            "JOIN job_members m ON m.job_id = o.job_id AND m.device_id = o.target_device_id "
            "JOIN devices d ON d.device_id = o.target_device_id "
            "LEFT JOIN receipts r USING (job_id, target_device_id) "
            "WHERE o.job_id = ? AND o.target_device_id = ?", (job_id, device_id),
        )
        if offer is None:
            raise RegistryError(404)
        if (payload["manifest_sha256"], payload["file_sha256"], payload["size"]) != (
            offer["manifest_sha256"].hex(), offer["file_sha256"].hex(), offer["size_bytes"]
        ):
            raise RegistryError(409)
        if offer["verified_at_ms"] is not None:
            return self._receipt(offer, offer)
        if (
            offer["state"] != "ACCEPTED" or not online(offer, self.now_ms)
            or offer["reconciled_epoch"] != offer["connection_epoch"]
            or self.row(
                "SELECT 1 FROM job_batches b WHERE b.job_id = ? AND NOT EXISTS "
                "(SELECT 1 FROM inventory i WHERE i.job_id = b.job_id AND i.batch_id = b.batch_id "
                "AND i.device_id = ?) LIMIT 1", (job_id, device_id),
            )
        ):
            raise RegistryError(409)
        self.db.execute("INSERT INTO receipts VALUES (?, ?, ?)", (job_id, device_id, self.now_ms))
        self.db.execute("UPDATE offers SET state = 'VERIFIED' WHERE offer_id = ?", (offer["offer_id"],))
        self.close_finished_job(job_id)
        return self._receipt(offer, dict(offer, verified_at_ms=self.now_ms))
