"""Assemble staged batches into a verified temporary output file."""

from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile
from typing import Mapping

from ratatoss.manifest import Manifest, READ_SIZE


class BatchAssemblyError(ValueError):
    """Raised when batch assembly fails validation or encounter file errors."""
    pass


class BatchInputError(BatchAssemblyError):
    """An identified input batch failed inspection or verification."""

    def __init__(self, batch_id: int, message: str, *, state: str = "CORRUPT"):
        super().__init__(message)
        self.batch_id = batch_id
        self.state = state


def _input_io_error(batch_id: int, cause: OSError) -> BatchInputError:
    missing = isinstance(cause, FileNotFoundError)
    return BatchInputError(
        batch_id, f"Batch file at index {batch_id} is missing or could not be read",
        state="MISSING" if missing else "UNREADABLE",
    )


def _read_batch(stream, size: int, batch_id: int) -> bytes:
    try:
        return stream.read(size)
    except OSError as exc:
        raise _input_io_error(batch_id, exc) from exc


def assemble_batches(
    manifest: Manifest,
    batches: Mapping[int, Path | str],
    temp_dir: Path | str,
    *,
    read_size: int = READ_SIZE,
) -> Path:
    """Assemble verified batches into a temporary file on temp_dir, verified against manifest.
    
    Args:
        manifest: Validated Manifest instance.
        batches: Mapping from batch index (int) to Path of the batch file in store.
        temp_dir: Directory on the target volume where the temp file is created.
        read_size: Buffer size for bounded stream reading/writing. Must be a positive integer.

    Returns:
        Path to the verified temporary output file.
        
    Raises:
        BatchAssemblyError: If batches are missing, invalid, size/hash mismatch occurs,
                            read_size is invalid, or temp file verification fails.
    """
    if type(read_size) is not int or read_size <= 0:
        raise BatchAssemblyError(f"read_size must be a positive integer, got: {read_size!r}")

    manifest.validate()
    temp_path = Path(temp_dir)
    if not temp_path.is_dir():
        raise BatchAssemblyError(f"Temporary directory does not exist or is not a directory: {temp_path}")

    expected_batch_count = len(manifest.batches)
    for idx in range(expected_batch_count):
        if idx not in batches:
            raise BatchAssemblyError(f"Missing batch at index {idx}")

    temp_file_fd, temp_file_path_str = tempfile.mkstemp(
        dir=str(temp_path),
        prefix="ratatoss-assemble-",
        suffix=".tmp",
    )
    temp_file_path = Path(temp_file_path_str)

    try:
        with os.fdopen(temp_file_fd, "wb") as destination:
            # Assembly must proceed strictly by offset order from manifest.batches
            for batch_meta in manifest.batches:
                batch_id = batch_meta.index
                batch_file_path = Path(batches[batch_meta.index])
                try:
                    batch_stat_before = batch_file_path.stat()
                except OSError as exc:
                    raise _input_io_error(batch_id, exc) from exc
                if not stat.S_ISREG(batch_stat_before.st_mode):
                    raise BatchInputError(
                        batch_id, f"Batch file at index {batch_id} is not a regular file: {batch_file_path}",
                    )
                if batch_stat_before.st_size != batch_meta.size:
                    raise BatchInputError(
                        batch_id, f"Batch size mismatch at index {batch_id}: "
                        f"expected {batch_meta.size}, found {batch_stat_before.st_size}",
                    )

                batch_hasher = sha256()
                batch_read = 0

                try:
                    batch_input = batch_file_path.open("rb")
                except OSError as exc:
                    raise _input_io_error(batch_id, exc) from exc
                with batch_input as src:
                    while batch_read < batch_meta.size:
                        chunk = _read_batch(src, min(read_size, batch_meta.size - batch_read), batch_id)
                        if not chunk:
                            raise BatchInputError(
                                batch_id, f"Unexpected EOF reading batch index {batch_id} "
                                f"at offset {batch_read}/{batch_meta.size}",
                            )
                        destination.write(chunk)
                        batch_hasher.update(chunk)
                        batch_read += len(chunk)

                    trailing = _read_batch(src, 1, batch_id)
                    if trailing:
                        raise BatchInputError(
                            batch_id, f"Batch file at index {batch_id} has trailing bytes beyond {batch_meta.size}",
                        )

                if batch_hasher.hexdigest() != batch_meta.sha256:
                    raise BatchInputError(
                        batch_id, f"Batch SHA-256 digest mismatch at index {batch_id}: "
                        f"expected {batch_meta.sha256}, calculated {batch_hasher.hexdigest()}",
                    )

            destination.flush()
            os.fsync(destination.fileno())

        # Verify the actual assembled file on disk directly using bounded buffers
        temp_stat = os.stat(temp_file_path)
        if not stat.S_ISREG(temp_stat.st_mode):
            raise BatchAssemblyError("Assembled temporary file is not a regular file")
        if temp_stat.st_size != manifest.size:
            raise BatchAssemblyError(
                f"Assembled file size mismatch: expected {manifest.size}, found {temp_stat.st_size}"
            )

        disk_hasher = sha256()
        verified_read = 0
        with temp_file_path.open("rb") as disk_src:
            while verified_read < manifest.size:
                block = disk_src.read(min(read_size, manifest.size - verified_read))
                if not block:
                    raise BatchAssemblyError("Unexpected EOF while verifying assembled temporary file")
                disk_hasher.update(block)
                verified_read += len(block)
            trailing_temp = disk_src.read(1)
            if trailing_temp:
                raise BatchAssemblyError("Assembled temporary file has trailing bytes beyond manifest size")

        if disk_hasher.hexdigest() != manifest.sha256:
            raise BatchAssemblyError(
                f"Assembled file SHA-256 mismatch: expected {manifest.sha256}, calculated {disk_hasher.hexdigest()}"
            )

        return temp_file_path

    except Exception:
        # Cleanup temporary assembly file on any failure
        if temp_file_path.exists():
            try:
                temp_file_path.unlink()
            except OSError:
                pass
        raise
