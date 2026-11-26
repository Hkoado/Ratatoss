"""Controller control-plane transaction tests through real SQLite connections."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from ratatoss.controller import connections, leases, schedule
from ratatoss.controller.config import ControllerConfig
from ratatoss.controller.registry import (
    OFFER_TTL_MS,
    Registry,
    RegistryError,
    parse_job,
)
from ratatoss.controller.runtime import ControllerRuntime
from ratatoss.database import open_database
from ratatoss.manifest import Manifest, Segment


def new_id():
    return str(uuid4())


def active_pair_id(db, first, second):
    low, high = sorted((first, second))
    row = db.execute(
        "SELECT pair_id FROM pairs WHERE device_low = ? AND device_high = ? AND state = 'ACTIVE'",
        (low, high),
    ).fetchone()
    return row[0] if row else None


class ControlStateTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.path = (Path(tmp) / "controller.sqlite3").resolve()
        self.now = 1_800_000_000_000
        self.source, self.target, self.peer = new_id(), new_id(), new_id()
        self.boots = {device: new_id() for device in (self.source, self.target, self.peer)}
        part = Segment(0, 0, 1, sha256(b"a").hexdigest())
        self.manifest = Manifest("payload.bin", 1, 1, 1, part.sha256, (part,), (part,))
        self.codes = leases.SessionCodes()
        self.profile = leases.LeaseProfile(100_000_000, 2200, 200, 200, 75_000, 75_000)
        self.schedule = schedule.FixedSchedule(
            routes={(self.source, self.target): "relay", (self.source, self.peer): "relay",
                    (self.target, self.peer): "relay", (self.peer, self.target): "relay"},
            link_slots={"relay": 4}, max_sessions=4,
        )
        with self.transaction() as registry:
            for device_id in self.boots:
                registry.db.execute(
                    "INSERT INTO devices (device_id, display_name, token_sha256, enrolled_at_ms) "
                    "VALUES (?, 'test-device', ?, ?)",
                    (device_id, sha256(device_id.encode()).digest(), self.now),
                )
            for device_id in (self.target, self.peer):
                registry.db.execute(
                    "INSERT INTO pairs (pair_id, opener_device_id, claimant_device_id, code_sha256, "
                    "comparison_code, opener_confirmed_at_ms, claimant_confirmed_at_ms, created_at_ms, "
                    "expires_at_ms, state) VALUES (?, ?, ?, ?, '000000', ?, ?, ?, ?, 'ACTIVE')",
                    (new_id(), self.source, device_id, sha256(new_id().encode()).digest(),
                     self.now, self.now, self.now, self.now + 1000),
                )

    @contextmanager
    def transaction(self):
        with closing(open_database(self.path, "controller")) as db, db:
            db.execute("BEGIN IMMEDIATE")
            yield Registry(db, self.now)

    def assert_status(self, status, run, *args):
        with self.assertRaises(RegistryError) as stopped:
            run(*args)
        self.assertEqual(stopped.exception.status, status)

    def create(self, registry, *targets):
        return registry.create_job(self.source, self.manifest, list(targets), active_pair_id)

    def approve(self, registry, job, index=0, *, forward=False):
        offer = job["offers"][index]
        registry.offer_decision(offer["target_device_id"], offer["offer_id"], {
            "decision": "ACCEPT", "manifest_sha256": job["manifest_sha256"], "allow_forward": forward,
        })

    def connect(self, registry, device_id, *, slots=2):
        connections.heartbeat(registry, device_id, self.boots[device_id], slots, slots, [])

    def reconcile(self, registry, device_id, job, batches):
        return connections.reconcile(
            registry, device_id, job["job_id"], self.boots[device_id], batches,
        )

    def prepare(self, registry):
        job = self.create(registry, self.target)
        self.approve(registry, job)
        for device in (self.source, self.target):
            self.connect(registry, device)
            self.reconcile(registry, device, job, [0] if device == self.source else [])
        return job

    def test_job_decoder_rejects_duplicate_envelope_and_segment_keys(self):
        envelope = json.dumps({"manifest": json.loads(self.manifest.to_json()),
                               "target_device_ids": [self.target]})
        for raw in (
            envelope[:-1] + ', "target_device_ids": []}',
            envelope.replace('"index": 0', '"index": 99, "index": 0', 1),
        ):
            with self.transaction() as registry:
                with self.assertRaises(RegistryError) as stopped:
                    manifest, targets = parse_job(raw.encode(), max_bytes=4096, max_targets=4)
                    registry.create_job(self.source, manifest, targets, active_pair_id)
                self.assertEqual(stopped.exception.status, 400)
                for table in ("jobs", "job_batches", "offers"):
                    self.assertEqual(registry.row(f"SELECT count(*) AS count FROM {table}")["count"], 0)
        manifest, targets = parse_job(envelope.encode(), max_bytes=4096, max_targets=4)
        self.assertEqual((manifest, targets), (self.manifest, [self.target]))

    def test_target_scope_and_pending_consent(self):
        with self.transaction() as registry:
            job = self.create(registry, self.target, self.peer)
            offer_id = job["offers"][0]["offer_id"]
            self.assertEqual(registry.get_offer(self.target, offer_id)["manifest_sha256"],
                             self.manifest.manifest_sha256())
            self.assert_status(404, registry.get_offer, self.peer, offer_id)
            self.assertEqual([item["offer_id"] for item in registry.list_offers(self.target)["offers"]],
                             [offer_id])
            self.assertEqual(len(registry.job_status(self.source, job["job_id"])["targets"]), 2)
            self.assertNotIn("targets", registry.job_status(self.target, job["job_id"]))
            for device in (self.source, self.target):
                self.connect(registry, device)
            self.reconcile(registry, self.source, job, [0])
            self.assert_status(409, self.reconcile, registry, self.target, job, [])
            self.assertEqual(schedule.issue_assignments(registry, self.schedule), [])

    def test_wrong_digest_and_expiry_are_distinct(self):
        with self.transaction() as registry:
            job = self.create(registry, self.target)
            offer_id = job["offers"][0]["offer_id"]
            body = {"decision": "ACCEPT", "manifest_sha256": "0" * 64, "allow_forward": False}
            self.assert_status(409, registry.offer_decision, self.target, offer_id, body)
            self.assertEqual(registry.get_offer(self.target, offer_id)["state"], "PENDING")
        self.now += OFFER_TTL_MS
        with self.transaction() as registry:
            self.assert_status(410, registry.offer_decision, self.target, offer_id, body)
        with self.transaction() as registry:
            self.assertEqual(registry.row("SELECT state FROM offers")["state"], "EXPIRED")
            self.assertEqual(registry.job_status(self.source, job["job_id"])["state"], "NO_DELIVERY")

    def test_pair_revocation_preserves_consent_already_granted(self):
        with self.transaction() as registry:
            accepted = self.create(registry, self.target)
            self.approve(registry, accepted)
            pending = self.create(registry, self.target)
            pair_id = active_pair_id(registry.db, self.source, self.target)
            self.assert_status(404, registry.revoke_pair, self.peer, pair_id)
            registry.revoke_pair(self.target, pair_id)
            self.assertEqual(registry.get_offer(self.target, accepted["offers"][0]["offer_id"])["state"],
                             "ACCEPTED")
            self.assertEqual(registry.get_offer(self.target, pending["offers"][0]["offer_id"])["state"],
                             "REVOKED")
            self.assert_status(404, self.create, registry, self.target)

    def test_competing_schedulers_issue_one_live_lease(self):
        with self.transaction() as registry:
            self.prepare(registry)
        barrier = Barrier(2)

        def tick():
            barrier.wait(5)
            with self.transaction() as registry:
                return schedule.issue_assignments(registry, self.schedule)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: tick(), range(2)))
        self.assertEqual(sorted(map(len, results)), [0, 1])

    def test_ready_requires_budget_and_replays_without_extending(self):
        with self.transaction() as registry:
            self.prepare(registry)
            assignment, = schedule.issue_assignments(registry, self.schedule)
            self.assert_status(409, leases.ready, registry, self.target, assignment, self.codes, {})
            self.assertIsNone(self.codes.get(assignment, self.now))
            self.assertEqual(registry.row("SELECT state FROM assignments")["state"], "OFFERED")
            self.assert_status(404, leases.ready, registry, self.source, assignment, self.codes, {"relay": self.profile})
            ready = leases.ready(registry, self.target, assignment, self.codes, {"relay": self.profile})
            code = ready["croc_code"]
        self.now += 1000
        with self.transaction() as registry:
            again = leases.ready(registry, self.target, assignment, self.codes, {"relay": self.profile}, replay=True)
            self.assertEqual((again["croc_code"], again["lease_expires_at"]),
                             (code, ready["lease_expires_at"]))
            self.assertEqual(again["lease_remaining_ms"], ready["lease_remaining_ms"] - 1000)
            self.assertNotIn("croc_code", leases.list_assignments(registry, self.target, self.codes)["assignments"][0])
            self.assertEqual(leases.list_assignments(registry, self.source, self.codes)["assignments"][0]["croc_code"], code)
            self.assertEqual(leases.list_assignments(registry, self.peer, self.codes)["assignments"], [])
        self.assertNotIn(code.encode(), self.path.read_bytes())

    def test_ack_replay_does_not_restore_reconciled_batch(self):
        with self.transaction() as registry:
            job = self.prepare(registry)
            assignment, = schedule.issue_assignments(registry, self.schedule)
            leases.ready(registry, self.target, assignment, self.codes, {"relay": self.profile})
            self.assert_status(409, leases.ack, registry, self.target, assignment, "0" * 64)
            result = leases.ack(registry, self.target, assignment, self.manifest.batches[0].sha256)
            self.assertEqual(result["outcome"], "ACKED")
            self.reconcile(registry, self.target, job, [])
            self.assertEqual(leases.ack(registry, self.target, assignment, self.manifest.batches[0].sha256), result)
            self.assertEqual(registry.rows("SELECT * FROM inventory WHERE device_id = ?", (self.target,)), [])
            self.assertEqual(len(registry.rows("SELECT * FROM audit")), 1)

    def test_late_ack_changes_inventory_but_not_replacement_lease(self):
        with self.transaction() as registry:
            self.prepare(registry)
            first, = schedule.issue_assignments(registry, self.schedule)
            short = leases.LeaseProfile(100_000_000, 0, 0, 0, 1000, 1000)
            leases.ready(registry, self.target, first, self.codes, {"relay": short})
        self.now += 1000
        with self.transaction() as registry:
            second, = schedule.issue_assignments(registry, self.schedule)
            result = leases.ack(registry, self.target, first, self.manifest.batches[0].sha256)
            self.assertEqual(result["outcome"], "LATE_ACKNOWLEDGED")
            self.assertEqual(registry.row("SELECT state FROM assignments WHERE assignment_id = ?", (first,))["state"], "EXPIRED")
            self.assertEqual(registry.row("SELECT state FROM assignments WHERE assignment_id = ?", (second,))["state"], "OFFERED")
            self.assertEqual(schedule.issue_assignments(registry, self.schedule), [])
            self.assertEqual(registry.row("SELECT state FROM assignments WHERE assignment_id = ?", (second,))["state"], "CANCELED")

    def test_offline_reconnect_requires_reconcile_and_rejects_old_ack(self):
        with self.transaction() as registry:
            job = self.prepare(registry)
            first, = schedule.issue_assignments(registry, self.schedule)
            leases.ready(registry, self.target, first, self.codes, {"relay": self.profile})
        self.now += 20_000
        with self.transaction() as registry:
            self.assertEqual(schedule.issue_assignments(registry, self.schedule), [])
            self.assertEqual(registry.row("SELECT state FROM assignments")["state"], "CANCELED")
            old_boot = self.boots[self.target]
            self.boots[self.target] = new_id()
            self.connect(registry, self.source)
            self.connect(registry, self.target)
            self.assertEqual(schedule.issue_assignments(registry, self.schedule), [])
            self.assert_status(409, connections.reconcile, registry, self.target, job["job_id"], old_boot, [])
            self.reconcile(registry, self.source, job, [0])
            self.reconcile(registry, self.target, job, [])
            self.assert_status(409, leases.ack, registry, self.target, first, self.manifest.batches[0].sha256)
            second, = schedule.issue_assignments(registry, self.schedule)
            self.assertNotEqual(first, second)

    def test_lan_forward_requires_verified_inventory_and_forward_consent(self):
        fixed = schedule.FixedSchedule(
            self.schedule.routes, self.schedule.link_slots, 4, (self.target, self.peer),
        )
        with self.transaction() as registry:
            job = self.create(registry, self.target, self.peer)
            self.approve(registry, job, 0, forward=True)
            self.approve(registry, job, 1)
            for device in (self.source, self.target, self.peer):
                self.connect(registry, device)
                self.reconcile(registry, device, job, [0] if device == self.source else [])
            first, = schedule.issue_assignments(registry, fixed)
            self.assertEqual(registry.row("SELECT target_device_id FROM assignments")["target_device_id"],
                             self.target)
            leases.ready(registry, self.target, first, self.codes, {"relay": self.profile})
            leases.ack(registry, self.target, first, self.manifest.batches[0].sha256)
            second, = schedule.issue_assignments(registry, fixed)
            self.assertEqual(registry.row("SELECT source_device_id FROM assignments WHERE assignment_id = ?",
                                          (second,))["source_device_id"], self.target)
            self.reconcile(registry, self.target, job, [])
            self.assertEqual(registry.row("SELECT state FROM assignments WHERE assignment_id = ?",
                                          (second,))["state"], "CANCELED")

    def test_receipt_closes_job_and_replays(self):
        with self.transaction() as registry:
            job = self.prepare(registry)
            body = {"manifest_sha256": job["manifest_sha256"], "file_sha256": self.manifest.sha256, "size": 1}
            self.assert_status(409, registry.receipt, self.target, job["job_id"], body)
            self.reconcile(registry, self.target, job, [0])
            receipt = registry.receipt(self.target, job["job_id"], body)
            self.assertEqual(registry.job_status(self.source, job["job_id"])["state"], "COMPLETE")
            self.assertEqual(registry.receipt(self.target, job["job_id"], body), receipt)

    def test_restart_invalidates_live_code_and_requires_fresh_heartbeats(self):
        with self.transaction() as registry:
            self.prepare(registry)
            assignment, = schedule.issue_assignments(registry, self.schedule)
            leases.ready(registry, self.target, assignment, self.codes, {"relay": self.profile})
        with self.transaction() as registry:
            leases.reset_connections(registry)
            self.assertEqual(leases.list_assignments(registry, self.source, self.codes)["assignments"], [])
            self.assertEqual(schedule.issue_assignments(registry, self.schedule), [])
            self.assertEqual(registry.row("SELECT state FROM assignments")["state"], "CANCELED")

    def test_withdraw_cancels_active_lease_and_blocks_late_ack(self):
        with self.transaction() as registry:
            job = self.prepare(registry)
            assignment, = schedule.issue_assignments(registry, self.schedule)
            leases.ready(registry, self.target, assignment, self.codes, {"relay": self.profile})
            registry.withdraw_offer(self.target, job["offers"][0]["offer_id"])
            self.assertEqual(registry.row("SELECT state FROM assignments")["state"], "CANCELED")
            self.assert_status(409, leases.ack, registry, self.target, assignment, self.manifest.sha256)
            self.assertEqual(registry.job_status(self.source, job["job_id"])["state"], "NO_DELIVERY")

    def test_simultaneous_croc_codes_use_different_legacy_rooms(self):
        codes = leases.SessionCodes()
        first = codes.issue(new_id(), self.now + 1000)
        second = codes.issue(new_id(), self.now + 1000)
        self.assertNotEqual(first[:4], second[:4])
        self.assertTrue(all(code[4] == "-" and len(code[5:]) == 32 for code in (first, second)))

    def test_runtime_resets_and_commits_scheduler_work(self):
        runtime = ControllerRuntime(
            self.path, ControllerConfig(self.schedule, {"relay": self.profile}),
            clock=lambda: self.now,
        )
        runtime.startup()
        with runtime.transaction() as registry:
            self.prepare(registry)
        assignment, = runtime.tick()
        with self.transaction() as registry:
            state = registry.row("SELECT state FROM assignments WHERE assignment_id = ?", (assignment,))
            self.assertEqual(state["state"], "OFFERED")
        runtime.startup()
        self.assertEqual(runtime.tick(), [])
        with self.transaction() as registry:
            state = registry.row("SELECT state FROM assignments WHERE assignment_id = ?", (assignment,))
            self.assertEqual(state["state"], "CANCELED")

    def test_runtime_rolls_back_unexpected_errors(self):
        runtime = ControllerRuntime(
            self.path, ControllerConfig(self.schedule, {}),
            clock=lambda: self.now,
        )
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with runtime.transaction() as registry:
                self.create(registry, self.target)
                raise RuntimeError("rollback")
        with self.transaction() as registry:
            self.assertFalse(registry.rows("SELECT job_id FROM jobs"))

    def test_config_loads_routes_and_relative_benchmark_reference(self):
        profile_path = self.path.parent / "batch-profiles.json"
        profile_path.write_text(json.dumps({"profiles": {"64": {
            "min_goodput_bps": 100_000_000,
            "setup_budget_ms": 2200,
            "verify_commit_ms": 200,
            "margin_ms": 200,
            "lease_ms": 75_000,
            "adapter_timeout_ms": 75_000,
            "basis": "fixture",
        }}}), encoding="utf-8")
        path = self.path.parent / "controller.toml"
        path.write_text(f"""
max_sessions = 4
lan_peers = ["{self.target}", "{self.peer}"]

[links.lab]
max_sessions = 2
benchmark = {{ path = "batch-profiles.json", profile = "64" }}

[[routes]]
source = "{self.source}"
target = "{self.target}"
link = "lab"
""", encoding="utf-8")
        config = ControllerConfig.load(path)
        self.assertEqual(config.schedule.routes[self.source, self.target], "lab")
        self.assertEqual(config.schedule.link_slots["lab"], 2)
        self.assertTrue(config.lease_profiles["lab"].fits(64 * 1024**2))

    def test_config_rejects_bad_route_and_accepts_link_without_budget(self):
        path = self.path.parent / "controller.toml"
        source = f"""
max_sessions = 1

[links.lab]
max_sessions = 1

[[routes]]
source = "{self.source}"
target = "{self.target}"
link = "testing"
"""
        path.write_text(source, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown link"):
            ControllerConfig.load(path)
        path.write_text(source.replace('"testing"', '"lab"'), encoding="utf-8")
        self.assertFalse(ControllerConfig.load(path).lease_profiles)
