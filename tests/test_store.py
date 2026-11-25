from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from ratatoss import store as store_module
from ratatoss.database import NODE_DATABASE_NAME, open_database
from ratatoss.manifest import Manifest, Segment, build_manifest
from ratatoss.store import NodeStore, StoreError


# A real subprocess exit leaves the filesystem and SQLite in the tested window.
CRASH = """
import os
from pathlib import Path
import sys
from ratatoss import store

root, identifier, window, assignment = sys.argv[1:]
with store.NodeStore(Path(root)) as node:
    real_publish = store.publish
    def interrupt(source, destination):
        batch = destination.name == 'batch-0.bin'
        output = destination == Path(root).parent / 'delivered.bin'
        if (batch and window == 'before-batch-publish') or (output and window == 'before-delivery-publish'):
            os._exit(71)
        real_publish(source, destination)
        if (batch and window == 'after-batch-publish') or (output and window == 'after-delivery-publish'):
            os._exit(71)
    store.publish = interrupt
    if 'delivery' in window:
        node.publish_delivery(identifier)
    else:
        staging = node.begin_receive(identifier, 0, assignment)
        staging.write_bytes(b'abcdef')
        node.commit_receive(assignment)
        if window == 'after-batch-commit':
            os._exit(71)
raise AssertionError('Crash point was not reached')
"""


class NodeStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / f".tmp-store-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.data = self.root / "node"
        self.source = self.root / "sample.bin"
        self.source.write_bytes(b"abcdefghij")
        self.output = self.root / "delivered.bin"
        self.manifest = build_manifest(self.source, piece_size=3, batch_size=6)
        self.source_device = str(uuid4())
        self.job_id = str(uuid4())
        self.offer_id = str(uuid4())
        self.consent_key = str(uuid4())

    def register(self, store, manifest=None, *, forward=True):
        return store.register_target(
            self.job_id, self.source_device, self.offer_id,
            self.manifest if manifest is None else manifest, self.output,
            consent_request_key=self.consent_key, allow_forward=forward,
        )

    def stage(self, store, batch_id, payload):
        assignment = str(uuid4())
        staging = store.begin_receive(self.job_id, batch_id, assignment)
        staging.write_bytes(payload)
        return assignment, staging

    def receive(self, store, batch_id, payload):
        assignment, _ = self.stage(store, batch_id, payload)
        return store.commit_receive(assignment)

    def rows(self, query, args=()):
        with closing(open_database(self.data / NODE_DATABASE_NAME, "node")) as db:
            return db.execute(query, args).fetchall()

    def write_db(self, query, args=()):
        with closing(open_database(self.data / NODE_DATABASE_NAME, "node")) as db, db:
            db.execute(query, args)

    def outbox(self, store):
        return [(event["event_kind"], json.loads(event["payload_json"]))
                for event in store.pending_events(self.job_id)]

    def crash(self, window, *, assignment=""):
        run = subprocess.run(
            [sys.executable, "-B", "-c", CRASH, str(self.data), self.job_id, window, assignment],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(run.returncode, 71, run.stdout + run.stderr)

    def test_corrupt_batch_and_piece_hash_are_rejected(self):
        wrong_piece = replace(self.manifest.pieces[1], sha256=sha256(b"xxx").hexdigest())
        altered = replace(self.manifest, pieces=(self.manifest.pieces[0], wrong_piece,
                                                *self.manifest.pieces[2:]))
        with NodeStore(self.data) as store:
            self.register(store, altered)
            for payload in (b"abcxyz", b"abcdef"):
                assignment, staging = self.stage(store, 0, payload)
                with self.assertRaisesRegex(StoreError, "^CORRUPT$"):
                    store.commit_receive(assignment)
                self.assertFalse(staging.exists())
                self.assertEqual(store.inventory(self.job_id), ())
                self.assertEqual(self.outbox(store), [])
            self.assertEqual(self.rows("SELECT state FROM local_batches"), [("CORRUPT",)])
            self.assertEqual(self.rows("SELECT state FROM local_attempts"), [("FAILED",), ("FAILED",)])

    def test_duplicate_receive_and_retry_preserve_file_and_ack_identity(self):
        with NodeStore(self.data) as store:
            self.register(store)
            first, _ = self.stage(store, 0, b"abcdef")
            second, _ = self.stage(store, 0, b"abcdef")
            with ThreadPoolExecutor(max_workers=2) as pool:
                paths = list(pool.map(store.commit_receive, (first, second)))
            self.assertEqual(paths[0], paths[1])
            before = store.pending_events(self.job_id)
            self.assertEqual({event["assignment_id"] for event in before}, {first, second})
            self.assertEqual(store.commit_receive(first), paths[0])
            self.assertEqual(store.pending_events(self.job_id), before)
            with self.assertRaisesRegex(StoreError, "^CORRUPT$"):
                self.receive(store, 0, b"abcdef!")
            self.assertEqual(store.inventory(self.job_id), (0,))
            self.assertEqual(store.pending_events(self.job_id), before)
            with store.tx_batch(self.job_id, 0) as path:
                self.assertEqual(path.read_bytes(), b"abcdef")

    def test_source_import_is_immutable_and_duplicate_safe(self):
        with NodeStore(self.data) as store:
            with self.assertRaisesRegex(StoreError, "^SOURCE_TOO_LARGE$"):
                store.import_source(self.job_id, self.source_device, self.source, max_bytes=9)
            options = dict(max_bytes=10, piece_size=3, batch_size=6)
            self.assertEqual(store.import_source(self.job_id, self.source_device, self.source, **options),
                             self.manifest)
            snapshot = self.data / "jobs" / self.job_id / "source.bin"
            original = snapshot.stat()
            self.assertEqual(store.import_source(self.job_id, self.source_device, self.source, **options),
                             self.manifest)
            self.assertEqual(snapshot.stat().st_ino, original.st_ino)
            self.source.write_bytes(b"0123456789")
            with self.assertRaisesRegex(StoreError, "^JOB_CONFLICT$"):
                store.import_source(self.job_id, self.source_device, self.source, **options)
            self.assertEqual(store.inventory(self.job_id), (0, 1))
            with store.tx_batch(self.job_id, 1) as path:
                self.assertEqual(path.read_bytes(), b"ghij")
            self.assertFalse(path.exists())
            self.assertEqual(snapshot.read_bytes(), b"abcdefghij")

    def test_batch_publish_precedes_atomic_availability_and_ack(self):
        with NodeStore(self.data) as store:
            self.register(store)
            assignment, staging = self.stage(store, 0, b"abcdef")
            self.write_db("""CREATE TRIGGER abort_ack BEFORE INSERT ON outbox WHEN NEW.event_kind = 'ACK'
                             BEGIN SELECT RAISE(ABORT, 'test ACK failure'); END""")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "test ACK failure"):
                store.commit_receive(assignment)
            self.assertEqual(self.rows("SELECT state FROM local_batches"), [("MISSING",)])
            self.assertEqual(self.rows("SELECT state FROM local_attempts"), [("VERIFIED",)])
            self.assertEqual(self.outbox(store), [])
            self.assertFalse(staging.exists())
            self.assertEqual((staging.parent / "batch-0.bin").read_bytes(), b"abcdef")
            with self.assertRaisesRegex(StoreError, "^BATCH_NOT_AVAILABLE$"):
                with store.tx_batch(self.job_id, 0):
                    self.fail("TX opened before commit")
            self.write_db("DROP TRIGGER abort_ack")
            store.commit_receive(assignment)
            self.assertEqual(self.rows("SELECT state FROM local_batches"), [("AVAILABLE",)])
            self.assertEqual(self.rows("SELECT state FROM local_attempts"), [("FINISHED",)])
            self.assertEqual(self.outbox(store), [("ACK", {"batch_sha256": self.manifest.batches[0].sha256})])

    def assert_crash_recovery(self, window, *, published, committed):
        with NodeStore(self.data) as store:
            self.register(store)
        assignment = str(uuid4())
        self.crash(window, assignment=assignment)
        directory = self.data / "jobs" / self.job_id
        self.assertEqual((directory / "batch-0.bin").is_file(), published)
        self.assertEqual(self.rows("SELECT state FROM local_batches WHERE batch_id = 0"),
                         [("AVAILABLE" if committed else "MISSING",)])
        self.assertEqual(self.rows("SELECT count(*) FROM outbox WHERE event_kind = 'ACK'"), [(int(committed),)])
        with NodeStore(self.data) as store:
            self.assertEqual(store.inventory(self.job_id), (0,) if published else ())
            self.assertFalse((directory / f"rx-{assignment}.part").exists())
            self.assertEqual(self.rows("SELECT state FROM local_attempts"),
                             [("FINISHED" if committed else "CANCELED",)])
            events = self.outbox(store)
            self.assertEqual(events[0], ("RECONCILE", {
                "boot_id": store.boot_id, "verified_batch_ids": [0] if published else [],
            }))
            self.assertEqual([kind for kind, _ in events], ["RECONCILE", "ACK"] if committed else ["RECONCILE"])

    def test_crash_before_batch_publish_discards_uncommitted_staging(self):
        self.assert_crash_recovery("before-batch-publish", published=False, committed=False)

    def test_crash_after_batch_publish_adopts_file_via_reconcile(self):
        self.assert_crash_recovery("after-batch-publish", published=True, committed=False)
        with NodeStore(self.data) as store:
            self.receive(store, 1, b"ghij")
            self.assertEqual(store.publish_delivery(self.job_id), self.output)
            self.assertEqual(sha256(self.output.read_bytes()).hexdigest(), self.manifest.sha256)
            self.assertEqual(store.inventory(self.job_id), (0, 1))

    def test_crash_after_batch_commit_preserves_ack(self):
        self.assert_crash_recovery("after-batch-commit", published=True, committed=True)

    def test_reconcile_drops_acks_for_missing_and_corrupt_batches(self):
        with NodeStore(self.data) as store:
            self.register(store)
            missing = self.receive(store, 0, b"abcdef")
            corrupt = self.receive(store, 1, b"ghij")
        missing.unlink()
        corrupt.write_bytes(b"xxxx")
        with NodeStore(self.data) as store:
            self.assertEqual(store.inventory(self.job_id), ())
            self.assertEqual(self.rows("SELECT state FROM local_batches ORDER BY batch_id"),
                             [("MISSING",), ("CORRUPT",)])
            self.assertEqual([kind for kind, _ in self.outbox(store)], ["RECONCILE"])
            self.receive(store, 1, b"ghij")
            self.assertEqual(store.inventory(self.job_id), (1,))

    def test_live_corruption_revokes_tx_and_queues_corrected_inventory(self):
        with NodeStore(self.data) as store:
            self.register(store)
            path = self.receive(store, 0, b"abcdef")
            path.write_bytes(b"xxxxx!")
            with self.assertRaisesRegex(StoreError, "^BATCH_NOT_AVAILABLE$"):
                with store.tx_batch(self.job_id, 0):
                    self.fail("Corrupt batch was offered to TX")
            self.assertEqual(self.outbox(store), [("RECONCILE", {
                "boot_id": store.boot_id, "verified_batch_ids": [],
            })])
            self.assertEqual(store.inventory(self.job_id), ())

    def test_live_corruption_replays_an_inflight_ack_before_reconcile(self):
        with NodeStore(self.data) as store:
            self.register(store)
            path = self.receive(store, 0, b"abcdef")
            ack = store.pending_events(self.job_id)[0]
            self.write_db("UPDATE outbox SET first_sent_at_ms = created_at_ms WHERE event_id = ?",
                          (ack["event_id"],))
            path.unlink()
            with self.assertRaisesRegex(StoreError, "^BATCH_NOT_AVAILABLE$"):
                with store.tx_batch(self.job_id, 0):
                    self.fail("Missing batch was offered to TX")
            events = store.pending_events(self.job_id)
            self.assertEqual([event["event_kind"] for event in events], ["ACK", "RECONCILE"])
            self.assertEqual(events[0]["request_key"], ack["request_key"])
        with NodeStore(self.data) as store:
            self.assertEqual([kind for kind, _ in self.outbox(store)], ["RECONCILE"])

    def test_tx_keeps_a_file_reference_without_locking_out_another_receive(self):
        with NodeStore(self.data) as store:
            self.register(store)
            self.receive(store, 0, b"abcdef")
            with store.tx_batch(self.job_id, 0) as tx_path:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    received = pool.submit(self.receive, store, 1, b"ghij").result(timeout=5)
                self.assertEqual(received.read_bytes(), b"ghij")
                self.assertEqual(tx_path.read_bytes(), b"abcdef")
            self.assertFalse(tx_path.exists())

    def test_delivery_keeps_batches_and_never_overwrites_an_occupied_path(self):
        self.output.write_bytes(b"abcdefghij")
        with NodeStore(self.data) as store:
            self.register(store, forward=False)
            self.receive(store, 1, b"ghij")
            with self.assertRaisesRegex(StoreError, "^BATCHES_INCOMPLETE$"):
                store.publish_delivery(self.job_id)
            self.receive(store, 0, b"abcdef")
            with self.assertRaisesRegex(StoreError, "^FORWARDING_NOT_ALLOWED$"):
                with store.tx_batch(self.job_id, 0):
                    self.fail("TX opened without consent to forward")
            with self.assertRaisesRegex(StoreError, "^PATH_CONFLICT$"):
                store.publish_delivery(self.job_id)
            self.assertEqual(store.inventory(self.job_id), (0, 1))
            alternate = self.output.with_name("alternate.bin")
            original = self.output.stat()
            self.assertEqual(store.publish_delivery(self.job_id, destination=alternate), alternate)
            self.assertEqual(self.output.stat().st_ino, original.st_ino)
            self.assertEqual(sha256(alternate.read_bytes()).hexdigest(), self.manifest.sha256)
            self.assertEqual(store.publish_delivery(self.job_id), alternate)
            self.assertEqual(self.outbox(store)[-1], ("RECEIPT", {
                "manifest_sha256": self.manifest.manifest_sha256(),
                "file_sha256": self.manifest.sha256, "size": 10,
            }))

    def test_final_payload_digest_is_independent_of_batch_digests(self):
        wrong_whole = replace(self.manifest, sha256=sha256(b"x").hexdigest())
        with NodeStore(self.data) as store:
            self.register(store, wrong_whole)
            self.receive(store, 0, b"abcdef")
            self.receive(store, 1, b"ghij")
            with self.assertRaisesRegex(ValueError, "Assembled file SHA-256 mismatch"):
                store.publish_delivery(self.job_id)
            self.assertFalse(self.output.exists())
            self.assertEqual(store.inventory(self.job_id), (0, 1))
            self.assertEqual([kind for kind, _ in self.outbox(store)], ["ACK", "ACK"])

    def test_delivery_does_not_overwrite_a_file_created_during_publication(self):
        real_publish = store_module.publish

        def race(source, destination):
            if destination == self.output:
                destination.write_bytes(b"user file")
            return real_publish(source, destination)

        with NodeStore(self.data) as store:
            self.register(store)
            self.receive(store, 0, b"abcdef")
            self.receive(store, 1, b"ghij")
            with patch.object(store_module, "publish", race):
                with self.assertRaisesRegex(StoreError, "^PATH_CONFLICT$"):
                    store.publish_delivery(self.job_id)
            self.assertEqual(self.output.read_bytes(), b"user file")
            self.assertEqual(self.rows("SELECT state FROM delivery"), [("PATH_CONFLICT",)])
            self.assertEqual([kind for kind, _ in self.outbox(store)], ["ACK", "ACK"])

    def test_crash_after_final_publish_recovers_empty_file_and_receipt(self):
        self.source.write_bytes(b"")
        manifest = build_manifest(self.source)
        with NodeStore(self.data) as store:
            self.register(store, manifest)
        self.crash("after-delivery-publish")
        self.assertEqual(self.output.read_bytes(), b"")
        self.assertEqual(self.rows("SELECT state FROM delivery"), [("PUBLISHING",)])
        with NodeStore(self.data) as store:
            self.assertEqual(store.publish_delivery(self.job_id), self.output)
            self.assertEqual(self.rows("SELECT state FROM delivery"), [("PUBLISHED",)])
            self.assertEqual([kind for kind, _ in self.outbox(store)], ["RECONCILE", "RECEIPT"])
            self.assertFalse(list(self.root.glob(".ratatoss-*")))

    def test_crash_before_final_publish_does_not_adopt_an_identical_user_file(self):
        with NodeStore(self.data) as store:
            self.register(store)
            self.receive(store, 0, b"abcdef")
            self.receive(store, 1, b"ghij")
        self.crash("before-delivery-publish")
        self.output.write_bytes(b"abcdefghij")
        with NodeStore(self.data) as store:
            self.assertEqual(self.rows("SELECT state FROM delivery"), [("PATH_CONFLICT",)])
            self.assertNotIn("RECEIPT", [kind for kind, _ in self.outbox(store)])
            self.assertEqual(self.output.read_bytes(), b"abcdefghij")

    def test_restart_uses_canonical_digest_for_api_vector_and_separate_payload_hash(self):
        payload_digest = "de541afdc888a29e740aa4fb394b67ff725f17279e083812fc61b85af73276ee"
        metadata_digest = "166d130902115c21f249e2432f4cf605926cfdff345f38d573f13fea37e6b756"
        segment = Segment(0, 0, 17, payload_digest)
        manifest = Manifest("sample.txt", 17, 4 * 1024**2, 64 * 1024**2,
                            payload_digest, (segment,), (segment,))
        fields = json.loads(manifest.to_json())
        alternate = json.dumps(dict(reversed(list(fields.items())))).encode()
        with NodeStore(self.data) as store:
            self.register(store, manifest.to_json())
            self.assertEqual(self.rows("SELECT manifest_canonical, hex(manifest_sha256) FROM local_jobs"),
                             [(manifest.canonical_bytes(), metadata_digest.upper())])
        for raw in (manifest.to_json().encode(), alternate):
            self.write_db("UPDATE local_jobs SET manifest_canonical = ?", (raw,))
            with NodeStore(self.data) as store:
                self.assertEqual(self.register(store, alternate).manifest_sha256(), metadata_digest)
        with NodeStore(self.data) as store:
            self.receive(store, 0, b"Hello, Ratatoss!\n")
            self.assertEqual(store.publish_delivery(self.job_id), self.output)
            self.assertEqual(self.outbox(store)[-1], ("RECEIPT", {
                "manifest_sha256": metadata_digest, "file_sha256": payload_digest, "size": 17,
            }))
            self.assertEqual(sha256(self.output.read_bytes()).hexdigest(), payload_digest)
        self.write_db("UPDATE local_jobs SET manifest_sha256 = ?", (bytes.fromhex(payload_digest),))
        with self.assertRaisesRegex(StoreError, "^MANIFEST_DIGEST_MISMATCH$"):
            NodeStore(self.data)
