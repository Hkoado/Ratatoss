"""Idempotency records scoped to device, method, concrete route and key."""

import json
import sqlite3
from dataclasses import dataclass

from .common import query_row


@dataclass(frozen=True)
class Scope:
    device_id: str
    method: str
    route: str
    request_key: str


@dataclass(frozen=True)
class Stored:
    status: int
    result: dict
    pair_id: str | None


class KeyReuseConflict(Exception):
    """The key was already used with a different payload."""


def find(connection: sqlite3.Connection, scope: Scope, payload_sha256: bytes) -> Stored | None:
    """Return the committed result for this key, or None when the key is new."""
    row = query_row(
        connection,
        "SELECT payload_sha256, status_code, result_json, pair_id FROM idempotency "
        "WHERE device_id = ? AND method = ? AND route = ? AND request_key = ?",
        (scope.device_id, scope.method, scope.route, scope.request_key),
    )
    if row is None:
        return None
    if row["payload_sha256"] != payload_sha256:
        raise KeyReuseConflict
    return Stored(row["status_code"], json.loads(row["result_json"]), row["pair_id"])


def record(connection: sqlite3.Connection, scope: Scope, payload_sha256: bytes, *,
           status: int, result: dict, pair_id: str | None, now_ms: int) -> None:
    """Store a filtered result in the caller's write transaction. Never store secrets."""
    connection.execute(
        "INSERT INTO idempotency (device_id, method, route, request_key, payload_sha256, "
        "pair_id, status_code, result_json, created_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (scope.device_id, scope.method, scope.route, scope.request_key, payload_sha256,
         pair_id, status, json.dumps(result, separators=(",", ":")), now_ms),
    )
