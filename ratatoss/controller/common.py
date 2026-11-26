"""Shared helpers for the controller identity and pairing modules."""

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from ..manifest import decode_manifest_object

ENROLLMENT_CODE = re.compile(r"[0-9a-f]{64}")
DEVICE_TOKEN = re.compile(r"[0-9a-f]{64}")
PAIR_CODE = re.compile(r"[0-9a-f]{32}")
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")

ENROLLMENT_TTL_MS = 10 * 60 * 1000
PAIR_TTL_MS = 10 * 60 * 1000
HEARTBEAT_TIMEOUT_MS = 20 * 1000

_ERRORS = {
    400: ("INVALID_REQUEST", "Invalid request."),
    401: ("UNAUTHENTICATED", "Valid device credential required."),
    404: ("NOT_FOUND", "Resource or code unavailable."),
    409: ("STATE_CONFLICT", "Request conflicts with the current state."),
    410: ("EXPIRED", "Pairing session has expired."),
    429: ("RATE_LIMITED", "Too many requests."),
}
IDEMPOTENCY_CONFLICT = "Idempotency key was already used with a different payload."


@dataclass(frozen=True)
class Reply:
    """HTTP status and JSON body produced by a controller operation."""

    status: int
    body: dict
    retry_after: int | None = None


def error(status: int, message: str | None = None, *, retry_after: int | None = None) -> Reply:
    code, default = _ERRORS[status]
    return Reply(status, {"error": {"code": code, "message": message or default}}, retry_after)


def secret_sha256(value: str) -> bytes:
    """Hash a lowercase hex secret. Raw secrets never reach SQLite."""
    return hashlib.sha256(value.encode("ascii")).digest()


def utc(ms: int) -> str:
    seconds, milliseconds = divmod(ms, 1000)
    stamp = datetime.fromtimestamp(seconds, timezone.utc).replace(microsecond=milliseconds * 1000)
    return stamp.isoformat(timespec="milliseconds" if milliseconds else "seconds").replace("+00:00", "Z")


def connection_state(heartbeat_at_ms: int | None, now_ms: int) -> str:
    if heartbeat_at_ms is not None and 0 <= now_ms - heartbeat_at_ms < HEARTBEAT_TIMEOUT_MS:
        return "ONLINE"
    return "OFFLINE"


def decode_body(raw: bytes) -> dict:
    """Decode a JSON object, rejecting duplicate keys and invalid Unicode."""
    body = decode_manifest_object(raw)
    _require_valid_text(body)
    return body


def payload_sha256(body: dict | None) -> bytes:
    """Digest a validated payload for idempotency. A missing body hashes as empty."""
    if body is None:
        return hashlib.sha256(b"").digest()
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).digest()


@contextmanager
def immediate_transaction(connection: sqlite3.Connection,
                          clock: Callable[[], int] | None = None) -> Iterator[int | None]:
    """Hold the SQLite write lock so checks and writes see the same state.

    With `clock`, yield the time read after the lock is held. A request that
    waited for the lock is then judged against TTLs at the moment it runs.
    """
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield None if clock is None else clock()
    except BaseException:
        connection.rollback()
        raise
    connection.commit()


def query_row(connection: sqlite3.Connection, sql: str, parameters=()) -> sqlite3.Row | None:
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, parameters).fetchone()


def query_rows(connection: sqlite3.Connection, sql: str, parameters=()) -> list[sqlite3.Row]:
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, parameters).fetchall()


def _require_valid_text(value) -> None:
    # json.loads accepts lone surrogate escapes such as "\ud800".
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8")
            _require_valid_text(item)
    elif isinstance(value, list):
        for item in value:
            _require_valid_text(item)
