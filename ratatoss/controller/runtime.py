"""SQLite transaction and scheduler lifecycle for one controller process."""

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from ..database import open_database
from .config import ControllerConfig
from .leases import SessionCodes, reset_connections
from .registry import Registry
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

    def connect(self) -> sqlite3.Connection:
        return open_database(self.database, "controller")

    @contextmanager
    def transaction(self) -> Iterator[Registry]:
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            yield Registry(connection, self.clock())

    def startup(self) -> None:
        with self.transaction() as registry:
            reset_connections(registry)
        self.codes = SessionCodes()

    def tick(self) -> list[str]:
        with self.transaction() as registry:
            issued = issue_assignments(registry, self.config.schedule)
            self.codes.discard_expired(registry.now_ms)
        return issued
