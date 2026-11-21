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
        read_size: Buffer size for bounded stream reading/writing.

    Returns:
        Path to the verified temporary output file.
        
    Raises:
        BatchAssemblyError: If batches are missing, invalid, size/hash mismatch occurs,
                            or temp file verification fails.
    """
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
        whole_hasher = sha256()
        total_written = 0

        with os.fdopen(temp_file_fd, "wb") as destination:
            # Assembly must proceed strictly by offset order from manifest.batches
            for batch_meta in manifest.batches:
                batch_file_path = Path(batches[batch_meta.index])
                if not batch_file_path.is_file():
                    raise BatchAssemblyError(
                        f"Batch file at index {batch_meta.index} is not a regular file: {batch_file_path}"
                    )

                batch_stat_before = os.stat(batch_file_path)
                if not stat.S_ISREG(batch_stat_before.st_mode):
                    raise BatchAssemblyError(
                        f"Batch file at index {batch_meta.index} is not a regular file: {batch_file_path}"
                    )
                if batch_stat_before.st_size != batch_meta.size:
                    raise BatchAssemblyError(
                        f"Batch size mismatch at index {batch_meta.index}: "
                        f"expected {batch_meta.size}, found {batch_stat_before.st_size}"
                    )

                batch_hasher = sha256()
                batch_read = 0

                with batch_file_path.open("rb") as src:
                    while batch_read < batch_meta.size:
                        chunk = src.read(min(read_size, batch_meta.size - batch_read))
                        if not chunk:
                            raise BatchAssemblyError(
                                f"Unexpected EOF reading batch index {batch_meta.index} "
                                f"at offset {batch_read}/{batch_meta.size}"
                            )
                        destination.write(chunk)
                        batch_hasher.update(chunk)
                        whole_hasher.update(chunk)
                        batch_read += len(chunk)
                        total_written += len(chunk)

                    # Ensure no extra trailing bytes
                    trailing = src.read(1)
                    if trailing:
                        raise BatchAssemblyError(
                            f"Batch file at index {batch_meta.index} has trailing bytes beyond {batch_meta.size}"
                        )

                if batch_hasher.hexdigest() != batch_meta.sha256:
                    raise BatchAssemblyError(
                        f"Batch SHA-256 digest mismatch at index {batch_meta.index}: "
                        f"expected {batch_meta.sha256}, calculated {batch_hasher.hexdigest()}"
                    )

            destination.flush()
            os.fsync(destination.fileno())

        if total_written != manifest.size:
            raise BatchAssemblyError(
                f"Total written size mismatch: expected {manifest.size}, got {total_written}"
            )

        calculated_whole_sha256 = whole_hasher.hexdigest()
        if calculated_whole_sha256 != manifest.sha256:
            raise BatchAssemblyError(
                f"Total file SHA-256 mismatch: expected {manifest.sha256}, calculated {calculated_whole_sha256}"
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
