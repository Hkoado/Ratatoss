"""HTTP routes for job, consent, and lease operations under /v1."""

import asyncio
import logging
import re
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..manifest import decode_manifest_object
from . import connections, leases
from .registry import SQLITE_MAX_INTEGER, Registry, RegistryError, is_uuid4, validate_job
from .request_log import RequestKey
from .runtime import ControllerRuntime

Identify = Callable[[sqlite3.Connection, list[str]], str | None]
ActivePairId = Callable[[sqlite3.Connection, str, str], str | None]
Operation = Callable[[Registry, str, dict | None, bool], dict]
DIGEST = re.compile(r"[0-9a-f]{64}")
LOGGER = logging.getLogger(__name__)

_ERRORS = {
    400: ("INVALID_REQUEST", "Invalid request."),
    401: ("UNAUTHENTICATED", "Valid device credential required."),
    404: ("NOT_FOUND", "Resource unavailable."),
    409: ("STATE_CONFLICT", "Request conflicts with the current state."),
    410: ("EXPIRED", "Offer or lease has expired."),
}


def _response(status: int, body: dict) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def _error(error: RegistryError) -> tuple[int, dict]:
    code, default = _ERRORS[error.status]
    return error.status, {"error": {"code": code, "message": error.message or default}}


async def _payload(request: Request, *, expected: bool, limit: int) -> dict | None:
    content_types = request.headers.getlist("content-type")
    if expected and (
        len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
    ):
        raise RegistryError(400)
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > (limit if expected else 0):
            raise RegistryError(400)
        raw.extend(chunk)
    if not expected:
        return None
    try:
        body = decode_manifest_object(bytes(raw))
        # A body can contain a lone surrogate via a JSON escape. Reject it before
        # fields or request digests can reach SQLite.
        _valid_unicode(body)
    except (ValueError, RecursionError) as exc:
        raise RegistryError(400) from exc
    return body


def _valid_unicode(value) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8")
            _valid_unicode(item)
    elif isinstance(value, list):
        for item in value:
            _valid_unicode(item)


def _keys(body: dict, *fields: str) -> None:
    if body.keys() != set(fields):
        raise RegistryError(400)


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= SQLITE_MAX_INTEGER:
        raise RegistryError(400)
    return value


def _unique_list(value: object, valid: Callable[[object], bool]) -> list:
    if not isinstance(value, list) or not all(valid(item) for item in value) or len(set(value)) != len(value):
        raise RegistryError(400)
    return value


def _uuid(value: object) -> str:
    if not is_uuid4(value):
        raise RegistryError(400)
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise RegistryError(400)
    return value


def create_control_app(runtime: ControllerRuntime, *, identify: Identify,
                       active_pair_id: ActivePairId, tick_seconds: float = 1) -> FastAPI:
    """Start one controller runtime and drive periodic assignment maintenance."""
    if tick_seconds <= 0:
        raise ValueError("Scheduler interval must be positive")

    @asynccontextmanager
    async def lifespan(_app):
        await run_in_threadpool(runtime.startup)
        stopped = asyncio.Event()

        async def schedule():
            while True:
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=tick_seconds)
                except TimeoutError:
                    try:
                        await run_in_threadpool(runtime.tick)
                    except sqlite3.OperationalError:
                        LOGGER.warning("Controller scheduler could not update SQLite. Retrying on the next tick.")
                else:
                    return

        task = asyncio.create_task(schedule())
        try:
            yield
        finally:
            stopped.set()
            await task

    app = FastAPI(lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None)
    app.include_router(create_control_router(runtime, identify=identify, active_pair_id=active_pair_id))
    return app


def create_control_router(runtime: ControllerRuntime, *, identify: Identify,
                          active_pair_id: ActivePairId) -> APIRouter:
    """Build the control routes. The mounted app supplies identity lookup."""
    router = APIRouter(prefix="/v1")

    async def run(request: Request, operation: Operation, *, resource_id: str | None = None,
                  json_body: bool = False, durable: bool = False, recheck_on_replay: bool = False,
                  status: int = 200, resource: str | None = None, refresh: bool = False):
        headers = request.headers.getlist("authorization")
        keys = request.headers.getlist("idempotency-key")
        method, route = request.method, request.url.path
        payload, parse_error = None, None
        if method != "GET":
            try:
                payload = await _payload(request, expected=json_body, limit=runtime.config.max_manifest_bytes)
            except RegistryError as exc:
                parse_error = exc

        def work() -> tuple[int, dict]:
            # Identify under the same lock used to authorize and record mutations.
            with runtime.transaction(write=method != "GET" or refresh) as registry:
                try:
                    device_id = identify(registry.db, headers)
                    if device_id is None:
                        raise RegistryError(401)
                    if resource_id is not None and not is_uuid4(resource_id):
                        raise RegistryError(404)
                    if parse_error is not None:
                        raise parse_error
                    if durable and (len(keys) != 1 or not is_uuid4(keys[0])):
                        raise RegistryError(400)

                    key = None
                    if durable:
                        try:
                            key = RequestKey.for_payload(device_id, method, route, keys[0], payload)
                        except ValueError as exc:
                            raise RegistryError(400) from exc
                    previous = key.find(registry) if key is not None else None
                    if previous is not None and not recheck_on_replay:
                        return previous
                    result = operation(registry, device_id, payload, previous is not None)
                    if key is not None and previous is None:
                        if resource == "offer":
                            scope = registry.row("SELECT job_id FROM offers WHERE offer_id = ?", (resource_id,))
                        elif resource == "assignment":
                            scope = registry.row("SELECT job_id FROM assignments WHERE assignment_id = ?",
                                                 (resource_id,))
                        else:
                            scope = result
                        job_id = scope["job_id"] if "job_id" in scope.keys() else None
                        key.record(registry, status, result, job_id=job_id, pair_id=result.get("pair_id"))
                    return status, result
                except RegistryError as exc:
                    return _error(exc)

        return _response(*(await run_in_threadpool(work)))

    @router.delete("/pairs/{pair_id}")
    async def revoke_pair(pair_id: str, request: Request):
        return await run(request, lambda r, d, _, _replay: r.revoke_pair(d, pair_id),
                         resource_id=pair_id, durable=True)

    @router.post("/jobs")
    async def create_job(request: Request):
        def apply(registry, device_id, body, _replay):
            manifest, targets = validate_job(body, max_targets=runtime.config.max_targets)
            return registry.create_job(device_id, manifest, targets, active_pair_id)
        return await run(request, apply, json_body=True, durable=True, status=201)

    @router.get("/offers")
    async def list_offers(request: Request):
        return await run(request, lambda r, d, _, _replay: r.list_offers(d))

    @router.get("/offers/{offer_id}")
    async def get_offer(offer_id: str, request: Request):
        return await run(request, lambda r, d, _, _replay: r.get_offer(d, offer_id), resource_id=offer_id)

    @router.post("/offers/{offer_id}/decision")
    async def decide_offer(offer_id: str, request: Request):
        return await run(request, lambda r, d, body, _: r.offer_decision(d, offer_id, body),
                         resource_id=offer_id, json_body=True, durable=True, resource="offer")

    @router.post("/offers/{offer_id}/withdraw")
    async def withdraw_offer(offer_id: str, request: Request):
        return await run(request, lambda r, d, _, _replay: r.withdraw_offer(d, offer_id),
                         resource_id=offer_id, durable=True, resource="offer")

    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, request: Request):
        return await run(request, lambda r, d, _, _replay: r.cancel_job(d, job_id),
                         resource_id=job_id, durable=True)

    @router.get("/jobs/{job_id}/status")
    async def job_status(job_id: str, request: Request):
        return await run(request, lambda r, d, _, _replay: r.job_status(d, job_id), resource_id=job_id)

    @router.post("/devices/me/heartbeat")
    async def heartbeat(request: Request):
        def apply(registry, device_id, body, _replay):
            _keys(body, "boot_id", "free_rx_slots", "free_tx_slots", "active_assignment_ids")
            return connections.heartbeat(
                registry, device_id, _uuid(body["boot_id"]), _count(body["free_rx_slots"]),
                _count(body["free_tx_slots"]), _unique_list(body["active_assignment_ids"], is_uuid4),
            )
        return await run(request, apply, json_body=True)

    @router.post("/jobs/{job_id}/reconcile")
    async def reconcile(job_id: str, request: Request):
        def apply(registry, device_id, body, replay):
            _keys(body, "boot_id", "verified_batch_ids")
            return connections.reconcile(
                registry, device_id, job_id, _uuid(body["boot_id"]),
                _unique_list(body["verified_batch_ids"],
                             lambda value: type(value) is int and 0 <= value <= SQLITE_MAX_INTEGER),
                replay=replay,
            )
        return await run(request, apply, resource_id=job_id, json_body=True, durable=True,
                         recheck_on_replay=True)

    @router.get("/devices/me/assignments")
    async def list_assignments(request: Request):
        return await run(request, lambda r, d, _, _replay: leases.list_assignments(r, d, runtime.codes),
                         refresh=True)

    @router.post("/assignments/{assignment_id}/ready")
    async def ready(assignment_id: str, request: Request):
        return await run(
            request, lambda r, d, _, replay: leases.ready(
                r, d, assignment_id, runtime.codes, runtime.config.lease_profiles, replay=replay,
            ),
            resource_id=assignment_id, durable=True, recheck_on_replay=True, resource="assignment",
        )

    @router.post("/assignments/{assignment_id}/ack")
    async def ack(assignment_id: str, request: Request):
        def apply(registry, device_id, body, _replay):
            _keys(body, "batch_sha256")
            return leases.ack(registry, device_id, assignment_id, _digest(body["batch_sha256"]))
        return await run(request, apply, resource_id=assignment_id, json_body=True, durable=True,
                         recheck_on_replay=True, resource="assignment")

    @router.post("/assignments/{assignment_id}/fail")
    async def fail(assignment_id: str, request: Request):
        def apply(registry, device_id, body, _replay):
            _keys(body, "code")
            if body["code"] not in ("NO_SLOT", "NO_SPACE", "TRANSPORT_TIMEOUT", "CORRUPT"):
                raise RegistryError(400)
            return leases.fail(registry, device_id, assignment_id, body["code"])
        return await run(request, apply, resource_id=assignment_id, json_body=True, durable=True,
                         resource="assignment")

    @router.post("/jobs/{job_id}/receipt")
    async def receipt(job_id: str, request: Request):
        def apply(registry, device_id, body, _replay):
            _keys(body, "manifest_sha256", "file_sha256", "size")
            _digest(body["manifest_sha256"])
            _digest(body["file_sha256"])
            _count(body["size"])
            return registry.receipt(device_id, job_id, body)
        return await run(request, apply, resource_id=job_id, json_body=True, durable=True)

    return router
