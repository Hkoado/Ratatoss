"""Controller CLI and the composed enrollment, consent and assignment APIs."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_controller_pairing as pairing_tests
from ratatoss.__main__ import main
from ratatoss.controller.config import ControllerConfig
from ratatoss.controller.leases import LeaseProfile
from ratatoss.controller.runtime import ControllerRuntime
from ratatoss.controller.schedule import FixedSchedule
from ratatoss.controller.service import create_service
from ratatoss.database import open_database
from ratatoss.manifest import Manifest, Segment


def cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, "argv", ["ratatoss", *args]), redirect_stdout(stdout), redirect_stderr(stderr):
        status = main()
    return status, stdout.getvalue(), stderr.getvalue()


class ControllerCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.database = self.root / "controller.sqlite3"

    def test_issue_enrollment_outputs_one_code_and_stores_only_its_hash(self):
        status, out, stderr = cli("controller", "issue-enrollment", "--db", str(self.database))
        self.assertEqual((status, stderr), (0, ""))
        self.assertRegex(out, r"\A[0-9a-f]{64}\n\Z")
        with closing(open_database(self.database, "controller")) as db:
            digest, issued, expires = db.execute(
                "SELECT code_sha256, issued_at_ms, expires_at_ms FROM enrollments"
            ).fetchone()
            self.assertEqual(digest, sha256(out.strip().encode("ascii")).digest())
            self.assertEqual(expires - issued, 600_000)

    def test_serve_uses_https_and_rejects_extra_key_file_bytes(self):
        config = self.root / "controller.toml"
        key = self.root / "pair-key.hex"
        config.write_text("max_sessions = 1\nroutes = []\n[links]\n", encoding="utf-8")
        args = (
            "controller", "serve", "--db", str(self.database), "--config", str(config),
            "--pair-key-file", str(key), "--ssl-certfile", str(self.root / "cert.pem"),
            "--ssl-keyfile", str(self.root / "key.pem"),
        )
        with patch("uvicorn.run") as serve:
            key.write_bytes(b"c" * 64 + b"\n\n\nextra")
            status, out, err = cli(*args)
            self.assertEqual((status, out), (2, ""))
            self.assertIn("Pair key file", err)
            serve.assert_not_called()

            key.write_bytes(b"c" * 64 + b"\r\n")
            self.assertEqual(cli(*args), (0, "", ""))
            self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
            self.assertEqual(serve.call_args.kwargs["port"], 9443)
            self.assertEqual(serve.call_args.kwargs["ssl_certfile"], str(self.root / "cert.pem"))
            self.assertEqual(serve.call_args.kwargs["ssl_keyfile"], str(self.root / "key.pem"))


class ControllerServiceTests(pairing_tests.ControllerTestCase):
    def start_server(self):
        self.routes = {}
        profile = LeaseProfile(100_000_000, 2200, 200, 200, 75_000, 75_000)
        self.runtime = ControllerRuntime(
            self.db_path, ControllerConfig(FixedSchedule(self.routes, {"loopback": 2}, 2),
                                           {"loopback": profile}),
            clock=self.clock,
        )
        app = create_service(self.runtime, pair_code_key=pairing_tests.CODE_KEY, tick_seconds=60)
        return pairing_tests.ControllerServer(self.db_path, self.clock, app=app)

    def test_enroll_pair_and_deliver_job_through_production_routes(self):
        with patch("ratatoss.controller.service.wall_clock_ms", self.clock):
            status, code, stderr = cli("controller", "issue-enrollment", "--db", str(self.db_path))
        self.assertEqual((status, stderr), (0, ""))
        self.secrets.append(code.strip())
        status, source, _ = self.http("POST", "/v1/devices/enroll",
                                      body={"enrollment_code": code.strip(), "display_name": "Atlas"})
        self.assertEqual(status, 201)
        self.secrets.append(source["device_token"])
        target = self.enroll("Birch")
        source_id, target_id = source["device_id"], target["device_id"]
        self.routes[source_id, target_id] = "loopback"

        def send(method, path, device, *, body=None, want=200):
            status, result, _ = self.http(method, path, token=device["device_token"],
                                          key=str(uuid4()) if method != "GET" else None, body=body)
            self.assertEqual(status, want)
            return result

        payload_hash = sha256(b"a").hexdigest()
        segment = Segment(0, 0, 1, payload_hash)
        manifest = Manifest("sample.txt", 1, 1, 1, payload_hash, (segment,), (segment,))
        request = {"manifest": json.loads(manifest.to_json()), "target_device_ids": [target_id]}
        send("POST", "/v1/jobs", source, body=request, want=404)
        self.activate(source, target)
        job = send("POST", "/v1/jobs", source, body=request, want=201)
        job_id = job["job_id"]
        offer_id = job["offers"][0]["offer_id"]
        self.assertEqual(send("GET", "/v1/offers", source), {"offers": []})
        self.assertEqual(self.runtime.tick(), [])
        send("POST", f"/v1/offers/{offer_id}/decision", target, body={
            "decision": "ACCEPT", "allow_forward": False, "manifest_sha256": job["manifest_sha256"],
        })
        for device in (source, target):
            boot = str(uuid4())
            send("POST", "/v1/devices/me/heartbeat", device, body={
                "boot_id": boot, "free_rx_slots": 1, "free_tx_slots": 1, "active_assignment_ids": [],
            })
            send("POST", f"/v1/jobs/{job_id}/reconcile", device, body={
                "boot_id": boot, "verified_batch_ids": [0] if device == source else [],
            })
        assignment, = self.runtime.tick()
        ready = send("POST", f"/v1/assignments/{assignment}/ready", target)
        self.secrets.append(ready["croc_code"])
        tx = send("GET", "/v1/devices/me/assignments", source)["assignments"][0]
        self.assertEqual(tx["croc_code"], ready["croc_code"])
        ack = send("POST", f"/v1/assignments/{assignment}/ack", target, body={"batch_sha256": payload_hash})
        self.assertEqual(ack["outcome"], "ACKED")
        send("POST", f"/v1/jobs/{job_id}/receipt", target, body={
            "manifest_sha256": job["manifest_sha256"], "file_sha256": payload_hash, "size": 1,
        })
        result = send("GET", f"/v1/jobs/{job_id}/status", source)
        self.assertEqual((result["state"], result["targets"][0]["verified_bytes"]), ("COMPLETE", 1))
        self.assert_no_raw_secrets_in_database()
