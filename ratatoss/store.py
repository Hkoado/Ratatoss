"""Durable Node storage for manifests, verified batches, and delivery."""

from contextlib import closing, contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Event, Lock, RLock
from time import time_ns
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

from ._store_files import check_path, discard_staging, lock_store, publish, sync_directory
from .batch_assembly import BatchInputError, assemble_batches
from .database import NODE_DATABASE_NAME, open_database
from .manifest import (
    DEFAULT_BATCH_SIZE, DEFAULT_PIECE_SIZE, READ_SIZE, Manifest,
    build_manifest, verify_batch, verify_file,
)
from .settings import local_absolute_path


class StoreError(RuntimeError):
    """A storage failure with a code usable by the Node agent."""


def _now() -> int:
    return time_ns() // 1_000_000


def _uuid(value: str) -> str:
    return str(UUID(value))


def _manifest(value: Manifest | str | bytes) -> Manifest:
    return value if isinstance(value, Manifest) else Manifest.from_json(value)


def _batch(manifest: Manifest, index: int):
    if type(index) is not int or not 0 <= index < len(manifest.batches):
        raise ValueError("Batch index out of range")
    return manifest.batches[index]


def _file_state(path: Path, size: int, verify) -> str:
    try:
        if check_path(path).st_size == size and verify():
            return "AVAILABLE"
    except FileNotFoundError:
        return "MISSING"
    except OSError:
        return "UNREADABLE"
    except ValueError:
        pass
    return "CORRUPT"


class NodeStore:
    """One active store per Node data directory.

    Open after stopping workers from the previous boot. Operations for a job
    serialize file publication, inventory updates, and delivery recovery.
    """

    def __init__(self, data_dir: Path):
        self.root = local_absolute_path(Path(data_dir), "Node data directory")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        check_path(self.root, directory=True)
        self.boot_id = str(uuid4())
        self._locks = WeakValueDictionary()
        self._locks_guard = Lock()
        self._active_tx: dict[tuple[str, int], dict[Path, Event]] = {}
        self._deferred_deliveries: set[str] = set()
        lock_path = self.root / "store.lock"
        if os.path.lexists(lock_path):
            check_path(lock_path)
        self._owner = lock_store(lock_path)
        try:
            self.jobs = self.root / "jobs"
            self.jobs.mkdir(mode=0o700, exist_ok=True)
            check_path(self.jobs, directory=True)
            sync_directory(self.root)
            self._recover()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._owner.close()

    def _job_lock(self, job_id, *, delivery=False):
        key = (job_id, delivery)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = RLock()
            return lock

    @contextmanager
    def _db(self, *, write=False):
        if self._owner.closed:
            raise StoreError("STORE_CLOSED")
        with closing(open_database(self.root / NODE_DATABASE_NAME, "node")) as db, db:
            db.row_factory = sqlite3.Row
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db

    def _directory(self, job_id):
        return self.jobs / job_id

    def _prepare_directory(self, job_id):
        directory = self._directory(job_id)
        directory.mkdir(mode=0o700, exist_ok=True)
        check_path(directory, directory=True)
        sync_directory(self.jobs)
        return directory

    def _batch_path(self, job_id, batch_id):
        return self._directory(job_id) / f"batch-{batch_id}.bin"

    def _receive_path(self, job_id, assignment_id):
        return self._directory(job_id) / f"rx-{assignment_id}.part"

    @staticmethod
    def _stored_manifest(job):
        manifest = Manifest.from_json(job["manifest_canonical"])
        if bytes.fromhex(manifest.manifest_sha256()) != job["manifest_sha256"]:
            raise StoreError("MANIFEST_DIGEST_MISMATCH")
        return manifest

    @staticmethod
    def _job(db, job_id):
        job = db.execute(
            "SELECT * FROM local_jobs WHERE job_id = ? AND closed_at_ms IS NULL", (job_id,)
        ).fetchone()
        if job is None:
            raise StoreError("JOB_NOT_OPEN")
        return job

    @staticmethod
    def _target(job):
        if job["role"] != "TARGET" or job["consent"] != "ACCEPT":
            raise StoreError("TARGET_NOT_ACCEPTED")

    def register_target(self, job_id: str, source_device_id: str, offer_id: str,
                        manifest: Manifest | str | bytes, destination: Path, *,
                        consent_request_key: str, allow_forward: bool = False) -> Manifest:
        """Persist an accepted offer and its delivery plan before sending consent."""
        job_id, source_device_id, offer_id = map(_uuid, (job_id, source_device_id, offer_id))
        manifest = _manifest(manifest)
        canonical = manifest.canonical_bytes()
        digest = bytes.fromhex(manifest.manifest_sha256())
        destination = self._destination(destination)
        with self._job_lock(job_id, delivery=True), self._job_lock(job_id):
            directory = self._prepare_directory(job_id)
            with self._db() as db:
                existing = db.execute("SELECT * FROM local_jobs WHERE job_id = ?", (job_id,)).fetchone()
                delivery = self._delivery(db, job_id)
            if existing is not None:
                if (
                    existing["closed_at_ms"] is not None or existing["role"] != "TARGET"
                    or (existing["source_device_id"], existing["offer_id"], existing["consent"],
                        existing["consent_request_key"], existing["allow_forward"])
                    != (source_device_id, offer_id, "ACCEPT", consent_request_key, allow_forward)
                    or self._stored_manifest(existing) != manifest
                    or delivery is None or delivery["intended_path"] != str(destination)
                ):
                    raise StoreError("JOB_CONFLICT")
                return manifest
            with self._db(write=True) as db:
                db.execute(
                    """INSERT INTO local_jobs
                       (job_id, role, source_device_id, offer_id, manifest_canonical, manifest_sha256,
                        private_job_path, consent, consent_request_key, allow_forward, created_at_ms)
                       VALUES (?, 'TARGET', ?, ?, ?, ?, ?, 'ACCEPT', ?, ?, ?)""",
                    (job_id, source_device_id, offer_id, canonical, digest, str(directory),
                     consent_request_key, allow_forward, _now()),
                )
                self._set_delivery(db, job_id, destination, "PLANNED")
        return manifest

    def import_source(self, job_id: str, source_device_id: str, source: Path, *,
                      max_bytes: int, piece_size: int = DEFAULT_PIECE_SIZE,
                      batch_size: int = DEFAULT_BATCH_SIZE) -> Manifest:
        """Copy a selected file into an immutable source snapshot before registering it."""
        job_id, source_device_id = map(_uuid, (job_id, source_device_id))
        source = Path(source)
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError("Invalid source size limit")
        with self._job_lock(job_id):
            directory = self._prepare_directory(job_id)
            with self._db() as db:
                existing = db.execute("SELECT * FROM local_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if existing is not None and (
                existing["role"] != "SOURCE" or existing["source_device_id"] != source_device_id
                or existing["closed_at_ms"] is not None
            ):
                raise StoreError("JOB_CONFLICT")
            before = check_path(source)
            if before.st_size > max_bytes:
                raise StoreError("SOURCE_TOO_LARGE")
            if shutil.disk_usage(directory).free < before.st_size:
                raise StoreError("NO_SPACE")
            snapshot = directory / "source.bin"
            temporary = directory / "source.part"
            temporary.unlink(missing_ok=True)
            try:
                with source.open("rb") as incoming, temporary.open("xb") as outgoing:
                    if not os.path.samestat(before, os.fstat(incoming.fileno())):
                        raise StoreError("SOURCE_CHANGED")
                    self._copy_bytes(incoming, outgoing, before.st_size)
                    after = os.fstat(incoming.fileno())
                    if incoming.read(1) or after.st_mtime_ns != before.st_mtime_ns:
                        raise StoreError("SOURCE_CHANGED")
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                manifest = replace(build_manifest(temporary, piece_size=piece_size, batch_size=batch_size),
                                   name=source.name)
                canonical = manifest.canonical_bytes()
                digest = bytes.fromhex(manifest.manifest_sha256())
                if existing is not None and self._stored_manifest(existing) != manifest:
                    raise StoreError("JOB_CONFLICT")
                state = self._source_state(snapshot, manifest)
                if state == "UNREADABLE":
                    raise StoreError("SOURCE_NOT_AVAILABLE")
                if state != "AVAILABLE":
                    snapshot.unlink(missing_ok=True)
                    publish(temporary, snapshot)
                sync_directory(directory)
                with self._db(write=True) as db:
                    if existing is None:
                        db.execute(
                            """INSERT INTO local_jobs
                               (job_id, role, source_device_id, manifest_canonical, manifest_sha256,
                                private_job_path, source_snapshot_path, created_at_ms)
                               VALUES (?, 'SOURCE', ?, ?, ?, ?, ?, ?)""",
                            (job_id, source_device_id, canonical, digest, str(directory), str(snapshot), _now()),
                        )
                    for segment in manifest.batches:
                        self._set_batch(db, job_id, segment.index, snapshot, "AVAILABLE")
                return manifest
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_bytes(incoming, outgoing, size):
        while size:
            block = incoming.read(min(size, READ_SIZE))
            if not block:
                raise StoreError("UNEXPECTED_EOF")
            outgoing.write(block)
            size -= len(block)

    def begin_receive(self, job_id: str, batch_id: int, assignment_id: str) -> Path:
        """Reserve the private destination passed to the transport adapter."""
        job_id, assignment_id = map(_uuid, (job_id, assignment_id))
        staging = self._receive_path(job_id, assignment_id)
        with self._job_lock(job_id):
            with self._db() as db:
                job = self._job(db, job_id)
                self._target(job)
            _batch(self._stored_manifest(job), batch_id)
            check_path(staging.parent, directory=True)
            with self._db(write=True) as db:
                attempt = db.execute("SELECT * FROM local_attempts WHERE assignment_id = ?", (assignment_id,)).fetchone()
                if attempt is not None:
                    if (attempt["job_id"], attempt["batch_id"], attempt["boot_id"], attempt["role"],
                        attempt["state"]) != (job_id, batch_id, self.boot_id, "RX", "ASSIGNED"):
                        raise StoreError("ASSIGNMENT_CONFLICT")
                    return staging
                db.execute(
                    """INSERT INTO local_batches (job_id, batch_id, state, updated_at_ms)
                       VALUES (?, ?, 'MISSING', ?) ON CONFLICT(job_id, batch_id) DO NOTHING""",
                    (job_id, batch_id, _now()),
                )
                db.execute(
                    """INSERT INTO local_attempts
                       (assignment_id, job_id, batch_id, boot_id, role, staging_path, state, created_at_ms)
                       VALUES (?, ?, ?, ?, 'RX', ?, 'ASSIGNED', ?)""",
                    (assignment_id, job_id, batch_id, self.boot_id, str(staging), _now()),
                )
        return staging

    def commit_receive(self, assignment_id: str) -> Path:
        """Verify after the RX worker stops, publish, then commit availability and ACK."""
        assignment_id = _uuid(assignment_id)
        with self._db() as db:
            attempt = db.execute("SELECT * FROM local_attempts WHERE assignment_id = ?", (assignment_id,)).fetchone()
        if attempt is None or attempt["role"] != "RX" or attempt["boot_id"] != self.boot_id:
            raise StoreError("ASSIGNMENT_NOT_ACTIVE")
        job_id, batch_id = attempt["job_id"], attempt["batch_id"]
        with self._job_lock(job_id, delivery=True), self._job_lock(job_id):
            with self._db() as db:
                job = self._job(db, job_id)
                self._target(job)
                state = db.execute("SELECT state FROM local_attempts WHERE assignment_id = ?",
                                   (assignment_id,)).fetchone()[0]
            manifest = self._stored_manifest(job)
            staging = self._receive_path(job_id, assignment_id)
            path = self._batch_path(job_id, batch_id)
            stored = self._batch_state(path, manifest, batch_id)
            if state == "FINISHED":
                if stored == "AVAILABLE":
                    return path
                with self._db(write=True) as db:
                    self._invalidate(db, job_id, batch_id, stored)
                raise StoreError("BATCH_NOT_AVAILABLE")
            if state not in ("ASSIGNED", "TRANSFERRING", "RECEIVED", "VERIFIED"):
                raise StoreError("ASSIGNMENT_NOT_ACTIVE")
            if stored == "UNREADABLE":
                with self._db(write=True) as db:
                    self._invalidate(db, job_id, batch_id, stored)
                raise StoreError("BATCH_NOT_AVAILABLE")
            # A published file with the same assignment may survive an interrupted DB commit.
            received = self._batch_state(staging, manifest, batch_id)
            if received == "UNREADABLE":
                raise StoreError("RX_NOT_STAGED")
            if received != "AVAILABLE" and not (
                received == "MISSING" and state == "VERIFIED" and stored == "AVAILABLE"
            ):
                if received == "MISSING":
                    raise StoreError("RX_NOT_STAGED")
                with self._db(write=True) as db:
                    self._finish_attempt(db, assignment_id, "FAILED")
                    if stored != "AVAILABLE":
                        self._invalidate(db, job_id, batch_id, "CORRUPT")
                discard_staging(staging)
                raise StoreError("CORRUPT")
            if received == "AVAILABLE":
                with staging.open("r+b") as stream:
                    os.fsync(stream.fileno())
                with self._db(write=True) as db:
                    if stored != "AVAILABLE":
                        self._invalidate(db, job_id, batch_id, stored)
                    db.execute("UPDATE local_attempts SET state = 'VERIFIED' WHERE assignment_id = ?",
                               (assignment_id,))
                if stored != "AVAILABLE":
                    discard_staging(path)
                    publish(staging, path)
            sync_directory(path.parent)
            with self._db(write=True) as db:
                self._set_batch(db, job_id, batch_id, path, "AVAILABLE")
                self._finish_attempt(db, assignment_id, "FINISHED")
                self._enqueue(db, job_id, "ACK", {"batch_sha256": manifest.batches[batch_id].sha256},
                              batch_id=batch_id, assignment_id=assignment_id)
            staging.unlink(missing_ok=True)
            return path

    @staticmethod
    def _finish_attempt(db, assignment_id, state):
        db.execute(
            """UPDATE local_attempts SET state = ?, closed_at_ms = max(created_at_ms, ?)
               WHERE assignment_id = ?""",
            (state, _now(), assignment_id),
        )

    @staticmethod
    def _batch_state(path, manifest, batch_id):
        return _file_state(path, manifest.batches[batch_id].size,
                           lambda: verify_batch(path, manifest, batch_id))

    @staticmethod
    def _source_state(path, manifest):
        return _file_state(path, manifest.size, lambda: verify_file(path, manifest))

    @staticmethod
    def _set_batch(db, job_id, batch_id, path, state):
        db.execute(
            """INSERT INTO local_batches (job_id, batch_id, storage_path, state, updated_at_ms)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(job_id, batch_id) DO UPDATE SET
               storage_path = excluded.storage_path, state = excluded.state,
               updated_at_ms = excluded.updated_at_ms""",
            (job_id, batch_id, str(path) if path is not None else None, state, _now()),
        )

    def _invalidate(self, db, job_id, batch_id, state):
        old = db.execute("SELECT state, storage_path FROM local_batches WHERE job_id = ? AND batch_id = ?",
                         (job_id, batch_id)).fetchone()
        self._record_unavailable(db, job_id, batch_id, state,
                                 read_retry_path=old["storage_path"] if old is not None else None)
        if old is not None and old["state"] == "AVAILABLE":
            self._snapshot(db, job_id)

    def _record_unavailable(self, db, job_id, batch_id, state, *, read_retry_path=None):
        for event in self._active_tx.get((job_id, batch_id), {}).values():
            event.set()
        if state == "UNREADABLE":
            self._set_batch(db, job_id, batch_id, read_retry_path, "MISSING")
        else:
            self._set_batch(db, job_id, batch_id, None, state)
        db.execute(
            """DELETE FROM outbox WHERE job_id = ? AND batch_id = ? AND event_kind = 'ACK'
               AND sent_boot_id IS NOT ?""",
            (job_id, batch_id, self.boot_id),
        )

    @staticmethod
    def _inventory(db, job_id):
        return tuple(
            row[0] for row in db.execute(
                "SELECT batch_id FROM local_batches WHERE job_id = ? AND state = 'AVAILABLE' ORDER BY batch_id",
                (job_id,),
            )
        )

    def inventory(self, job_id: str) -> tuple[int, ...]:
        """Return committed, reconciled batch IDs for a local job."""
        job_id = _uuid(job_id)
        with self._db() as db:
            job = self._job(db, job_id)
            if job["role"] == "TARGET":
                self._target(job)
            return self._inventory(db, job_id)

    def reconcile(self, job_id: str) -> tuple[int, ...]:
        """Rescan a job on reconnect and retry deferred delivery verification."""
        job_id = _uuid(job_id)
        with self._job_lock(job_id):
            with self._db() as db:
                job = self._job(db, job_id)
                if job["role"] == "TARGET":
                    self._target(job)
            source = job["role"] == "SOURCE"
            manifest = self._stored_manifest(job)
            batches = self._scan_batches(job_id, manifest, source)
            with self._db(write=True) as db:
                self._record_scan(db, job_id, batches, adopt=source)
                self._snapshot(db, job_id)
                inventory = self._inventory(db, job_id)
        if job_id in self._deferred_deliveries:
            with self._job_lock(job_id, delivery=True):
                if job_id in self._deferred_deliveries:
                    with self._db() as db:
                        delivery = self._delivery(db, job_id)
                    self._recover_delivery(job_id, manifest, delivery)
        return inventory

    @contextmanager
    def tx_batch(self, job_id: str, batch_id: int, *, cancel_event: Event | None = None):
        """Hold a verified input until TX stops. A worker can watch cancel_event
        for invalidation and must stop before its caller exits the context.
        """
        job_id = _uuid(job_id)
        path = self._directory(job_id) / f"tx-{uuid4().hex}.part"
        registered = False
        try:
            with self._job_lock(job_id):
                self._prepare_tx(job_id, batch_id, path)
                if cancel_event is not None:
                    self._active_tx.setdefault((job_id, batch_id), {})[path] = cancel_event
                    registered = True
            yield path
        finally:
            if registered:
                with self._job_lock(job_id):
                    active = self._active_tx[(job_id, batch_id)]
                    del active[path]
                    if not active:
                        del self._active_tx[(job_id, batch_id)]
            path.unlink(missing_ok=True)

    def _prepare_tx(self, job_id, batch_id, path):
        with self._db() as db:
            job = self._job(db, job_id)
            available = batch_id in self._inventory(db, job_id)
        manifest = self._stored_manifest(job)
        segment = _batch(manifest, batch_id)
        if not available:
            raise StoreError("BATCH_NOT_AVAILABLE")
        if job["role"] == "TARGET":
            self._target(job)
            if not job["allow_forward"]:
                raise StoreError("FORWARDING_NOT_ALLOWED")
            batch = self._batch_path(job_id, batch_id)
            state = self._batch_state(batch, manifest, batch_id)
            if state != "AVAILABLE":
                with self._db(write=True) as db:
                    self._invalidate(db, job_id, batch_id, state)
                raise StoreError("BATCH_NOT_AVAILABLE")
            # Pin the verified file while the worker uses it, even if the batch's
            # canonical path is later invalidated and replaced.
            os.link(batch, path)
            return
        snapshot = self._directory(job_id) / "source.bin"
        try:
            check_path(snapshot)
            with snapshot.open("rb") as incoming, path.open("xb") as outgoing:
                incoming.seek(segment.offset)
                self._copy_bytes(incoming, outgoing, segment.size)
        except (FileNotFoundError, ValueError, StoreError) as exc:
            state = "MISSING" if isinstance(exc, FileNotFoundError) else "CORRUPT"
            with self._db(write=True) as db:
                for index in self._inventory(db, job_id):
                    self._record_unavailable(db, job_id, index, state)
                self._snapshot(db, job_id)
            raise StoreError("BATCH_NOT_AVAILABLE") from exc
        if self._batch_state(path, manifest, batch_id) != "AVAILABLE":
            with self._db(write=True) as db:
                self._invalidate(db, job_id, batch_id, "CORRUPT")
            raise StoreError("BATCH_NOT_AVAILABLE")

    @staticmethod
    def _destination(path):
        path = local_absolute_path(Path(path), "Delivery path")
        if not path.name or ".." in path.parts:
            raise ValueError("Expected a file destination without parent traversal")
        check_path(path.parent, directory=True)
        return path

    @staticmethod
    def _delivery(db, job_id):
        return db.execute("SELECT * FROM delivery WHERE job_id = ?", (job_id,)).fetchone()

    def _delivery_stage(self, job_id, destination=None):
        marker = self._directory(job_id) / "delivery-stage.json"
        if destination is None:
            try:
                parent, token = json.loads(marker.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            return local_absolute_path(Path(parent), "Delivery staging parent") / f".ratatoss-{_uuid(token)}"
        token = str(uuid4())
        temporary = marker.with_suffix(".part")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump((str(destination.parent), token), stream)
            stream.flush()
            os.fsync(stream.fileno())
        publish(temporary, marker)
        return destination.parent / f".ratatoss-{token}"

    @staticmethod
    def _set_delivery(db, job_id, path, state):
        db.execute(
            """INSERT INTO delivery (job_id, intended_path, state, published_at_ms) VALUES (?, ?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET intended_path = excluded.intended_path,
               state = excluded.state, published_at_ms = excluded.published_at_ms""",
            (job_id, str(path), state, _now() if state == "PUBLISHED" else None),
        )

    @staticmethod
    def _receipt(manifest):
        return {"manifest_sha256": manifest.manifest_sha256(), "file_sha256": manifest.sha256,
                "size": manifest.size}

    def _commit_delivery(self, db, job_id, destination, receipt):
        self._set_delivery(db, job_id, destination, "PUBLISHED")
        self._enqueue(db, job_id, "RECEIPT", receipt)

    def publish_delivery(self, job_id: str, *, destination: Path | None = None) -> Path:
        """Assemble and publish a verified file on the user's volume."""
        job_id = _uuid(job_id)
        # Exclude other delivery operations and RX publication while assembly
        # reads the canonical files. TX can still pin and read those files.
        with self._job_lock(job_id, delivery=True):
            with self._job_lock(job_id), self._db() as db:
                job = self._job(db, job_id)
                self._target(job)
                delivery = self._delivery(db, job_id)
                inventory = self._inventory(db, job_id)
            manifest = self._stored_manifest(job)
            planned = Path(delivery["intended_path"])
            if delivery["state"] == "PUBLISHING" or job_id in self._deferred_deliveries:
                delivery = self._recover_delivery(job_id, manifest, delivery)
                if job_id in self._deferred_deliveries:
                    raise StoreError("DELIVERY_NOT_AVAILABLE")
            if delivery["state"] == "PUBLISHED":
                if destination is not None and Path(destination) != planned:
                    raise StoreError("DELIVERY_ALREADY_PUBLISHED")
                return planned
            if inventory != tuple(range(len(manifest.batches))):
                raise StoreError("BATCHES_INCOMPLETE")
            destination = self._destination(planned if destination is None else destination)
            if os.path.lexists(destination):
                with self._db(write=True) as db:
                    self._set_delivery(db, job_id, destination, "PATH_CONFLICT")
                raise StoreError("PATH_CONFLICT")
            self._clear_stage(job_id)
            stage = self._delivery_stage(job_id, destination)
            with self._db(write=True) as db:
                self._set_delivery(db, job_id, destination, "PUBLISHING")
            proof = stage / "verified.tmp"
            batches = {batch_id: self._batch_path(job_id, batch_id) for batch_id in inventory}
            try:
                stage.mkdir(mode=0o700)
                sync_directory(stage.parent)
                for batch_id, path in batches.items():
                    state = self._batch_state(path, manifest, batch_id)
                    if state != "AVAILABLE":
                        with self._job_lock(job_id), self._db(write=True) as db:
                            self._invalidate(db, job_id, batch_id, state)
                        raise StoreError("BATCH_NOT_AVAILABLE")
                temporary = assemble_batches(manifest, batches, stage)
                publish(temporary, proof)
                # The marker distinguishes an assembled file waiting to be moved
                # from a crash that happened before a verified file existed.
                marker = stage / "ready.part"
                with marker.open("xb") as stream:
                    os.fsync(stream.fileno())
                publish(marker, stage / "ready")
                publish(proof, destination)
            except FileExistsError as exc:
                self._recover_delivery(job_id, manifest, {
                    "intended_path": str(destination), "state": "PUBLISHING",
                })
                raise StoreError("PATH_CONFLICT") from exc
            except Exception as exc:
                try:
                    if isinstance(exc, BatchInputError):
                        with self._job_lock(job_id), self._db(write=True) as db:
                            self._invalidate(db, job_id, exc.batch_id, exc.state)
                finally:
                    self._recover_delivery(job_id, manifest, {
                        "intended_path": str(destination), "state": "PUBLISHING",
                    })
                raise
            receipt = self._receipt(manifest)
            with self._db(write=True) as db:
                self._commit_delivery(db, job_id, destination, receipt)
            self._clear_stage(job_id)
            return destination

    def _clear_stage(self, job_id):
        marker = self._directory(job_id) / "delivery-stage.json"
        marker.with_suffix(".part").unlink(missing_ok=True)
        stage = self._delivery_stage(job_id)
        if stage is None:
            return
        try:
            check_path(stage, directory=True)
        except FileNotFoundError:
            marker.unlink(missing_ok=True)
            return
        for pattern in ("verified.tmp", "ratatoss-assemble-*.tmp", "ready", "ready.part"):
            for path in stage.glob(pattern):
                path.unlink(missing_ok=True)
        if not any(stage.iterdir()):
            stage.rmdir()
        sync_directory(stage.parent)
        marker.unlink(missing_ok=True)
        sync_directory(marker.parent)

    def _recover_delivery(self, job_id, manifest, delivery):
        path = Path(delivery["intended_path"])
        if delivery["state"] == "PUBLISHING":
            stage = self._delivery_stage(job_id)
            try:
                owns_output = False
                if stage is not None and stage.parent == path.parent:
                    check_path(stage / "ready")
                    proof = stage / "verified.tmp"
                    check_path(path)
                    if os.path.lexists(proof):
                        check_path(proof)
                        owns_output = proof.samefile(path)
                    else:
                        owns_output = True
            except (ValueError, FileNotFoundError):
                owns_output = False
            except OSError:
                self._deferred_deliveries.add(job_id)
                return delivery
            state = "PATH_CONFLICT" if os.path.lexists(path) else "PLANNED"
            output_state = self._source_state(path, manifest) if owns_output else None
            if output_state == "UNREADABLE":
                self._deferred_deliveries.add(job_id)
                return delivery
            if output_state == "AVAILABLE":
                sync_directory(path.parent)
                receipt = self._receipt(manifest)
            with self._db(write=True) as db:
                if output_state == "AVAILABLE":
                    self._commit_delivery(db, job_id, path, receipt)
                else:
                    self._set_delivery(db, job_id, path, state)
        elif delivery["state"] == "PUBLISHED":
            with self._db() as db:
                pending = db.execute("SELECT 1 FROM outbox WHERE job_id = ? AND event_kind = 'RECEIPT'",
                                     (job_id,)).fetchone()
            output_state = self._source_state(path, manifest) if pending is not None else None
            if output_state == "UNREADABLE":
                self._deferred_deliveries.add(job_id)
                return delivery
            if output_state in ("MISSING", "CORRUPT"):
                state = "PATH_CONFLICT" if os.path.lexists(path) else "PLANNED"
                with self._db(write=True) as db:
                    db.execute("DELETE FROM outbox WHERE job_id = ? AND event_kind = 'RECEIPT'", (job_id,))
                    self._set_delivery(db, job_id, path, state)
        self._clear_stage(job_id)
        self._deferred_deliveries.discard(job_id)
        with self._db() as db:
            return self._delivery(db, job_id)

    @staticmethod
    def _enqueue(db, job_id, kind, payload, *, batch_id=None, assignment_id=None, boot_id=None):
        now = _now()
        db.execute(
            """INSERT INTO outbox (request_key, job_id, event_kind, batch_id, assignment_id,
                                   boot_id, payload_json, created_at_ms, next_attempt_at_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), job_id, kind, batch_id, assignment_id, boot_id,
             json.dumps(payload, separators=(",", ":")), now, now),
        )

    def _snapshot(self, db, job_id):
        db.execute(
            """DELETE FROM outbox WHERE job_id = ? AND event_kind = 'RECONCILE'
               AND (boot_id <> ? OR sent_boot_id IS NOT ?)""",
            (job_id, self.boot_id, self.boot_id),
        )
        self._enqueue(db, job_id, "RECONCILE", {
            "boot_id": self.boot_id, "verified_batch_ids": self._inventory(db, job_id),
        }, boot_id=self.boot_id)

    def pending_events(self, job_id: str) -> tuple[dict, ...]:
        """Replay an in-flight request from this boot before a replacement snapshot."""
        with self._db() as db:
            return tuple(dict(row) for row in self._ordered_events(db, _uuid(job_id)))

    def _ordered_events(self, db, job_id):
        return db.execute(
            """SELECT * FROM outbox WHERE job_id = ?
               AND (event_kind <> 'RECEIPT' OR ?)
               ORDER BY CASE
                   WHEN sent_boot_id = ? THEN 0 WHEN event_kind = 'RECONCILE' THEN 1
                   WHEN event_kind = 'ACK' THEN 2 ELSE 3 END,
                   event_id""",
            (job_id, job_id not in self._deferred_deliveries, self.boot_id),
        )

    def mark_event_sent(self, job_id: str, request_key: str) -> None:
        """Record the head event's sending boot before the network call.

        If a rescan changed the head, the sender must reload the outbox before
        sending. Retries retain the original timestamp, request key and payload.
        """
        job_id, request_key = map(_uuid, (job_id, request_key))
        with self._db(write=True) as db:
            head = self._ordered_events(db, job_id).fetchone()
            if head is None or head["request_key"] != request_key:
                raise StoreError("OUTBOX_HEAD_CHANGED")
            db.execute(
                """UPDATE outbox SET sent_boot_id = ?,
                   first_sent_at_ms = coalesce(first_sent_at_ms, max(created_at_ms, ?))
                   WHERE event_id = ?""",
                (self.boot_id, _now(), head["event_id"]),
            )

    def _scan_batches(self, job_id, manifest, source):
        snapshot = self._directory(job_id) / "source.bin"
        source_state = self._source_state(snapshot, manifest) if source else None
        batches = []
        for batch in manifest.batches:
            path = snapshot if source else self._batch_path(job_id, batch.index)
            state = source_state if source else self._batch_state(path, manifest, batch.index)
            batches.append((batch.index, path, state))
        return batches

    def _record_scan(self, db, job_id, batches, *, adopt):
        known_paths = set() if adopt else {
            row[0] for row in db.execute(
                "SELECT batch_id FROM local_batches WHERE job_id = ? AND storage_path IS NOT NULL",
                (job_id,),
            )
        }
        for batch_id, path, state in batches:
            known = adopt or batch_id in known_paths
            if state == "AVAILABLE":
                # A path temporarily blocked by a read error may be verified
                # again. Fresh live RX must still commit availability and ACK.
                if known:
                    self._set_batch(db, job_id, batch_id, path, state)
            else:
                self._record_unavailable(db, job_id, batch_id, state,
                                         read_retry_path=path if known else None)
        extra_batches = db.execute(
            "SELECT batch_id FROM local_batches WHERE job_id = ? AND batch_id >= ?",
            (job_id, len(batches)),
        ).fetchall()
        for (batch_id,) in extra_batches:
            self._record_unavailable(db, job_id, batch_id, "MISSING")

    def _discard_unregistered_sources(self, registered):
        for directory in self.jobs.iterdir():
            if directory.name in registered:
                continue
            try:
                if directory.name != _uuid(directory.name):
                    continue
                check_path(directory, directory=True)
            except (ValueError, FileNotFoundError):
                continue
            for name in ("source.part", "source.bin"):
                discard_staging(directory / name)
            sync_directory(directory)

    def _recover(self):
        with self._db() as db:
            jobs = db.execute("SELECT * FROM local_jobs").fetchall()
        self._discard_unregistered_sources({job["job_id"] for job in jobs})
        for job in jobs:
            if job["closed_at_ms"] is not None:
                continue
            job_id = _uuid(job["job_id"])
            if job_id != job["job_id"]:
                raise StoreError("INVALID_STORED_JOB_ID")
            manifest = self._stored_manifest(job)
            directory = self._prepare_directory(job_id)
            for pattern in ("rx-*.part", "tx-*.part", "source.part"):
                for path in directory.glob(pattern):
                    discard_staging(path)
            source = job["role"] == "SOURCE"
            batches = self._scan_batches(job_id, manifest, source)
            # A previous process may have linked the batch without syncing
            # this directory. Persist its entries before advertising them.
            sync_directory(directory)
            with self._db(write=True) as db:
                db.execute(
                    """UPDATE local_attempts SET state = 'CANCELED', closed_at_ms = max(created_at_ms, ?)
                       WHERE job_id = ? AND closed_at_ms IS NULL""",
                    (_now(), job_id),
                )
                self._record_scan(db, job_id, batches, adopt=True)
                delivery = self._delivery(db, job_id)
                if source or job["consent"] == "ACCEPT":
                    self._snapshot(db, job_id)
            if delivery is not None:
                self._recover_delivery(job_id, manifest, delivery)
