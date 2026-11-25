"""Coverage for the pinned Croc payload-frame observer."""

import unittest

try:
    from scripts.croc_r02_tap import DataFrames, FRAME_BODY_BYTES, PAYLOAD_BYTES
except ModuleNotFoundError as error:
    if error.name not in {"scripts", "scripts.croc_r02_tap"}:
        raise
    raise unittest.SkipTest("Benchmark scripts are kept outside the installed wheel") from error


def frame(body: bytes) -> bytes:
    return b"croc" + len(body).to_bytes(4, "little") + body


class DataFrameTests(unittest.TestCase):
    def test_counts_only_payload_and_handles_split_header_and_body(self):
        observer = DataFrames()
        observer.observe(frame(b"admission"), 1)
        first = frame(bytes(FRAME_BODY_BYTES))
        # 8-byte frame header plus 20 bytes of nonce and encrypted offset.
        observer.observe(first[:3], 2)
        observer.observe(first[3:28], 3)
        self.assertIsNone(observer.first_ns)
        observer.observe(first[28:-16], 4)
        observer.observe(first[-16:] + frame(b"\x01"), 5)
        measurement = observer.interval(PAYLOAD_BYTES)
        self.assertIsNone(measurement)  # One timestamp is insufficient for a rate.
        observer.observe(first, 6)
        measurement = observer.interval(2 * PAYLOAD_BYTES)
        self.assertIsNotNone(measurement)
        self.assertEqual((measurement.first_ns, measurement.last_ns, measurement.frames), (4, 6, 2))

    def test_rejects_truncated_unexpected_and_extra_payload(self):
        payload = frame(bytes(FRAME_BODY_BYTES))
        for bad_tail in (payload[:-1], b"oops" + payload[4:], payload + payload):
            with self.subTest(size=len(bad_tail)):
                observer = DataFrames()
                observer.observe(frame(b"admission"), 1)
                observer.observe(bad_tail[:128], 2)
                observer.observe(bad_tail[128:], 3)
                self.assertIsNone(observer.interval(PAYLOAD_BYTES))
