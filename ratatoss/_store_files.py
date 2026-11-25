"""Filesystem operations for durable publication in the Node store."""

import os
import stat
from pathlib import Path


def check_path(path: Path, *, directory: bool = False) -> os.stat_result:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Expected an absolute path without parent traversal")
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        expected = stat.S_ISDIR if directory or component != path else stat.S_ISREG
        if not expected(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Expected a regular file or directory without links")
    return info


def sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def publish(source: Path, destination: Path) -> None:
    """Publish a flushed file without replacing an existing destination."""
    if os.name != "nt":
        os.link(source, destination)
        sync_directory(destination.parent)
        source.unlink()
        return

    import ctypes
    from ctypes import wintypes

    move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    move.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move.restype = wintypes.BOOL
    # MOVEFILE_WRITE_THROUGH without REPLACE_EXISTING or COPY_ALLOWED.
    if not move(str(source), str(destination), 0x00000008):
        raise ctypes.WinError(ctypes.get_last_error())


def lock_store(path: Path):
    """Hold a process lock until the returned file is closed."""
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        stream.close()
        raise
    return stream
