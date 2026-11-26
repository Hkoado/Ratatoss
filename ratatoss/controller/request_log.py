"""Persist the result of a job-scoped mutation inside its write transaction."""

import json
from dataclasses import dataclass
from hashlib import sha256

from .registry import Registry, RegistryError


@dataclass(frozen=True)
class RequestKey:
    device_id: str
    method: str
    route: str
    key: str
    digest: bytes

    @classmethod
    def for_payload(cls, device_id: str, method: str, route: str, key: str,
                    payload: dict | None) -> "RequestKey":
        canonical = b"" if payload is None else json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
        return cls(device_id, method, route, key, sha256(canonical).digest())

    def find(self, registry: Registry) -> tuple[int, dict] | None:
        record = registry.row(
            "SELECT payload_sha256, status_code, result_json FROM idempotency "
            "WHERE device_id = ? AND method = ? AND route = ? AND request_key = ?",
            (self.device_id, self.method, self.route, self.key),
        )
        if record is None:
            return None
        if record["payload_sha256"] != self.digest:
            raise RegistryError(409, "Idempotency key was already used with a different payload.")
        return record["status_code"], json.loads(record["result_json"])

    def record(self, registry: Registry, status: int, result: dict, *,
               job_id: str | None = None, pair_id: str | None = None) -> None:
        safe_result = {field: value for field, value in result.items() if field != "croc_code"}
        registry.db.execute(
            "INSERT INTO idempotency (device_id, method, route, request_key, payload_sha256, "
            "job_id, pair_id, status_code, result_json, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self.device_id, self.method, self.route, self.key, self.digest, job_id, pair_id,
             status, json.dumps(safe_result, separators=(",", ":")), registry.now_ms),
        )
