"""Open the local SQLite databases from the versioned Ratatoss schemas."""

import sqlite3
from contextlib import closing
from importlib.resources import files
from pathlib import Path
from time import monotonic, sleep
from typing import Literal

from .settings import local_absolute_path

Role = Literal["node", "controller"]
NODE_DATABASE_NAME = "node.sqlite3"
SCHEMA_VERSIONS = {"node": 2, "controller": 1}
BUSY_TIMEOUT_MS = 5000
APPLICATION_IDS = {
    "node": 0x5241544E,        # RATN
    "controller": 0x52415443,  # RATC
}


def _schema_statements(role: Role):
    resource = files("ratatoss").joinpath("_sql", f"{role}.sql")
    if resource.is_file():
        source = resource.read_text(encoding="utf-8")
    else:
        # Source checkouts and editable installs use the same canonical DDL.
        path = Path(__file__).resolve().parent.parent / "spec" / "db" / f"{role}.sql"
        source = path.read_text(encoding="utf-8")

    # The canonical DDL is also a standalone bootstrap script. Keep the DDL
    # inside our transaction while applying its connection settings separately.
    prefix, begin, body = source.partition("BEGIN IMMEDIATE;")
    body, commit, suffix = body.rpartition("COMMIT;")
    if not (begin and commit) or suffix.strip() or not prefix.rstrip().endswith(
        "PRAGMA busy_timeout = 5000;"
    ):
        raise ValueError("Unrecognized SQLite schema script envelope")
    statement = ""
    for line in body.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            yield statement
            statement = ""
    if statement.strip():
        raise ValueError("Incomplete SQLite schema statement")


def _schema_version(connection: sqlite3.Connection, role: Role) -> int:
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if application_id == APPLICATION_IDS[role]:
        if not 1 <= version <= SCHEMA_VERSIONS[role]:
            raise ValueError(f"Unsupported {role} database schema version")
        return version
    if application_id in APPLICATION_IDS.values():
        raise ValueError(f"Database belongs to the other Ratatoss role, expected {role}")
    if application_id or version or connection.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone():
        raise ValueError("Unrecognized SQLite database schema")
    return 0


def _enable_wal(connection: sqlite3.Connection) -> None:
    deadline = monotonic() + BUSY_TIMEOUT_MS / 1000
    while True:
        try:
            mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode != "wal":
                raise ValueError("SQLite database requires WAL journal mode")
            return
        except sqlite3.OperationalError as exc:
            # Changing journal mode can report BUSY without waiting for the
            # connection's busy handler when another process is bootstrapping.
            if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY or monotonic() >= deadline:
                raise
            sleep(0.01)


def open_database(path: Path, role: Role) -> sqlite3.Connection:
    """Return an initialized connection. The caller owns and closes it."""
    application_id = APPLICATION_IDS[role]
    target_version = SCHEMA_VERSIONS[role]
    if sqlite3.sqlite_version_info < (3, 38, 0):
        raise ValueError("Ratatoss requires SQLite 3.38.0 or later")
    local_absolute_path(path, "Database path")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("SELECT json_valid('{}')").fetchone()

        # Reopening an initialized WAL database requires no write lock.
        # Read the identity consistently before changing journal mode.
        with connection:
            connection.execute("BEGIN")
            version = _schema_version(connection, role)
            if version == target_version and connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                return connection
        _enable_wal(connection)

        # Recheck under the write lock since another initializer may have won
        # the race between the identity check and the journal mode change.
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            version = _schema_version(connection, role)
            if version == 0:
                for statement in _schema_statements(role):
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id = {application_id}")
            elif role == "node" and version == 1:
                connection.execute(
                    """ALTER TABLE outbox ADD COLUMN sent_boot_id TEXT
                       CHECK (sent_boot_id IS NULL OR first_sent_at_ms IS NOT NULL)"""
                )
            if version < target_version:
                connection.execute(f"PRAGMA user_version = {target_version}")
    except BaseException:
        connection.close()
        raise
    return connection


def initialize_database(path: Path, role: Role) -> None:
    with closing(open_database(path, role)):
        pass
