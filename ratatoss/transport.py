"""Pinned Croc transport for the R0.1 Windows relay profile."""

import asyncio
import errno
import hashlib
import ipaddress
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ._croc_process import JobCleanup, WindowsChild
from .lease_profile import evaluate_lease_budget

CROC_VERSION = "11.6.5"
WINDOWS_X64_SHA256 = "1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e"
COMMON_FLAGS = ("--disable-clipboard", "--no-update-check")
MAX_BATCH_BYTES = 128 * 1024 * 1024


class _PayloadProgress:
    """Keep only timestamps from Croc's receive progress bar."""

    _frame = re.compile(rb"^\s*(?:1/1 )?batch-[^\r\n]*?\s+(\d{1,3})%\s*\|")

    def __init__(self):
        self.first = None
        self.last = None
        self.first_percent = None

    def feed(self, frame: bytes, observed: float):
        match = self._frame.match(frame)
        if match is None:
            return
        percent = int(match[1])
        if 0 < percent < 100 and self.first is None:
            self.first = observed
            self.first_percent = percent
        elif percent == 100 and self.first is not None and self.last is None:
            if observed > self.first:
                self.last = observed

    def drain(self, read_fd):
        # Discard all child output after inspecting a bounded frame in memory.
        with os.fdopen(read_fd, "rb", buffering=0) as pipe:
            pending = b""
            while chunk := pipe.read(4096):
                observed = time.monotonic()
                *frames, pending = re.split(rb"[\r\n]", pending + chunk)
                for frame in frames:
                    self.feed(frame, observed)
                self.feed(pending, observed)
                if len(pending) > 4096:
                    pending = b""
            self.feed(pending, time.monotonic())


@dataclass(frozen=True)
class Batch:
    attempt_id: UUID
    size: int
    sha256: str

    def __post_init__(self):
        if not isinstance(self.attempt_id, UUID):
            raise ValueError("Expected an assignment UUID")
        if type(self.size) is not int or not 1 <= self.size <= MAX_BATCH_BYTES:
            raise ValueError("Batch size exceeds the transport profile")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("Expected a lowercase SHA-256 digest")

    @property
    def filename(self) -> str:
        return f"batch-{self.attempt_id.hex}.bin"


@dataclass(frozen=True)
class RelayProfile:
    endpoint: str
    password: str = field(repr=False)
    min_goodput_bps: int
    setup_ms: int
    verify_commit_ms: int
    margin_ms: int

    def __post_init__(self):
        host, _, port = self.endpoint.rpartition(":")
        ipaddress.IPv4Address(host)
        if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
            raise ValueError("Expected an IPv4 relay endpoint with a TCP port")
        if not self.password or "\0" in self.password:
            raise ValueError("Expected a relay password")
        evaluate_lease_budget(
            batch_bytes=1, min_goodput_bps=self.min_goodput_bps,
            remaining_lease_ms=0, remaining_adapter_ms=0,
            remaining_setup_ms=self.setup_ms, verify_commit_ms=self.verify_commit_ms,
            margin_ms=self.margin_ms,
        )


@dataclass(frozen=True)
class ProcessRun:
    pid: int
    started_at: str
    stopped_at: str
    started_monotonic: float
    stopped_monotonic: float
    deadline_monotonic: float
    exit_code: int
    job: JobCleanup
    staging_cleanup_pending: bool = False
    # Payload-level timing markers (monotonic seconds)
    first_byte_monotonic: float | None = None
    last_byte_monotonic: float | None = None
    sha256_done_monotonic: float | None = None
    first_progress_percent: int | None = None


class CrocError(RuntimeError):
    def __init__(self, code: str, process: ProcessRun | None = None):
        super().__init__(code)
        self.code = code
        self.process = process
        self.partial_isolated = False
        self.staging_cleanup_pending = False


class TransportAdapter(Protocol):
    async def send(
        self, source: Path, session_code: str, *, batch: Batch,
        timeout: float, lease_deadline: float, remaining_setup_ms: int | None = None,
    ) -> ProcessRun: ...

    async def receive(
        self, destination: Path, session_code: str, *, batch: Batch,
        timeout: float, lease_deadline: float, remaining_setup_ms: int | None = None,
    ) -> ProcessRun: ...


def _check_path(path: Path, *, directory: bool) -> os.stat_result:
    """Check an absolute path inside an adapter-owned or trusted directory tree."""
    if not path.is_absolute() or ".." in path.parts:
        raise CrocError("UNSAFE_PATH")
    for component in (*reversed(path.parents), path):
        info = component.lstat()
        is_directory = directory or component != path
        check_type = stat.S_ISDIR if is_directory else stat.S_ISREG
        if not check_type(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise CrocError("UNSAFE_PATH")
    return info


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def child_environment(private: Path) -> dict[str, str]:
    config = private / "config"
    temp = private / "temp"
    config.mkdir(mode=0o700)
    temp.mkdir(mode=0o700)
    return {
        **({"SystemRoot": os.environ["SystemRoot"]} if "SystemRoot" in os.environ else {}),
        "CROC_CONFIG_DIR": str(config),
        "TMP": str(temp),
        "TEMP": str(temp),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _remaining_ms(deadline: float, now: float) -> int:
    return max(0, math.floor((deadline - now) * 1000))


class CrocAdapter:
    """Use a trusted executable and an exclusive, access-controlled staging root.

    The caller supplies a fresh attempt ID and a deadline after authorization and
    holds its transfer slot until this call returns. Supply the estimated setup
    still needed at spawn. If omitted, the adapter reserves the profile's full
    setup budget. Cancel the RX task when the assignment becomes terminal.
    RX delivers a verified file into caller staging for a separate store commit.
    """

    def __init__(self, executable: Path, root: Path, relay: RelayProfile, *, observe_payload=False):
        self.executable = executable
        self.root = root
        self.relay = relay
        self.observe_payload = observe_payload
        try:
            _check_path(root, directory=True)
        except OSError as exc:
            raise self._io_error(exc) from None
        self._verify_binary()

    def _verify_binary(self) -> None:
        if os.name != "nt" or self.executable.suffix.lower() != ".exe":
            raise CrocError("CROC_PLATFORM_UNSUPPORTED")
        try:
            _check_path(self.executable, directory=False)
            if sha256_file(self.executable) != WINDOWS_X64_SHA256:
                raise CrocError("CROC_DIGEST_MISMATCH")
            checks = (
                (("--version",), (f"croc version {CROC_VERSION}",)),
                (("--help",), (*COMMON_FLAGS, "--relay", "--yes", "--throttleUpload")),
                (("send", "--help"), ("--no-local", "--transport")),
                (("relay", "--help"), ("--host", "--ports")),
            )
            with tempfile.TemporaryDirectory(dir=self.root) as directory:
                probe_dir = Path(directory)
                env = child_environment(probe_dir)
                for argv, required in checks:
                    result = subprocess.run(
                        [str(self.executable), *argv], shell=False, cwd=probe_dir, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10,
                    )
                    stdout = result.stdout.decode("utf-8", errors="replace")
                    if argv == ("--version",) and stdout.strip() != required[0]:
                        raise CrocError("CROC_VERSION_MISMATCH")
                    if result.returncode or not all(flag in stdout for flag in required):
                        raise CrocError("CROC_PROBE_FAILED")
        except (OSError, subprocess.TimeoutExpired):
            raise CrocError("CROC_PROBE_FAILED") from None

    def argv(self, role: str, batch: Batch) -> list[str]:
        common = [str(self.executable), *COMMON_FLAGS, "--relay", self.relay.endpoint]
        if role == "tx":
            return [*common, "send", "--no-local", "--transport", "relay", batch.filename]
        return [*common, "--yes"]

    async def send(
        self, source: Path, session_code: str, *, batch: Batch,
        timeout: float, lease_deadline: float, remaining_setup_ms: int | None = None,
    ) -> ProcessRun:
        return await self._transfer(
            "tx", source, session_code, batch, timeout, lease_deadline, remaining_setup_ms,
        )

    async def receive(
        self, destination: Path, session_code: str, *, batch: Batch,
        timeout: float, lease_deadline: float, remaining_setup_ms: int | None = None,
    ) -> ProcessRun:
        return await self._transfer(
            "rx", destination, session_code, batch, timeout, lease_deadline, remaining_setup_ms,
        )

    async def _transfer(self, role, path, session_code, batch, timeout, lease_deadline, remaining_setup_ms):
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(lease_deadline):
            raise ValueError("Expected finite transfer deadlines and a positive timeout")
        if not session_code or "\0" in session_code:
            raise ValueError("Expected the authorization's Croc session code")
        adapter_deadline = time.monotonic() + timeout
        deadline = min(adapter_deadline, lease_deadline)
        setup_ms = self.relay.setup_ms if remaining_setup_ms is None else remaining_setup_ms
        self._check_budget(batch, adapter_deadline, lease_deadline, setup_ms)
        try:
            work = self._reserve(role, batch)
        except OSError as exc:
            raise self._io_error(exc) from None

        stage = work / "data"
        payload = stage / batch.filename
        process = None
        failure = None
        delivered = False
        try:
            stage.mkdir(mode=0o700)
            env = child_environment(work) | {
                "CROC_SECRET": session_code, "CROC_PASS": self.relay.password,
            }
            if role == "tx":
                if _check_path(path, directory=False).st_size != batch.size:
                    raise CrocError("CORRUPT")
                shutil.copyfile(path, payload)
                self._check_payload(payload, batch)
            else:
                parent = _check_path(path.parent, directory=True)
                if parent.st_dev != stage.stat().st_dev:
                    raise CrocError("STAGING_FILESYSTEM_MISMATCH")
                if os.path.lexists(path):
                    raise CrocError("DESTINATION_EXISTS")

            self._check_budget(batch, adapter_deadline, lease_deadline, setup_ms)
            process = await self._run(role, batch, stage, env, deadline)
            if role == "rx":
                await self._verify_received(stage, payload, batch)
                process = replace(
                    process,
                    sha256_done_monotonic=time.monotonic(),
                )
                # Dispatch queued cancellation before entering the atomic handoff.
                await asyncio.sleep(0)
                if time.monotonic() >= deadline:
                    raise CrocError("TRANSPORT_TIMEOUT")
                os.link(payload, path)
                delivered = True
        except (OSError, CrocError, asyncio.CancelledError) as exc:
            failure = self._io_error(exc) if isinstance(exc, OSError) else exc
            if isinstance(failure, CrocError) and failure.process is None:
                failure.process = process
            if failure is exc:
                raise
            raise failure from None
        finally:
            # A failed stop leaves the reserved staging untouched for recovery.
            if isinstance(failure, CrocError) and failure.code == "PROCESS_CLEANUP_FAILED":
                failure.staging_cleanup_pending = True
            else:
                try:
                    isolated = self._cleanup_staging(work, quarantine=role == "rx" and failure is not None)
                    if isinstance(failure, CrocError):
                        failure.partial_isolated = isolated
                except OSError:
                    if delivered:
                        process = replace(process, staging_cleanup_pending=True)
                    elif isinstance(failure, CrocError):
                        failure.staging_cleanup_pending = True
                    else:
                        raise CrocError("STAGING_CLEANUP_FAILED", process) from None
        return process

    async def _verify_received(self, stage, payload, batch):
        def verify_and_flush():
            self._check_receive_directory(stage, batch)
            self._check_payload(payload, batch)
            with payload.open("r+b") as stream:
                os.fsync(stream.fileno())

        verification = asyncio.create_task(asyncio.to_thread(verify_and_flush))
        try:
            return await asyncio.shield(verification)
        except asyncio.CancelledError:
            # Even repeated cancellation must leave staging owned until the file
            # has been closed by the worker.
            while not verification.done():
                try:
                    await asyncio.wait((verification,))
                except asyncio.CancelledError:
                    continue
            if not verification.cancelled():
                verification.exception()
            raise

    @staticmethod
    def _cleanup_staging(work, *, quarantine):
        stage = work / "data"
        isolated = False
        deadline = time.monotonic() + 1
        while True:
            try:
                if quarantine and stage.is_dir() and any(stage.iterdir()):
                    stage.rename(work / "quarantine")
                    isolated = True
                for name in ("data", "config", "temp"):
                    directory = work / name
                    if directory.exists():
                        shutil.rmtree(directory)
                return isolated
            except OSError as exc:
                # On Windows, a closed process can leave a handle in rundown briefly.
                if getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)

    def _reserve(self, role, batch):
        assignment = self.root / batch.attempt_id.hex
        assignment.mkdir(mode=0o700, exist_ok=True)
        _check_path(assignment, directory=True)
        work = assignment / role
        try:
            work.mkdir(mode=0o700)
        except FileExistsError:
            raise CrocError("ATTEMPT_ALREADY_USED") from None
        return work

    def _check_budget(self, batch, adapter_deadline, lease_deadline, remaining_setup_ms):
        now = time.monotonic()
        budget = evaluate_lease_budget(
            batch_bytes=batch.size, min_goodput_bps=self.relay.min_goodput_bps,
            remaining_lease_ms=_remaining_ms(lease_deadline, now),
            remaining_adapter_ms=_remaining_ms(adapter_deadline, now),
            remaining_setup_ms=remaining_setup_ms, verify_commit_ms=self.relay.verify_commit_ms,
            margin_ms=self.relay.margin_ms,
        )
        if not budget.fits:
            raise CrocError("INSUFFICIENT_LEASE_BUDGET")

    @staticmethod
    def _check_payload(path, batch):
        try:
            info = _check_path(path, directory=False)
        except (FileNotFoundError, CrocError):
            raise CrocError("CORRUPT") from None
        if info.st_nlink != 1 or info.st_size != batch.size or sha256_file(path) != batch.sha256:
            raise CrocError("CORRUPT")

    @staticmethod
    def _check_receive_directory(stage, batch, *, running=False):
        for path in stage.iterdir():
            # v11.6.5 briefly probes hardlinks in these directories on receive.
            if running and re.fullmatch(r"\.croc-bundle-probe-[0-9a-f]{24}", path.name):
                try:
                    _check_path(path, directory=True)
                except FileNotFoundError:
                    pass
                continue
            if path.name != batch.filename:
                raise CrocError("CORRUPT")
            try:
                info = _check_path(path, directory=False)
            except FileNotFoundError:
                continue
            # Windows may omit the link count while Croc holds the write handle.
            if info.st_nlink > 1 or info.st_size > batch.size:
                raise CrocError("CORRUPT")

    async def _run(self, role, batch, stage, env, deadline):
        started = time.monotonic()
        started_at = _utc_now()
        progress = _PayloadProgress() if role == "rx" and self.observe_payload else None
        first_byte_monotonic = None
        last_byte_monotonic = None
        reader = None
        try:
            argv = self.argv(role, batch)
            if progress is None:
                child = WindowsChild(argv, cwd=stage, env=env)
            else:
                read_fd, write_fd = os.pipe()
                try:
                    with os.fdopen(write_fd, "wb", buffering=0) as stderr:
                        child = WindowsChild(argv, cwd=stage, env=env, stderr=stderr)
                except BaseException:
                    os.close(read_fd)
                    raise
                reader = threading.Thread(target=progress.drain, args=(read_fd,), daemon=True)
                reader.start()
        except OSError:
            raise CrocError("CROC_SPAWN_FAILED") from None
        exit_code = None
        error = None
        try:
            while time.monotonic() < deadline:
                exit_code = child.poll()
                if role == "rx":
                    self._check_receive_directory(stage, batch, running=exit_code is None)
                    payload = stage / batch.filename
                    if payload.is_file():
                        payload_size = payload.stat().st_size
                        now = time.monotonic()
                        if payload_size > 0 and first_byte_monotonic is None:
                            first_byte_monotonic = now
                        if payload_size >= batch.size and last_byte_monotonic is None:
                            last_byte_monotonic = now
                if exit_code is not None:
                    break
                await asyncio.sleep(min(0.001, max(0, deadline - time.monotonic())))
            if exit_code is None:
                error = CrocError("TRANSPORT_TIMEOUT")
            elif exit_code:
                error = CrocError("CROC_EXIT_NONZERO")
        except CrocError as exc:
            error = exc
        finally:
            try:
                cleanup = child.stop()
            except OSError:
                raise CrocError("PROCESS_CLEANUP_FAILED") from None
            finally:
                if reader is not None:
                    reader.join(timeout=1)
        result = ProcessRun(
            child.pid, started_at, _utc_now(), started, time.monotonic(), deadline, cleanup.exit_code, cleanup,
            first_byte_monotonic=first_byte_monotonic,
            last_byte_monotonic=last_byte_monotonic,
            first_progress_percent=progress.first_percent if progress else None,
        )
        if error:
            error.process = result
            raise error
        return result

    @staticmethod
    def _io_error(exc: OSError) -> CrocError:
        if exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == 112:
            return CrocError("NO_SPACE")
        if isinstance(exc, FileExistsError):
            return CrocError("DESTINATION_EXISTS")
        return CrocError("STAGING_IO_FAILED")
