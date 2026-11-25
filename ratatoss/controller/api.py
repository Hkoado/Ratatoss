"""HTTP routes for controller enrollment and pairing under `/v1`.

`create_router` returns a self-contained FastAPI router. The application that
mounts it owns process bootstrap, TLS and the remaining controller routes.
"""

import sqlite3
import time
from collections.abc import Callable
from contextlib import closing

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import identity, pairing
from .common import ENROLLMENT_CODE, UUID4, Reply, decode_body, error
from .identity import Device
from .ratelimit import RateLimiter

Connect = Callable[[], sqlite3.Connection]
MIN_PAIR_CODE_KEY_BYTES = 32


def wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def create_router(*, connect: Connect, pair_code_key: bytes,
                  clock: Callable[[], int] = wall_clock_ms,
                  enroll_limiter: RateLimiter | None = None,
                  claim_limiter: RateLimiter | None = None) -> APIRouter:
    """Build the enrollment and pairing routes.

    `connect` returns a new controller SQLite connection that the route closes.
    `pair_code_key` stays outside SQLite and must remain stable across restarts.
    """
    if len(pair_code_key) < MIN_PAIR_CODE_KEY_BYTES:
        raise ValueError("Pair code key must hold at least 32 bytes")
    enroll_limiter = enroll_limiter or RateLimiter(limit=10, window_ms=60_000, clock=clock)
    claim_limiter = claim_limiter or RateLimiter(limit=20, window_ms=60_000, clock=clock)
    router = APIRouter(prefix="/v1")

    async def run(operation: Callable[[sqlite3.Connection], Reply]) -> JSONResponse:
        def work() -> Reply:
            with closing(connect()) as connection:
                return operation(connection)

        return respond(await run_in_threadpool(work))

    def authenticated(request: Request, operation: Callable[[sqlite3.Connection, Device], Reply]):
        authorization = request.headers.getlist("authorization")

        def guarded(connection: sqlite3.Connection) -> Reply:
            device = identity.authenticate(connection, authorization)
            return error(401) if device is None else operation(connection, device)

        return guarded

    @router.post("/devices/enroll")
    async def enroll(request: Request):
        retry_after = enroll_limiter.hit(("enroll", _source(request)))
        if retry_after is not None:
            return respond(error(429, retry_after=retry_after))
        body = await _json_body(request)
        if body is None or body.keys() != {"enrollment_code", "display_name"} \
                or not isinstance(body["enrollment_code"], str) \
                or not ENROLLMENT_CODE.fullmatch(body["enrollment_code"]) \
                or not isinstance(body["display_name"], str) or not body["display_name"]:
            return respond(error(400))
        return await run(lambda connection: identity.enroll_device(
            connection, enrollment_code=body["enrollment_code"],
            display_name=body["display_name"], clock=clock,
        ))

    @router.get("/devices/me")
    async def me(request: Request):
        return await run(authenticated(request, lambda _, device: Reply(
            200, {"device_id": device.device_id, "display_name": device.display_name},
        )))

    @router.post("/pairs")
    async def create_pair(request: Request):
        key = _idempotency_key(request)
        raw = await request.body()

        def operation(connection, device):
            if key is None or raw:
                return error(400)
            return pairing.open_pair(connection, device=device, request_key=key,
                                     clock=clock, code_key=pair_code_key)

        return await run(authenticated(request, operation))

    @router.get("/pairs")
    async def list_pairs(request: Request):
        return await run(authenticated(request, lambda connection, device: pairing.list_pairs(
            connection, device=device, now_ms=clock(),
        )))

    @router.post("/pairs/claim")
    async def claim_pair(request: Request):
        key = _idempotency_key(request)
        body = await _json_body(request)
        source = _source(request)

        def operation(connection, device):
            retry_after = claim_limiter.hit(("claim", source), ("claim-device", device.device_id))
            if retry_after is not None:
                return error(429, retry_after=retry_after)
            if key is None or body is None:
                return error(400)
            return pairing.claim_pair(connection, device=device, request_key=key,
                                      body=body, clock=clock)

        return await run(authenticated(request, operation))

    @router.post("/pairs/{pair_id}/decision")
    async def decide_pair(pair_id: str, request: Request):
        key = _idempotency_key(request)
        body = await _json_body(request)

        def operation(connection, device):
            if not UUID4.fullmatch(pair_id):
                return error(404)
            if key is None or body is None:
                return error(400)
            return pairing.decide_pair(connection, device=device, pair_id=pair_id,
                                       request_key=key, body=body, clock=clock)

        return await run(authenticated(request, operation))

    return router


def respond(reply: Reply) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if reply.retry_after is not None:
        headers["Retry-After"] = str(reply.retry_after)
    return JSONResponse(reply.body, status_code=reply.status, headers=headers)


def _source(request: Request) -> str:
    return request.client.host if request.client else ""


def _idempotency_key(request: Request) -> str | None:
    values = request.headers.getlist("idempotency-key")
    return values[0] if len(values) == 1 and UUID4.fullmatch(values[0]) else None


async def _json_body(request: Request) -> dict | None:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";")[0].strip().lower() != "application/json":
        return None
    try:
        return decode_body(await request.body())
    except ValueError:
        return None
