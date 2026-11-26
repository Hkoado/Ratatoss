"""Compose the controller's device and job APIs for one HTTPS server process."""

import re
from argparse import Namespace
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI

from ..database import open_database
from ..settings import LOOPBACK, controller_database
from . import active_pair_id, authenticate, create_router, issue_enrollment_code
from .config import ControllerConfig
from .control_api import create_control_app
from .runtime import ControllerRuntime, wall_clock_ms

_PAIR_KEY = re.compile(rb"[0-9a-f]{64}(?:\r?\n)?")


def create_service(runtime: ControllerRuntime, *, pair_code_key: bytes,
                   tick_seconds: float = 1) -> FastAPI:
    def identify(connection, headers):
        device = authenticate(connection, headers)
        return device.device_id if device is not None else None

    app = create_control_app(runtime, identify=identify, active_pair_id=active_pair_id,
                             tick_seconds=tick_seconds)
    app.include_router(create_router(connect=runtime.connect, pair_code_key=pair_code_key,
                                     clock=runtime.clock))
    return app


def run(args: Namespace) -> int:
    database = controller_database(args.db)
    if args.controller_command == "issue-enrollment":
        with closing(open_database(database, "controller")) as connection:
            code = issue_enrollment_code(connection, now_ms=wall_clock_ms())
        print(code)
        return 0

    if not 1 <= args.port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    with args.pair_key_file.open("rb") as stream:
        raw_key = stream.read(67)
    if not _PAIR_KEY.fullmatch(raw_key):
        raise ValueError("Pair key file must contain 64 lowercase hex digits")
    pair_key = bytes.fromhex(raw_key.decode("ascii"))
    runtime = ControllerRuntime(database, ControllerConfig.load(args.config))

    import uvicorn

    uvicorn.run(
        create_service(runtime, pair_code_key=pair_key),
        host=args.host, port=args.port, ssl_certfile=str(args.ssl_certfile),
        ssl_keyfile=str(args.ssl_keyfile), proxy_headers=False, access_log=False,
    )
    return 0
