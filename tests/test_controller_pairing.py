"""Enrollment, authentication and two-way pairing over real HTTP and SQLite."""

import hashlib
import http.client
import json
import re
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from contextlib import closing
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ratatoss.controller import (
    active_pair_id,
    active_peer_ids,
    authenticate,
    create_router,
    issue_enrollment_code,
)
from ratatoss.controller.pairing import pair_code
from ratatoss.controller.ratelimit import RateLimiter
from ratatoss.database import open_database

START_MS = 1_800_000_000_000
TTL_MS = 10 * 60 * 1000
CODE_KEY = b"k" * 32  # Synthetic key for tests.
HEX64 = re.compile(r"[0-9a-f]{64}")
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


class Clock:
    def __init__(self):
        self.now_ms = START_MS

    def __call__(self) -> int:
        return self.now_ms


class ControllerServer:
    """Serve the pairing router on an ephemeral loopback port."""

    def __init__(self, db_path: Path, clock: Clock, **router_options):
        self.on_connect = None  # Optional hook run on each request's connection.

        def connect():
            connection = open_database(db_path, "controller")
            if self.on_connect is not None:
                self.on_connect(connection)
            return connection

        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.include_router(create_router(
            connect=connect,
            pair_code_key=CODE_KEY, clock=clock, **router_options,
        ))
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        self.port = listener.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [listener]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("Controller test server did not start")
            time.sleep(0.01)

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def request(self, method, path, *, token=None, key=None, body=None, raw=None,
                headers=None):
        request_headers = dict(headers or {})
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        if key is not None:
            request_headers["Idempotency-Key"] = key
        payload = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        with closing(http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)) as connection:
            connection.request(method, path, body=payload, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else None, response


class ControllerTestCase(unittest.TestCase):
    router_options: dict = {}

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "controller.sqlite3"
        self.db = open_database(self.db_path, "controller")
        self.addCleanup(self.db.close)
        self.clock = Clock()
        self.server = ControllerServer(self.db_path, self.clock, **self.router_options)
        self.addCleanup(self.server.close)
        self.secrets: list[str] = []

    def http(self, *args, **kwargs):
        return self.server.request(*args, **kwargs)

    def enroll(self, name):
        code = issue_enrollment_code(self.db, now_ms=self.clock())
        status, body, _ = self.http("POST", "/v1/devices/enroll",
                                    body={"enrollment_code": code, "display_name": name})
        self.assertEqual(status, 201, body)
        self.secrets += [code, body["device_token"]]
        return body

    def open_pair(self, device, key=None):
        status, body, _ = self.http("POST", "/v1/pairs", token=device["device_token"],
                                    key=key or str(uuid.uuid4()))
        self.assertEqual(status, 201, body)
        self.secrets.append(body["pair_code"])
        return body

    def claim(self, device, code, key=None):
        return self.http("POST", "/v1/pairs/claim", token=device["device_token"],
                         key=key or str(uuid.uuid4()), body={"pair_code": code})

    def decide(self, device, pair_id, decision="CONFIRM", key=None):
        return self.http("POST", f"/v1/pairs/{pair_id}/decision", token=device["device_token"],
                         key=key or str(uuid.uuid4()), body={"decision": decision})

    def pairs(self, device):
        status, body, _ = self.http("GET", "/v1/pairs", token=device["device_token"])
        self.assertEqual(status, 200, body)
        return body["pairs"]

    def pair_row(self, pair_id):
        self.db.row_factory = sqlite3.Row
        try:
            return self.db.execute("SELECT * FROM pairs WHERE pair_id = ?", (pair_id,)).fetchone()
        finally:
            self.db.row_factory = None

    def activate(self, a, b):
        opened = self.open_pair(a)
        self.assertEqual(self.claim(b, opened["pair_code"])[0], 200)
        self.assertEqual(self.decide(a, opened["pair_id"])[0], 200)
        status, body, _ = self.decide(b, opened["pair_id"])
        self.assertEqual((status, body["state"]), (200, "ACTIVE"))
        return opened["pair_id"]

    def assert_error(self, result, status, code):
        self.assertEqual(result[0], status, result[1])
        self.assertEqual(result[1]["error"]["code"], code)

    def assert_no_raw_secrets_in_database(self):
        dump = "\n".join(self.db.iterdump())
        for value in self.secrets:
            self.assertNotIn(value, dump)


class EnrollmentTests(ControllerTestCase):
    def test_enrollment_consumes_code_once_in_device_transaction(self):
        code = issue_enrollment_code(self.db, now_ms=START_MS)
        self.secrets.append(code)
        self.clock.now_ms = START_MS + 1234
        status, body, response = self.http(
            "POST", "/v1/devices/enroll", body={"enrollment_code": code, "display_name": "Atlas"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertRegex(body["device_id"], UUID4)
        self.assertRegex(body["device_token"], HEX64)
        self.assertEqual(body["display_name"], "Atlas")
        self.secrets.append(body["device_token"])

        consumed_at, device_id = self.db.execute(
            "SELECT consumed_at_ms, device_id FROM enrollments WHERE code_sha256 = ?",
            (hashlib.sha256(code.encode()).digest(),),
        ).fetchone()
        self.assertEqual((consumed_at, device_id), (START_MS + 1234, body["device_id"]))
        stored = self.db.execute(
            "SELECT token_sha256, enrolled_at_ms FROM devices WHERE device_id = ?", (device_id,),
        ).fetchone()
        self.assertEqual(stored, (hashlib.sha256(body["device_token"].encode()).digest(), START_MS + 1234))

        reused = self.http("POST", "/v1/devices/enroll",
                           body={"enrollment_code": code, "display_name": "Copy"})
        self.assert_error(reused, 404, "NOT_FOUND")
        self.assertEqual(self.db.execute("SELECT count(*) FROM devices").fetchone()[0], 1)
        self.assert_no_raw_secrets_in_database()

    def test_concurrent_enrollments_consume_a_code_once(self):
        code = issue_enrollment_code(self.db, now_ms=START_MS)
        results = []
        gate = threading.Barrier(6)

        def enroll(index):
            gate.wait()
            results.append(self.http("POST", "/v1/devices/enroll",
                                     body={"enrollment_code": code, "display_name": f"Node {index}"})[0])

        threads = [threading.Thread(target=enroll, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [201] + [404] * 5)
        self.assertEqual(self.db.execute("SELECT count(*) FROM devices").fetchone()[0], 1)

    def test_expired_and_unknown_codes_fail_without_creating_devices(self):
        expired = issue_enrollment_code(self.db, now_ms=START_MS)
        self.clock.now_ms = START_MS + TTL_MS  # TTL is exclusive.
        for code in (expired, "f" * 64):
            with self.subTest(code=code[:4]):
                result = self.http("POST", "/v1/devices/enroll",
                                   body={"enrollment_code": code, "display_name": "Late"})
                self.assert_error(result, 404, "NOT_FOUND")
        self.assertEqual(self.db.execute("SELECT count(*) FROM devices").fetchone()[0], 0)
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM enrollments WHERE consumed_at_ms IS NOT NULL").fetchone()[0], 0,
        )

    def test_each_device_receives_and_reads_a_separate_identity(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        self.assertNotEqual(atlas["device_id"], birch["device_id"])
        self.assertNotEqual(atlas["device_token"], birch["device_token"])
        for device in (atlas, birch):
            status, body, _ = self.http("GET", "/v1/devices/me", token=device["device_token"])
            self.assertEqual(status, 200)
            self.assertEqual(body, {"device_id": device["device_id"], "display_name": device["display_name"]})

    def test_malformed_enrollment_requests_are_rejected(self):
        code = issue_enrollment_code(self.db, now_ms=START_MS)
        cases = {
            "extra field": json.dumps({"enrollment_code": code, "display_name": "A", "x": 1}).encode(),
            "missing name": json.dumps({"enrollment_code": code}).encode(),
            "empty name": json.dumps({"enrollment_code": code, "display_name": ""}).encode(),
            "uppercase code": json.dumps({"enrollment_code": code.upper(), "display_name": "A"}).encode(),
            "duplicate key": f'{{"enrollment_code":"{code}","display_name":"A","display_name":"B"}}'.encode(),
            "lone surrogate": f'{{"enrollment_code":"{code}","display_name":"\\ud800"}}'.encode(),
            "invalid utf-8": f'{{"enrollment_code":"{code}","display_name":"'.encode() + b'\xff"}',
            "array": b"[]",
        }
        for name, raw in cases.items():
            with self.subTest(name):
                self.assert_error(self.http("POST", "/v1/devices/enroll", raw=raw), 400, "INVALID_REQUEST")
        wrong_type = self.http("POST", "/v1/devices/enroll", raw=cases["missing name"],
                               headers={"Content-Type": "text/plain"})
        self.assert_error(wrong_type, 400, "INVALID_REQUEST")
        self.assertEqual(self.db.execute("SELECT count(*) FROM devices").fetchone()[0], 0)


class AuthenticationTests(ControllerTestCase):
    def test_missing_malformed_unknown_and_revoked_tokens_are_rejected(self):
        atlas = self.enroll("Atlas")
        token = atlas["device_token"]
        cases = {
            "missing": {},
            "wrong scheme": {"Authorization": f"Basic {token}"},
            "short token": {"Authorization": f"Bearer {token[:-1]}"},
            "uppercase token": {"Authorization": f"Bearer {token.upper()}"},
            "unknown token": {"Authorization": f"Bearer {'e' * 64}"},
        }
        for name, headers in cases.items():
            for method, path in (("GET", "/v1/devices/me"), ("GET", "/v1/pairs"),
                                 ("POST", "/v1/pairs")):
                with self.subTest(name, path=path, method=method):
                    result = self.http(method, path, headers=headers, key=str(uuid.uuid4()))
                    self.assert_error(result, 401, "UNAUTHENTICATED")

        self.db.execute("UPDATE devices SET revoked_at_ms = ? WHERE device_id = ?", (START_MS, atlas["device_id"]))
        self.db.commit()
        self.assert_error(self.http("GET", "/v1/devices/me", token=token), 401, "UNAUTHENTICATED")
        self.assertIsNone(authenticate(self.db, [f"Bearer {token}"]))
        self.assertEqual(self.db.execute("SELECT count(*) FROM pairs").fetchone()[0], 0)

    def test_duplicate_authorization_headers_are_rejected(self):
        atlas = self.enroll("Atlas")
        header = [f"Bearer {atlas['device_token']}"]
        self.assertIsNotNone(authenticate(self.db, header))
        self.assertIsNone(authenticate(self.db, header * 2))


class PairingTests(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.atlas = self.enroll("Atlas")
        self.birch = self.enroll("Birch")
        self.cedar = self.enroll("Cedar")

    def test_pair_becomes_active_only_after_both_confirm(self):
        opened = self.open_pair(self.atlas)
        pair_id = opened["pair_id"]
        self.assertRegex(opened["pair_code"], re.compile(r"[0-9a-f]{32}"))
        self.assertEqual(opened["expires_at"], "2027-01-15T08:10:00Z")
        [listed] = self.pairs(self.atlas)
        self.assertEqual(listed["state"], "OPEN")
        self.assertNotIn("claimant", listed)

        status, body, _ = self.claim(self.birch, opened["pair_code"])
        self.assertEqual((status, body), (200, {"pair_id": pair_id}))
        atlas_view, birch_view = self.pairs(self.atlas)[0], self.pairs(self.birch)[0]
        self.assertEqual(atlas_view, birch_view)
        self.assertEqual(atlas_view["state"], "CLAIMED")
        self.assertRegex(atlas_view["comparison_code"], re.compile(r"[0-9]{6}"))
        self.assertEqual(atlas_view["initiator"]["display_name"], "Atlas")
        self.assertEqual(atlas_view["initiator"]["device_id_suffix"], self.atlas["device_id"][-6:])
        self.assertEqual(atlas_view["claimant"]["display_name"], "Birch")
        self.assertFalse(atlas_view["initiator"]["confirmed"] or atlas_view["claimant"]["confirmed"])

        self.clock.now_ms += 1000
        status, first, _ = self.decide(self.atlas, pair_id)
        self.assertEqual((status, first["state"]), (200, "CLAIMED"))
        self.assertTrue(first["initiator"]["confirmed"])
        self.assertFalse(first["claimant"]["confirmed"])
        row = self.pair_row(pair_id)
        self.assertEqual((row["state"], row["opener_confirmed_at_ms"], row["claimant_confirmed_at_ms"]),
                         ("CLAIMED", START_MS + 1000, None))
        self.assertIsNone(active_pair_id(self.db, self.atlas["device_id"], self.birch["device_id"]))

        self.clock.now_ms += 1000
        status, second, _ = self.decide(self.birch, pair_id)
        self.assertEqual((status, second["state"]), (200, "ACTIVE"))
        self.assertEqual(second["peer_device_id"], self.atlas["device_id"])
        self.assertEqual(self.pairs(self.atlas)[0]["peer_device_id"], self.birch["device_id"])
        row = self.pair_row(pair_id)
        self.assertEqual((row["state"], row["claimant_confirmed_at_ms"]), ("ACTIVE", START_MS + 2000))
        self.assertEqual(active_pair_id(self.db, self.birch["device_id"], self.atlas["device_id"]), pair_id)
        self.assertEqual(active_peer_ids(self.db, self.atlas["device_id"]), {self.birch["device_id"]})
        self.assert_no_raw_secrets_in_database()

    def test_rejection_ends_the_session(self):
        opened = self.open_pair(self.atlas)
        self.claim(self.birch, opened["pair_code"])
        self.decide(self.atlas, opened["pair_id"])
        status, body, _ = self.decide(self.birch, opened["pair_id"], "REJECT")
        self.assertEqual((status, body), (200, {"pair_id": opened["pair_id"], "expires_at": opened["expires_at"],
                                                "state": "DECLINED"}))
        self.assert_error(self.decide(self.atlas, opened["pair_id"]), 409, "STATE_CONFLICT")
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "DECLINED")

    def test_sessions_expire_at_the_deadline(self):
        claimed = self.open_pair(self.atlas)
        self.claim(self.birch, claimed["pair_code"])
        self.decide(self.atlas, claimed["pair_id"])
        unclaimed = self.open_pair(self.atlas)

        self.clock.now_ms = START_MS + TTL_MS  # TTL is exclusive.
        self.assert_error(self.decide(self.birch, claimed["pair_id"]), 410, "EXPIRED")
        self.assert_error(self.claim(self.cedar, unclaimed["pair_code"]), 404, "NOT_FOUND")
        for pair_id in (claimed["pair_id"], unclaimed["pair_id"]):
            self.assertEqual(self.pair_row(pair_id)["state"], "EXPIRED")
        self.assertEqual([pair["state"] for pair in self.pairs(self.atlas)], ["EXPIRED", "EXPIRED"])
        self.assertIsNone(active_pair_id(self.db, self.atlas["device_id"], self.birch["device_id"]))

    def test_concurrent_claims_consume_a_code_once(self):
        opened = self.open_pair(self.atlas)
        claimants = [self.birch, self.cedar] + [self.enroll(f"Node {index}") for index in range(3)]
        results = {}
        gate = threading.Barrier(len(claimants))

        def claim(device):
            gate.wait()
            results[device["device_id"]] = self.claim(device, opened["pair_code"])[0]

        threads = [threading.Thread(target=claim, args=(device,)) for device in claimants]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [device_id for device_id, status in results.items() if status == 200]
        self.assertEqual(len(winners), 1)
        self.assertEqual(sorted(results.values()), [200] + [404] * (len(claimants) - 1))
        self.assertEqual(self.pair_row(opened["pair_id"])["claimant_device_id"], winners[0])

    def test_self_pairing_is_rejected(self):
        opened = self.open_pair(self.atlas)
        self.assert_error(self.claim(self.atlas, opened["pair_code"]), 409, "STATE_CONFLICT")
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "OPEN")

    def test_only_one_active_pair_per_device_pair(self):
        first = self.open_pair(self.atlas)
        second = self.open_pair(self.atlas)
        self.claim(self.birch, first["pair_code"])
        self.claim(self.birch, second["pair_code"])
        for pair in (first, second):
            self.decide(self.atlas, pair["pair_id"])
        self.assertEqual(self.decide(self.birch, first["pair_id"])[1]["state"], "ACTIVE")
        self.assert_error(self.decide(self.birch, second["pair_id"]), 409, "STATE_CONFLICT")
        self.assertEqual(self.pair_row(second["pair_id"])["state"], "CLAIMED")

        third = self.open_pair(self.birch)
        self.assert_error(self.claim(self.atlas, third["pair_code"]), 409, "STATE_CONFLICT")
        self.assertEqual(self.pair_row(third["pair_id"])["state"], "OPEN")
        count = self.db.execute("SELECT count(*) FROM pairs WHERE state = 'ACTIVE'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_devices_outside_the_pair_cannot_see_or_decide(self):
        opened = self.open_pair(self.atlas)
        self.claim(self.birch, opened["pair_code"])
        self.assert_error(self.claim(self.cedar, opened["pair_code"]), 404, "NOT_FOUND")
        self.assertEqual(self.pairs(self.cedar), [])
        for decision in ("CONFIRM", "REJECT"):
            self.assert_error(self.decide(self.cedar, opened["pair_id"], decision), 404, "NOT_FOUND")
        self.assert_error(self.decide(self.cedar, str(uuid.uuid4())), 404, "NOT_FOUND")
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "CLAIMED")

        self.decide(self.atlas, opened["pair_id"])
        self.decide(self.birch, opened["pair_id"])
        self.assertEqual(self.pairs(self.cedar), [])
        self.assertEqual(active_peer_ids(self.db, self.cedar["device_id"]), set())

    def test_opener_cannot_decide_before_a_claim(self):
        opened = self.open_pair(self.atlas)
        self.assert_error(self.decide(self.atlas, opened["pair_id"]), 409, "STATE_CONFLICT")
        self.assertIsNone(self.pair_row(opened["pair_id"])["opener_confirmed_at_ms"])

    def test_connection_reflects_recent_heartbeat(self):
        opened = self.open_pair(self.atlas)
        self.claim(self.birch, opened["pair_code"])
        self.db.execute("UPDATE devices SET boot_id = 'boot', heartbeat_at_ms = ? WHERE device_id = ?",
                        (START_MS - 19_999, self.atlas["device_id"]))
        self.db.execute("UPDATE devices SET boot_id = 'boot', heartbeat_at_ms = ? WHERE device_id = ?",
                        (START_MS - 20_000, self.birch["device_id"]))
        self.db.commit()
        [view] = self.pairs(self.atlas)
        self.assertEqual((view["initiator"]["connection"], view["claimant"]["connection"]),
                         ("ONLINE", "OFFLINE"))


class IdempotencyTests(ControllerTestCase):
    def setUp(self):
        super().setUp()
        self.atlas = self.enroll("Atlas")
        self.birch = self.enroll("Birch")

    def test_create_replay_returns_code_only_while_usable(self):
        key = str(uuid.uuid4())
        first = self.open_pair(self.atlas, key)
        status, replay, _ = self.http("POST", "/v1/pairs", token=self.atlas["device_token"], key=key)
        self.assertEqual((status, replay), (201, first))
        self.assertEqual(first["pair_code"], pair_code(CODE_KEY, first["pair_id"]))
        self.assertEqual(self.db.execute("SELECT count(*) FROM pairs").fetchone()[0], 1)

        self.claim(self.birch, first["pair_code"])
        replay = self.http("POST", "/v1/pairs", token=self.atlas["device_token"], key=key)
        self.assert_error(replay, 409, "STATE_CONFLICT")

        expiring_key = str(uuid.uuid4())
        self.open_pair(self.atlas, expiring_key)
        self.clock.now_ms = START_MS + TTL_MS
        replay = self.http("POST", "/v1/pairs", token=self.atlas["device_token"], key=expiring_key)
        self.assert_error(replay, 410, "EXPIRED")

        stored = [json.loads(row[0]) for row in self.db.execute("SELECT result_json FROM idempotency")]
        self.assertTrue(stored)
        self.assertFalse(any("pair_code" in result for result in stored))
        self.assert_no_raw_secrets_in_database()

    def test_claim_replay_survives_code_consumption(self):
        opened = self.open_pair(self.atlas)
        key = str(uuid.uuid4())
        self.assertEqual(self.claim(self.birch, opened["pair_code"], key)[0], 200)
        status, body, _ = self.claim(self.birch, opened["pair_code"], key)
        self.assertEqual((status, body), (200, {"pair_id": opened["pair_id"]}))
        changed = self.claim(self.birch, "0" * 32, key)
        self.assert_error(changed, 409, "STATE_CONFLICT")
        self.assertEqual(changed[1]["error"]["message"],
                         "Idempotency key was already used with a different payload.")

    def test_decision_replay_and_key_scope(self):
        opened = self.open_pair(self.atlas)
        self.claim(self.birch, opened["pair_code"])
        key = str(uuid.uuid4())
        first = self.decide(self.atlas, opened["pair_id"], key=key)
        self.assertEqual((first[0], first[1]["state"]), (200, "CLAIMED"))
        replay = self.decide(self.atlas, opened["pair_id"], key=key)
        self.assertEqual(replay[:2], first[:2])
        self.assert_error(self.decide(self.atlas, opened["pair_id"], "REJECT", key=key), 409, "STATE_CONFLICT")
        # The same key on another device is a separate scope.
        self.assertEqual(self.decide(self.birch, opened["pair_id"], key=key)[1]["state"], "ACTIVE")
        # A replay returns the committed result, not the pair's later state.
        self.assertEqual(self.decide(self.atlas, opened["pair_id"], key=key)[:2], first[:2])
        self.assertEqual(self.decide(self.birch, opened["pair_id"], key=key)[1]["state"], "ACTIVE")

        stored = [json.loads(row[0]) for row in self.db.execute(
            "SELECT result_json FROM idempotency WHERE route = ?", (f"/v1/pairs/{opened['pair_id']}/decision",))]
        self.assertEqual([result["state"] for result in stored], ["CLAIMED", "ACTIVE"])
        self.assertFalse(any("comparison_code" in result for result in stored))

    def test_rejection_replay_returns_the_declined_result(self):
        opened = self.open_pair(self.atlas)
        self.claim(self.birch, opened["pair_code"])
        key = str(uuid.uuid4())
        first = self.decide(self.birch, opened["pair_id"], "REJECT", key=key)
        self.assertEqual(first[:2], (200, {"pair_id": opened["pair_id"], "expires_at": first[1]["expires_at"],
                                            "state": "DECLINED"}))
        self.clock.now_ms = START_MS + TTL_MS
        self.assertEqual(self.decide(self.birch, opened["pair_id"], "REJECT", key=key)[:2], first[:2])

    def test_missing_or_malformed_keys_and_bodies_are_rejected(self):
        token = self.atlas["device_token"]
        opened = self.open_pair(self.atlas)
        for key in (None, "not-a-uuid", str(uuid.uuid4()).upper(), "00000000-0000-1000-8000-000000000000"):
            with self.subTest(key=key):
                self.assert_error(self.http("POST", "/v1/pairs", token=token, key=key), 400, "INVALID_REQUEST")
                claim = self.http("POST", "/v1/pairs/claim", token=self.birch["device_token"], key=key,
                                  body={"pair_code": opened["pair_code"]})
                self.assert_error(claim, 400, "INVALID_REQUEST")
        self.assert_error(self.http("POST", "/v1/pairs", token=token, key=str(uuid.uuid4()), body={}),
                          400, "INVALID_REQUEST")
        for body in ({"decision": "MAYBE"}, {"decision": "CONFIRM", "extra": True}, {}):
            with self.subTest(body=body):
                result = self.http("POST", f"/v1/pairs/{opened['pair_id']}/decision", token=token,
                                   key=str(uuid.uuid4()), body=body)
                self.assert_error(result, 400, "INVALID_REQUEST")
        for code in ("D" * 32, "d" * 31, 7):
            with self.subTest(code=code):
                result = self.http("POST", "/v1/pairs/claim", token=self.birch["device_token"],
                                   key=str(uuid.uuid4()), body={"pair_code": code})
                self.assert_error(result, 400, "INVALID_REQUEST")
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "OPEN")


class LockWaitTests(ControllerTestCase):
    """A request that waits for the write lock is judged at the time it gets the lock."""

    def send_while_locked(self, send, *, now_ms=None, change=None):
        """Run `send` while this test holds the write lock.

        Once the request has reached `BEGIN IMMEDIATE` and is waiting, move the
        clock to `now_ms` or commit `change(self.db)` under the held lock. A
        request that read the time or the caller's token earlier sees the old value.
        """
        waiting = threading.Event()
        self.server.on_connect = lambda connection: connection.set_trace_callback(
            lambda sql: waiting.set() if sql == "BEGIN IMMEDIATE" else None)
        self.addCleanup(setattr, self.server, "on_connect", None)
        results = []
        self.db.execute("BEGIN IMMEDIATE")
        try:
            worker = threading.Thread(target=lambda: results.append(send()))
            worker.start()
            self.assertTrue(waiting.wait(5), "Request never waited for the write lock")
            if now_ms is not None:
                self.clock.now_ms = now_ms
            if change is not None:
                change(self.db)
        except BaseException:
            self.db.rollback()
            raise
        self.db.commit()
        worker.join(10)
        self.server.on_connect = None
        return results[0]

    def revoke(self, device):
        """Return a change that revokes `device`'s token."""
        return lambda db: db.execute(
            "UPDATE devices SET revoked_at_ms = ? WHERE device_id = ?",
            (self.clock(), device["device_id"]))

    def idempotency_rows(self, device):
        return self.db.execute(
            "SELECT count(*) FROM idempotency WHERE device_id = ?", (device["device_id"],)).fetchone()[0]

    def test_create_with_a_token_revoked_during_the_wait_is_rejected(self):
        atlas = self.enroll("Atlas")
        result = self.send_while_locked(lambda: self.http(
            "POST", "/v1/pairs", token=atlas["device_token"], key=str(uuid.uuid4())),
            change=self.revoke(atlas))
        self.assert_error(result, 401, "UNAUTHENTICATED")
        self.assertEqual(self.db.execute("SELECT count(*) FROM pairs").fetchone()[0], 0)
        self.assertEqual(self.idempotency_rows(atlas), 0)

    def test_create_replay_with_a_token_revoked_during_the_wait_hides_the_code(self):
        atlas = self.enroll("Atlas")
        key = str(uuid.uuid4())
        opened = self.open_pair(atlas, key=key)
        result = self.send_while_locked(lambda: self.http(
            "POST", "/v1/pairs", token=atlas["device_token"], key=key),
            change=self.revoke(atlas))
        self.assert_error(result, 401, "UNAUTHENTICATED")
        self.assertNotIn(opened["pair_code"], json.dumps(result[1]))
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "OPEN")

    def test_claim_with_a_token_revoked_during_the_wait_is_rejected(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        opened = self.open_pair(atlas)
        result = self.send_while_locked(lambda: self.claim(birch, opened["pair_code"]),
                                        change=self.revoke(birch))
        self.assert_error(result, 401, "UNAUTHENTICATED")
        row = self.pair_row(opened["pair_id"])
        self.assertEqual((row["state"], row["claimant_device_id"], row["comparison_code"]),
                         ("OPEN", None, None))
        self.assertEqual(self.idempotency_rows(birch), 0)

    def test_decision_with_a_token_revoked_during_the_wait_is_rejected(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        opened = self.open_pair(atlas)
        self.claim(birch, opened["pair_code"])
        self.assertEqual(self.decide(atlas, opened["pair_id"])[1]["state"], "CLAIMED")
        result = self.send_while_locked(lambda: self.decide(birch, opened["pair_id"]),
                                        change=self.revoke(birch))
        self.assert_error(result, 401, "UNAUTHENTICATED")
        row = self.pair_row(opened["pair_id"])
        self.assertEqual((row["state"], row["claimant_confirmed_at_ms"]), ("CLAIMED", None))
        self.assertIsNone(active_pair_id(self.db, atlas["device_id"], birch["device_id"]))

    def test_decision_replay_with_a_token_revoked_during_the_wait_is_rejected(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        opened = self.open_pair(atlas)
        self.claim(birch, opened["pair_code"])
        key = str(uuid.uuid4())
        first = self.decide(atlas, opened["pair_id"], key=key)
        self.assertEqual((first[0], first[1]["state"]), (200, "CLAIMED"))
        result = self.send_while_locked(lambda: self.decide(atlas, opened["pair_id"], key=key),
                                        change=self.revoke(atlas))
        self.assert_error(result, 401, "UNAUTHENTICATED")
        self.assertNotIn("comparison_code", json.dumps(result[1]))

    def test_enrollment_that_waits_past_the_deadline_is_rejected(self):
        code = issue_enrollment_code(self.db, now_ms=START_MS)
        result = self.send_while_locked(lambda: self.http(
            "POST", "/v1/devices/enroll", body={"enrollment_code": code, "display_name": "Late"}),
            now_ms=START_MS + TTL_MS)
        self.assert_error(result, 404, "NOT_FOUND")
        self.assertEqual(self.db.execute("SELECT count(*) FROM devices").fetchone()[0], 0)
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM enrollments WHERE consumed_at_ms IS NULL").fetchone()[0], 1)

    def test_second_confirmation_that_waits_past_the_deadline_does_not_activate(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        opened = self.open_pair(atlas)
        self.claim(birch, opened["pair_code"])
        self.assertEqual(self.decide(atlas, opened["pair_id"])[1]["state"], "CLAIMED")
        result = self.send_while_locked(lambda: self.decide(birch, opened["pair_id"]),
                                        now_ms=START_MS + TTL_MS)
        self.assert_error(result, 410, "EXPIRED")
        row = self.pair_row(opened["pair_id"])
        self.assertEqual((row["state"], row["claimant_confirmed_at_ms"]), ("EXPIRED", None))
        self.assertIsNone(active_pair_id(self.db, atlas["device_id"], birch["device_id"]))

    def test_claim_that_waits_past_the_deadline_is_rejected(self):
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        opened = self.open_pair(atlas)
        result = self.send_while_locked(lambda: self.claim(birch, opened["pair_code"]),
                                        now_ms=START_MS + TTL_MS)
        self.assert_error(result, 404, "NOT_FOUND")
        row = self.pair_row(opened["pair_id"])
        self.assertEqual((row["state"], row["claimant_device_id"]), ("EXPIRED", None))

    def test_new_pair_deadline_starts_when_the_lock_is_held(self):
        atlas = self.enroll("Atlas")
        result = self.send_while_locked(lambda: self.http(
            "POST", "/v1/pairs", token=atlas["device_token"], key=str(uuid.uuid4())),
            now_ms=START_MS + 5_000)
        self.assertEqual(result[0], 201, result[1])
        self.secrets.append(result[1]["pair_code"])
        row = self.pair_row(result[1]["pair_id"])
        self.assertEqual((row["created_at_ms"], row["expires_at_ms"]),
                         (START_MS + 5_000, START_MS + 5_000 + TTL_MS))


class RateLimitTests(ControllerTestCase):
    def setUp(self):
        self.router_options = {}
        super().setUp()

    def test_enrollment_and_claims_are_rate_limited(self):
        self.server.close()
        self.server = ControllerServer(
            self.db_path, self.clock,
            enroll_limiter=RateLimiter(limit=2, window_ms=60_000, clock=self.clock),
            claim_limiter=RateLimiter(limit=1, window_ms=60_000, clock=self.clock),
        )
        self.addCleanup(self.server.close)
        atlas, birch = self.enroll("Atlas"), self.enroll("Birch")
        code = issue_enrollment_code(self.db, now_ms=self.clock())
        status, body, response = self.http("POST", "/v1/devices/enroll",
                                           body={"enrollment_code": code, "display_name": "Cedar"})
        self.assertEqual((status, body["error"]["code"]), (429, "RATE_LIMITED"))
        self.assertEqual(response.getheader("Retry-After"), "60")
        self.assertIsNone(self.db.execute(
            "SELECT consumed_at_ms FROM enrollments WHERE code_sha256 = ?",
            (hashlib.sha256(code.encode()).digest(),),
        ).fetchone()[0])

        opened = self.open_pair(atlas)
        self.assertEqual(self.claim(birch, "0" * 32)[0], 404)
        self.assert_error(self.claim(birch, opened["pair_code"]), 429, "RATE_LIMITED")
        self.assertEqual(self.pair_row(opened["pair_id"])["state"], "OPEN")

        self.clock.now_ms += 60_000
        self.assertEqual(self.claim(birch, opened["pair_code"])[0], 200)


class PairCodeTests(unittest.TestCase):
    def test_codes_are_stable_per_pair_and_key(self):
        pair_id = str(uuid.uuid4())
        self.assertEqual(pair_code(CODE_KEY, pair_id), pair_code(CODE_KEY, pair_id))
        self.assertNotEqual(pair_code(CODE_KEY, pair_id), pair_code(CODE_KEY, str(uuid.uuid4())))
        self.assertNotEqual(pair_code(CODE_KEY, pair_id), pair_code(b"q" * 32, pair_id))

    def test_router_requires_a_long_code_key(self):
        with self.assertRaises(ValueError):
            create_router(connect=lambda: None, pair_code_key=b"short")


if __name__ == "__main__":
    unittest.main()
