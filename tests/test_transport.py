import asyncio
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ratatoss._croc_process import JobCleanup, WindowsChild
from ratatoss.transport import WINDOWS_X64_SHA256, Batch, CrocAdapter, CrocError, RelayProfile


class FakeChild:
    pid = 123

    def __init__(self, exit_code):
        self.exit_code = exit_code
        self.stopped = False

    def poll(self):
        return self.exit_code

    def stop(self):
        self.stopped = True
        return JobCleanup(int(self.exit_code is None), 0, 1, self.exit_code or 0)


class CrocAdapterTests(unittest.IsolatedAsyncioTestCase):
    payload = b"synthetic test batch"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.binary = self.root / "croc.exe"
        self.profile = RelayProfile("127.0.0.1:19009", "relay-test-password", 1_000_000, 0, 0, 0)
        self.attempts = self.root / "attempts"
        self.attempts.mkdir()
        self.destination = self.root / "verified.bin"
        self.batch = self.new_batch()

    def new_batch(self):
        return Batch(uuid4(), len(self.payload), hashlib.sha256(self.payload).hexdigest())

    def adapter(self):
        with patch.object(CrocAdapter, "_verify_binary", autospec=True):
            return CrocAdapter(self.binary, self.attempts, self.profile)

    async def receive(self, adapter, batch=None, timeout=2, lease=None):
        return await adapter.receive(
            self.destination, "test-session-code", batch=batch or self.batch,
            timeout=timeout, lease_deadline=time.monotonic() + 2 if lease is None else lease,
        )

    @unittest.skipUnless(os.name == "nt", "Windows Croc pin")
    def test_wrong_digest_never_executes_binary(self):
        self.binary.write_bytes(b"untrusted fixture")
        with patch("ratatoss.transport.subprocess.run") as probe:
            with self.assertRaisesRegex(CrocError, "^CROC_DIGEST_MISMATCH$"):
                CrocAdapter(self.binary, self.attempts, self.profile)
        probe.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows Croc pin")
    def test_wrong_reported_version_blocks_adapter(self):
        self.binary.touch()
        with (
            patch("ratatoss.transport.sha256_file", return_value=WINDOWS_X64_SHA256),
            patch("ratatoss.transport.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, b"croc version 11.6.50\n",
            )) as probe,
        ):
            with self.assertRaisesRegex(CrocError, "^CROC_VERSION_MISMATCH$"):
                CrocAdapter(self.binary, self.attempts, self.profile)
        probe.assert_called_once()
        self.assertFalse(probe.call_args.kwargs["shell"])

    async def test_lease_rejects_before_spawn_and_does_not_reserve_attempt(self):
        with patch("ratatoss.transport.WindowsChild") as spawn:
            with self.assertRaisesRegex(CrocError, "^INSUFFICIENT_LEASE_BUDGET$"):
                await self.receive(self.adapter(), lease=time.monotonic())
        spawn.assert_not_called()
        self.assertEqual(list(self.attempts.iterdir()), [])

    async def test_preflight_rechecks_lease_after_preparing_tx(self):
        adapter = self.adapter()
        self.destination.write_bytes(self.payload)
        with (
            patch("ratatoss.transport.WindowsChild") as spawn,
            patch("ratatoss.transport._remaining_ms", side_effect=[100, 100, 0, 100]),
        ):
            with self.assertRaisesRegex(CrocError, "^INSUFFICIENT_LEASE_BUDGET$"):
                await adapter.send(
                    self.destination, "test-session-code", batch=self.batch,
                    timeout=2, lease_deadline=time.monotonic() + 2,
                )
        spawn.assert_not_called()
        self.assertEqual(list((self.attempts / self.batch.attempt_id.hex / "tx").iterdir()), [])

    async def test_preflight_only_charges_setup_still_required_at_spawn(self):
        self.profile = replace(self.profile, setup_ms=3000)
        adapter = self.adapter()
        self.destination.write_bytes(self.payload)
        lease = time.monotonic() + 2
        with patch("ratatoss.transport.WindowsChild", return_value=FakeChild(0)) as spawn:
            with self.assertRaisesRegex(CrocError, "^INSUFFICIENT_LEASE_BUDGET$"):
                await adapter.send(
                    self.destination, "test-session-code", batch=self.batch,
                    timeout=4, lease_deadline=lease,
                )
            spawn.assert_not_called()
            result = await adapter.send(
                self.destination, "test-session-code", batch=self.batch,
                timeout=4, lease_deadline=lease, remaining_setup_ms=100,
            )
        spawn.assert_called_once()
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.deadline_monotonic, lease)

    async def test_timeout_isolates_partial_retry_verifies_and_existing_output_survives(self):
        adapter = self.adapter()
        timed_out = FakeChild(None)

        def write_partial(argv, *, cwd, env):
            self.assertEqual(list(cwd.iterdir()), [])
            self.assertEqual(argv[-3:], ["--relay", self.profile.endpoint, "--yes"])
            self.assertNotIn("test-session-code", " ".join(argv))
            self.assertNotIn(self.profile.password, " ".join(argv))
            self.assertEqual(env["CROC_SECRET"], "test-session-code")
            self.assertEqual(env["CROC_PASS"], self.profile.password)
            self.assertNotIn("PATH", env)
            self.assertTrue(Path(env["CROC_CONFIG_DIR"]).is_dir())
            (cwd / self.batch.filename).write_bytes(self.payload[:3])
            return timed_out

        with patch("ratatoss.transport.WindowsChild", side_effect=write_partial):
            with self.assertRaisesRegex(CrocError, "^TRANSPORT_TIMEOUT$") as failure:
                await self.receive(adapter, timeout=0.2)
        self.assertTrue(timed_out.stopped)
        self.assertEqual(failure.exception.process.job.active_after_stop, 0)
        self.assertTrue(failure.exception.partial_isolated)
        self.assertFalse(self.destination.exists())
        area = self.attempts / self.batch.attempt_id.hex / "rx"
        self.assertEqual(list(area.iterdir()), [area / "quarantine"])
        self.assertEqual((area / "quarantine" / self.batch.filename).read_bytes(), self.payload[:3])

        retry = self.new_batch()
        successful = FakeChild(0)

        def write_verified(argv, *, cwd, env):
            (cwd / retry.filename).write_bytes(self.payload)
            return successful

        with patch("ratatoss.transport.WindowsChild", side_effect=write_verified) as spawn:
            with self.assertRaisesRegex(CrocError, "^ATTEMPT_ALREADY_USED$"):
                await self.receive(adapter)
            result = await self.receive(adapter, retry)
            with self.assertRaisesRegex(CrocError, "^DESTINATION_EXISTS$"):
                await self.receive(adapter, self.new_batch())
        spawn.assert_called_once()
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(successful.stopped)
        self.assertEqual(self.destination.read_bytes(), self.payload)
        self.assertIsNone(result.first_byte_monotonic)
        self.assertIsNone(result.last_byte_monotonic)
        self.assertIsNotNone(result.sha256_done_monotonic)

    async def test_wrong_hash_after_exit_never_delivers(self):
        def corrupt(argv, *, cwd, env):
            (cwd / self.batch.filename).write_bytes(b"x" * self.batch.size)
            return FakeChild(0)

        with patch("ratatoss.transport.WindowsChild", side_effect=corrupt):
            with self.assertRaisesRegex(CrocError, "^CORRUPT$") as failure:
                await self.receive(self.adapter())
        self.assertTrue(failure.exception.partial_isolated)
        self.assertFalse(self.destination.exists())

    async def test_transient_croc_probe_must_disappear_before_delivery(self):
        child = FakeChild(None)

        def create_probe(argv, *, cwd, env):
            (cwd / self.batch.filename).write_bytes(self.payload)
            (cwd / (".croc-bundle-probe-" + "0" * 24)).mkdir()
            child.poll = unittest.mock.Mock(side_effect=[None, 0])
            return child

        with patch("ratatoss.transport.WindowsChild", side_effect=create_probe):
            with self.assertRaisesRegex(CrocError, "^CORRUPT$"):
                await self.receive(self.adapter())
        self.assertEqual(child.poll.call_count, 2)
        self.assertTrue(child.stopped)
        self.assertFalse(self.destination.exists())

    async def test_cleanup_failure_after_verified_delivery_keeps_success(self):
        def write_verified(argv, *, cwd, env):
            (cwd / self.batch.filename).write_bytes(self.payload)
            return FakeChild(0)

        with (
            patch("ratatoss.transport.WindowsChild", side_effect=write_verified),
            patch.object(CrocAdapter, "_cleanup_staging", side_effect=PermissionError),
        ):
            result = await self.receive(self.adapter())
        self.assertTrue(result.staging_cleanup_pending)
        self.assertEqual(self.destination.read_bytes(), self.payload)

    async def test_cancel_stops_worker_before_isolating_staging(self):
        spawned = asyncio.Event()
        child = FakeChild(None)

        def write_partial(argv, *, cwd, env):
            (cwd / self.batch.filename).write_bytes(self.payload[:3])
            spawned.set()
            return child

        with patch("ratatoss.transport.WindowsChild", side_effect=write_partial):
            task = asyncio.create_task(self.receive(self.adapter()))
            await asyncio.wait_for(spawned.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(child.stopped)
        self.assertFalse(self.destination.exists())
        self.assertTrue((self.attempts / self.batch.attempt_id.hex / "rx" / "quarantine").is_dir())

    async def test_cancel_during_verification_keeps_staging_owned_and_prevents_delivery(self):
        loop = asyncio.get_running_loop()
        hashing = asyncio.Event()
        allow_hash_to_finish = threading.Event()
        child = FakeChild(0)
        attempt = self.attempts / self.batch.attempt_id.hex / "rx"

        def write_verified(argv, *, cwd, env):
            (cwd / self.batch.filename).write_bytes(self.payload)
            return child

        def verify_with_open_file(path):
            with path.open("rb") as stream:
                loop.call_soon_threadsafe(hashing.set)
                if not allow_hash_to_finish.wait(5):
                    raise TimeoutError("Test did not unblock verification")
                return hashlib.file_digest(stream, "sha256").hexdigest()

        with (
            patch("ratatoss.transport.WindowsChild", side_effect=write_verified),
            patch("ratatoss.transport.sha256_file", side_effect=verify_with_open_file),
        ):
            task = asyncio.create_task(self.receive(self.adapter(), timeout=5, lease=time.monotonic() + 5))
            try:
                await asyncio.wait_for(hashing.wait(), 2)
                self.assertTrue(child.stopped)
                for _ in range(2):
                    self.assertTrue(task.cancel())
                    await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertTrue((attempt / "data" / self.batch.filename).is_file())
                self.assertFalse(self.destination.exists())
            finally:
                allow_hash_to_finish.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        self.assertFalse(self.destination.exists())
        self.assertEqual((attempt / "quarantine" / self.batch.filename).read_bytes(), self.payload)


@unittest.skipUnless(os.name == "nt", "Windows process tree")
class WindowsJobTests(unittest.TestCase):
    def test_stop_terminates_live_descendant_and_releases_file_handle(self):
        import _winapi

        worker = """
from pathlib import Path
import os
import time

with Path("held").open("w") as held:
    Path("ready").write_text(str(os.getpid()), encoding="ascii")
    time.sleep(60)
"""
        parent = """
import subprocess
import sys
import time

subprocess.Popen([sys.executable, "-c", sys.argv[1]])
time.sleep(60)
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = WindowsChild(
                [sys.executable, "-c", parent, worker], cwd=root,
                env={"SystemRoot": os.environ["SystemRoot"]},
            )
            descendant = None
            try:
                ready = root / "ready"
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        pid = int(ready.read_text(encoding="ascii"))
                    except (OSError, ValueError):
                        time.sleep(0.025)
                        continue
                    descendant = _winapi.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                    break
                self.assertIsNotNone(descendant)
            finally:
                try:
                    cleanup = process.stop()
                    if descendant is not None:
                        self.assertEqual(
                            _winapi.WaitForSingleObject(descendant, 1000), _winapi.WAIT_OBJECT_0,
                        )
                finally:
                    if descendant is not None:
                        _winapi.CloseHandle(descendant)
            self.assertGreaterEqual(cleanup.active_before_stop, 2)
            self.assertGreaterEqual(cleanup.total_processes, 2)
            self.assertEqual(cleanup.active_after_stop, 0)
            (root / "held").unlink()


if __name__ == "__main__":
    unittest.main()
