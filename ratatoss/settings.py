"""Settings used by the local runtime and database initialization."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath
from typing import TypeVar

LOOPBACK = "127.0.0.1"
DEFAULT_NODE_PORT = 8765
PathType = TypeVar("PathType", bound=PurePath)


def local_absolute_path(value: PathType, setting: str) -> PathType:
    if not value.is_absolute():
        raise ValueError(f"{setting} must be an absolute path")
    windows_drive = PureWindowsPath(value).drive
    if windows_drive.startswith("\\\\"):
        extended_local_drive = windows_drive.removeprefix("\\\\?\\")
        if len(extended_local_drive) != 2 or extended_local_drive[1] != ":":
            raise ValueError(f"{setting} must use a local drive")
    return value


def _default_node_data_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "Ratatoss"
        return Path.home() / "AppData" / "Local" / "Ratatoss"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Ratatoss"
    root = os.environ.get("XDG_DATA_HOME")
    if root and Path(root).is_absolute():
        return Path(root) / "ratatoss"
    return Path.home() / ".local" / "share" / "ratatoss"


def node_data_dir(override: Path | None = None) -> Path:
    if override is not None:
        return local_absolute_path(override, "--data-dir")
    configured = os.environ.get("RATATOSS_NODE_DATA_DIR")
    if configured:
        return local_absolute_path(Path(configured), "RATATOSS_NODE_DATA_DIR")
    return local_absolute_path(_default_node_data_dir(), "Default Node data directory")


def controller_database(override: Path | None = None) -> Path:
    if override is not None:
        return local_absolute_path(override, "--db")
    configured = os.environ.get("RATATOSS_CONTROLLER_DB")
    if not configured:
        raise ValueError("Set --db or RATATOSS_CONTROLLER_DB for the controller database")
    return local_absolute_path(Path(configured), "RATATOSS_CONTROLLER_DB")


@dataclass(frozen=True)
class NodeSettings:
    port: int
    data_dir: Path

    @classmethod
    def load(cls, port: int | None = None, data_dir: Path | None = None) -> "NodeSettings":
        if port is None:
            configured = os.environ.get("RATATOSS_NODE_PORT", str(DEFAULT_NODE_PORT))
            try:
                port = int(configured)
            except ValueError:
                raise ValueError("RATATOSS_NODE_PORT must be an integer") from None
        if not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return cls(port, node_data_dir(data_dir))
