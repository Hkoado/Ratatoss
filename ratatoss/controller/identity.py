"""Device enrollment and bearer-token authentication for the controller."""

import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

from .common import (
    DEVICE_TOKEN,
    ENROLLMENT_TTL_MS,
    Reply,
    error,
    immediate_transaction,
    query_row,
    secret_sha256,
)


@dataclass(frozen=True)
class Device:
    """An enrolled device whose token was valid when it was authenticated."""

    device_id: str
    display_name: str
    # Hash of the presented token, so a write can recheck that exact token.
    token_sha256: bytes = field(repr=False, compare=False)


def issue_enrollment_code(connection: sqlite3.Connection, *, now_ms: int,
                          ttl_ms: int = ENROLLMENT_TTL_MS) -> str:
    """Create a one-time 256-bit code for an administrator to share out of band."""
    if ttl_ms <= 0:
        raise ValueError("Enrollment TTL must be positive")
    code = secrets.token_hex(32)
    with immediate_transaction(connection):
        connection.execute(
            "INSERT INTO enrollments (code_sha256, issued_at_ms, expires_at_ms) VALUES (?, ?, ?)",
            (secret_sha256(code), now_ms, now_ms + ttl_ms),
        )
    return code


def enroll_device(connection: sqlite3.Connection, *, enrollment_code: str,
                  display_name: str, clock: Callable[[], int]) -> Reply:
    """Consume an unexpired code and create the device in one transaction."""
    code_sha256 = secret_sha256(enrollment_code)
    with immediate_transaction(connection, clock) as now_ms:
        usable = query_row(
            connection,
            "SELECT 1 FROM enrollments WHERE code_sha256 = ? AND consumed_at_ms IS NULL "
            "AND issued_at_ms <= ? AND ? < expires_at_ms",
            (code_sha256, now_ms, now_ms),
        )
        if usable is None:
            return error(404)
        device_id = str(uuid4())
        token = secrets.token_hex(32)
        connection.execute(
            "INSERT INTO devices (device_id, display_name, token_sha256, enrolled_at_ms) "
            "VALUES (?, ?, ?, ?)",
            (device_id, display_name, secret_sha256(token), now_ms),
        )
        consumed = connection.execute(
            "UPDATE enrollments SET consumed_at_ms = ?, device_id = ? "
            "WHERE code_sha256 = ? AND consumed_at_ms IS NULL",
            (now_ms, device_id, code_sha256),
        )
        if consumed.rowcount != 1:
            raise RuntimeError("Enrollment code was consumed concurrently")
    return Reply(201, {"device_id": device_id, "display_name": display_name, "device_token": token})


def authenticate(connection: sqlite3.Connection, authorization: list[str]) -> Device | None:
    """Return the caller for exactly one valid `Authorization: Bearer <token>` header."""
    if len(authorization) != 1:
        return None
    scheme, _, token = authorization[0].partition(" ")
    if scheme.lower() != "bearer" or not DEVICE_TOKEN.fullmatch(token):
        return None
    token_sha256 = secret_sha256(token)
    row = query_row(
        connection,
        "SELECT device_id, display_name FROM devices "
        "WHERE token_sha256 = ? AND revoked_at_ms IS NULL",
        (token_sha256,),
    )
    return None if row is None else Device(row["device_id"], row["display_name"], token_sha256)


def still_valid(connection: sqlite3.Connection, device: Device) -> bool:
    """Recheck the caller's token inside the current write transaction.

    Call this right after `BEGIN IMMEDIATE`, before idempotency lookups or
    writes. A token revoked while the request waited for the lock then
    authorizes neither a new write nor a replay.
    """
    return query_row(
        connection,
        "SELECT 1 FROM devices WHERE device_id = ? AND token_sha256 = ? AND revoked_at_ms IS NULL",
        (device.device_id, device.token_sha256),
    ) is not None
