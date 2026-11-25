"""Two-way device pairing for the controller.

A pair moves from OPEN to CLAIMED when another device presents the code, and
to ACTIVE only after both members confirm before the deadline. OPEN or CLAIMED
sessions expire at `expires_at_ms`. A rejection ends the session. Revocation of
ACTIVE pairs belongs to the job and consent layer.
"""

import hashlib
import hmac
import secrets
import sqlite3
from uuid import uuid4

from . import idempotency
from .common import (
    IDEMPOTENCY_CONFLICT,
    PAIR_CODE,
    PAIR_TTL_MS,
    UUID4,
    Reply,
    connection_state,
    error,
    immediate_transaction,
    payload_sha256,
    query_row,
    query_rows,
    secret_sha256,
    utc,
)
from .identity import Device

_PAIR_VIEW = (
    "SELECT p.pair_id, p.opener_device_id, p.claimant_device_id, p.comparison_code, "
    "p.opener_confirmed_at_ms, p.claimant_confirmed_at_ms, p.expires_at_ms, p.state, "
    "o.display_name AS opener_name, o.heartbeat_at_ms AS opener_heartbeat_at_ms, "
    "c.display_name AS claimant_name, c.heartbeat_at_ms AS claimant_heartbeat_at_ms "
    "FROM pairs p JOIN devices o ON o.device_id = p.opener_device_id "
    "LEFT JOIN devices c ON c.device_id = p.claimant_device_id "
)
_PENDING = ("OPEN", "CLAIMED")


def pair_code(key: bytes, pair_id: str) -> str:
    """Derive the 128-bit pairing code from a key kept outside SQLite.

    Replaying the same create request after a lost response returns the same
    code while SQLite stores only its hash.
    """
    digest = hmac.new(key, b"ratatoss-pair-code\x00" + pair_id.encode("ascii"), hashlib.sha256)
    return digest.hexdigest()[:32]


def active_pair_id(connection: sqlite3.Connection, device_a: str, device_b: str) -> str | None:
    """Return the ACTIVE pair joining two devices, in either order."""
    low, high = sorted((device_a, device_b))
    row = query_row(
        connection,
        "SELECT pair_id FROM pairs WHERE state = 'ACTIVE' AND device_low = ? AND device_high = ?",
        (low, high),
    )
    return None if row is None else row["pair_id"]


def active_peer_ids(connection: sqlite3.Connection, device_id: str) -> set[str]:
    """Return the devices that currently share an ACTIVE pair with `device_id`."""
    rows = query_rows(
        connection,
        "SELECT CASE WHEN opener_device_id = ? THEN claimant_device_id ELSE opener_device_id END "
        "AS peer FROM pairs WHERE state = 'ACTIVE' AND (opener_device_id = ? OR claimant_device_id = ?)",
        (device_id, device_id, device_id),
    )
    return {row["peer"] for row in rows}


def open_pair(connection: sqlite3.Connection, *, device: Device, request_key: str,
              now_ms: int, code_key: bytes) -> Reply:
    scope = idempotency.Scope(device.device_id, "POST", "/v1/pairs", request_key)
    digest = payload_sha256(None)
    with immediate_transaction(connection):
        try:
            stored = idempotency.find(connection, scope, digest)
        except idempotency.KeyReuseConflict:
            return error(409, IDEMPOTENCY_CONFLICT)
        if stored is not None:
            # Reveal the code again only while it is still the usable OPEN session.
            state = _expire_if_due(connection, stored.pair_id, now_ms)
            if state == "OPEN":
                return Reply(stored.status, stored.result | {"pair_code": pair_code(code_key, stored.pair_id)})
            return error(410) if state == "EXPIRED" else error(409)

        pair_id = str(uuid4())
        expires_at_ms = now_ms + PAIR_TTL_MS
        connection.execute(
            "INSERT INTO pairs (pair_id, opener_device_id, code_sha256, created_at_ms, "
            "expires_at_ms, state) VALUES (?, ?, ?, ?, ?, 'OPEN')",
            (pair_id, device.device_id, secret_sha256(pair_code(code_key, pair_id)), now_ms, expires_at_ms),
        )
        result = {"pair_id": pair_id, "expires_at": utc(expires_at_ms)}
        idempotency.record(connection, scope, digest, status=201, result=result,
                           pair_id=pair_id, now_ms=now_ms)
    return Reply(201, result | {"pair_code": pair_code(code_key, pair_id)})


def claim_pair(connection: sqlite3.Connection, *, device: Device, request_key: str,
               body: dict, now_ms: int) -> Reply:
    if body.keys() != {"pair_code"} or not isinstance(body["pair_code"], str) \
            or not PAIR_CODE.fullmatch(body["pair_code"]):
        return error(400)
    scope = idempotency.Scope(device.device_id, "POST", "/v1/pairs/claim", request_key)
    digest = payload_sha256(body)
    with immediate_transaction(connection):
        try:
            stored = idempotency.find(connection, scope, digest)
        except idempotency.KeyReuseConflict:
            return error(409, IDEMPOTENCY_CONFLICT)
        if stored is not None:
            return Reply(stored.status, stored.result)

        row = query_row(
            connection,
            "SELECT pair_id, opener_device_id FROM pairs WHERE code_sha256 = ?",
            (secret_sha256(body["pair_code"]),),
        )
        # Unknown, consumed and expired codes share one generic failure.
        if row is None or _expire_if_due(connection, row["pair_id"], now_ms) != "OPEN":
            return error(404)
        opener = row["opener_device_id"]
        if opener == device.device_id:
            return error(409, "A device cannot pair with itself.")
        if active_pair_id(connection, opener, device.device_id) is not None:
            return error(409, "These devices are already paired.")

        comparison_code = f"{secrets.randbelow(1_000_000):06d}"
        claimed = connection.execute(
            "UPDATE pairs SET claimant_device_id = ?, comparison_code = ?, state = 'CLAIMED' "
            "WHERE pair_id = ? AND state = 'OPEN'",
            (device.device_id, comparison_code, row["pair_id"]),
        )
        if claimed.rowcount != 1:
            raise RuntimeError("Pair changed under the write lock")
        result = {"pair_id": row["pair_id"]}
        idempotency.record(connection, scope, digest, status=200, result=result,
                           pair_id=row["pair_id"], now_ms=now_ms)
    return Reply(200, result)


def list_pairs(connection: sqlite3.Connection, *, device: Device, now_ms: int) -> Reply:
    rows = query_rows(
        connection,
        _PAIR_VIEW + "WHERE p.opener_device_id = ? OR p.claimant_device_id = ? "
        "ORDER BY p.created_at_ms, p.pair_id",
        (device.device_id, device.device_id),
    )
    return Reply(200, {"pairs": [_render(row, device.device_id, now_ms) for row in rows]})


def decide_pair(connection: sqlite3.Connection, *, device: Device, pair_id: str,
                request_key: str, body: dict, now_ms: int) -> Reply:
    if not UUID4.fullmatch(pair_id):
        return error(404)
    if body.keys() != {"decision"} or body["decision"] not in ("CONFIRM", "REJECT"):
        return error(400)
    scope = idempotency.Scope(device.device_id, "POST", f"/v1/pairs/{pair_id}/decision", request_key)
    digest = payload_sha256(body)
    with immediate_transaction(connection):
        try:
            stored = idempotency.find(connection, scope, digest)
        except idempotency.KeyReuseConflict:
            return error(409, IDEMPOTENCY_CONFLICT)
        if stored is not None:
            # Replays show the pair as the caller may see it now.
            return Reply(stored.status, _view(connection, pair_id, device.device_id, now_ms))

        row = query_row(
            connection,
            "SELECT opener_device_id, claimant_device_id, opener_confirmed_at_ms, "
            "claimant_confirmed_at_ms FROM pairs "
            "WHERE pair_id = ? AND (opener_device_id = ? OR claimant_device_id = ?)",
            (pair_id, device.device_id, device.device_id),
        )
        if row is None:
            return error(404)
        state = _expire_if_due(connection, pair_id, now_ms)
        if state == "EXPIRED":
            return error(410)
        if state != "CLAIMED":
            return error(409)

        if body["decision"] == "REJECT":
            connection.execute("UPDATE pairs SET state = 'DECLINED' WHERE pair_id = ?", (pair_id,))
        else:
            if row["opener_device_id"] == device.device_id:
                mine, theirs = "opener_confirmed_at_ms", "claimant_confirmed_at_ms"
            else:
                mine, theirs = "claimant_confirmed_at_ms", "opener_confirmed_at_ms"
            activate = row[theirs] is not None
            if activate and active_pair_id(connection, row["opener_device_id"], row["claimant_device_id"]):
                return error(409, "These devices are already paired.")
            # Column names come from the two constants above, never from input.
            connection.execute(
                f"UPDATE pairs SET {mine} = coalesce({mine}, ?), "
                "state = CASE WHEN ? THEN 'ACTIVE' ELSE state END WHERE pair_id = ?",
                (now_ms, activate, pair_id),
            )
        idempotency.record(connection, scope, digest, status=200, result={"pair_id": pair_id},
                           pair_id=pair_id, now_ms=now_ms)
        view = _view(connection, pair_id, device.device_id, now_ms)
    return Reply(200, view)


def _expire_if_due(connection: sqlite3.Connection, pair_id: str, now_ms: int) -> str:
    """Persist expiry for a pending session whose deadline has passed and return the state."""
    connection.execute(
        "UPDATE pairs SET state = 'EXPIRED' WHERE pair_id = ? AND state IN ('OPEN', 'CLAIMED') "
        "AND expires_at_ms <= ?",
        (pair_id, now_ms),
    )
    return query_row(connection, "SELECT state FROM pairs WHERE pair_id = ?", (pair_id,))["state"]


def _view(connection: sqlite3.Connection, pair_id: str, viewer: str, now_ms: int) -> dict:
    row = query_row(connection, _PAIR_VIEW + "WHERE p.pair_id = ?", (pair_id,))
    return _render(row, viewer, now_ms)


def _render(row: sqlite3.Row, viewer: str, now_ms: int) -> dict:
    state = row["state"]
    if state in _PENDING and now_ms >= row["expires_at_ms"]:
        state = "EXPIRED"
    view = {"pair_id": row["pair_id"], "expires_at": utc(row["expires_at_ms"])}
    if state not in ("OPEN", "CLAIMED", "ACTIVE"):
        return view | {"state": state}
    view["initiator"] = _participant(
        row["opener_device_id"], row["opener_name"], row["opener_heartbeat_at_ms"],
        row["opener_confirmed_at_ms"], now_ms,
    )
    if state == "OPEN":
        return view | {"state": state}
    view["claimant"] = _participant(
        row["claimant_device_id"], row["claimant_name"], row["claimant_heartbeat_at_ms"],
        row["claimant_confirmed_at_ms"], now_ms,
    )
    if state == "CLAIMED":
        return view | {"comparison_code": row["comparison_code"], "state": state}
    peer = row["claimant_device_id"] if viewer == row["opener_device_id"] else row["opener_device_id"]
    return view | {"peer_device_id": peer, "state": state}


def _participant(device_id: str, name: str, heartbeat_at_ms: int | None,
                 confirmed_at_ms: int | None, now_ms: int) -> dict:
    return {
        "display_name": name,
        "device_id_suffix": device_id[-6:],
        "connection": connection_state(heartbeat_at_ms, now_ms),
        "confirmed": confirmed_at_ms is not None,
    }
