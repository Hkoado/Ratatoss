"""SQLite transaction and scheduler lifecycle for one controller process."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager, nullcontext
from pathlib import Path
from threading import Lock

from ..database import open_database
from .config import ControllerConfig
from .leases import SessionCodes, reset_connections
from .registry import Registry, SlotReport
from .schedule import issue_assignments


def wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


class ControllerRuntime:
    def __init__(self, database: Path, config: ControllerConfig,
                 *, clock: Callable[[], int] = wall_clock_ms):
        self.database = database
        self.config = config
        self.clock = clock
        self.codes = SessionCodes()
        self._writer = Lock()
        self._slot_reports: dict[str, SlotReport] = {}

    def connect(self) -> sqlite3.Connection:
        return open_database(self.database, "controller")

    @contextmanager
    def transaction(self, *, write: bool = True) -> Iterator[Registry]:
        # Keep the heartbeat observations in step with the committed slot counters.
        with self._writer if write else nullcontext(), closing(self.connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                registry = Registry(connection, self.clock(), self._slot_reports if write else None)
                yield registry
            if write:
                self._slot_reports.update(registry.pending_slot_reports)

    def startup(self) -> None:
        with self.transaction() as registry:
            reset_connections(registry)
        self._slot_reports.clear()
        self.codes = SessionCodes()

    def tick(self) -> list[str]:
        with self.transaction() as registry:
            issued = issue_assignments(registry, self.config.schedule, self.config.lease_profiles)
            self.codes.discard_expired(registry.now_ms)
        return issued
