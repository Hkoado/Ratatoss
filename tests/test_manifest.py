import hashlib
import json
from pathlib import Path
from shutil import rmtree
import unittest
from uuid import uuid4

from ratatoss.manifest import Manifest, Segment, build_manifest, verify_batch, verify_file


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ManifestTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).parent / f".tmp-{uuid4().hex}"
        directory.mkdir()
        self.addCleanup(rmtree, directory)
        self.source = directory / "nguồn.bin"
        self.source.write_bytes(b"abcdefghij")
        self.manifest = build_manifest(self.source, piece_size=3, batch_size=6)

    def test_known_content_and_layout(self):
        self.assertEqual(self.manifest.sha256, digest(b"abcdefghij"))
        self.assertEqual(self.manifest.pieces, (
            Segment(0, 0, 3, digest(b"abc")),
            Segment(1, 3, 3, digest(b"def")),
            Segment(2, 6, 3, digest(b"ghi")),
            Segment(3, 9, 1, digest(b"j")),
        ))
        self.assertEqual(self.manifest.batches, (
            Segment(0, 0, 6, digest(b"abcdef")),
            Segment(1, 6, 4, digest(b"ghij")),
        ))
        self.assertEqual(Manifest.from_json(self.manifest.to_json()), self.manifest)

    def test_verifies_under_a_new_name_and_detects_damage(self):
        moved = self.source.rename(self.source.with_name("other.bin"))
        self.assertTrue(verify_file(moved, self.manifest))
        for content in (b"abzdefghij", b"abcdefghi", b"abcdefghijk"):
            with self.subTest(content=content):
                moved.write_bytes(content)
                self.assertFalse(verify_file(moved, self.manifest))

    def test_validates_last_batch(self):
        batch = self.source.with_name("batch.bin")
        batch.write_bytes(b"ghij")
        self.assertTrue(verify_batch(batch, self.manifest, 1))
        self.assertFalse(verify_batch(batch, self.manifest, 0))
        batch.write_bytes(b"ghix")
        self.assertFalse(verify_batch(batch, self.manifest, 1))
        with self.assertRaises(ValueError):
            verify_batch(batch, self.manifest, -1)

    def test_empty_file(self):
        self.source.write_bytes(b"")
        manifest = build_manifest(self.source)
        self.assertEqual((manifest.pieces, manifest.batches), ((), ()))
        self.assertEqual(manifest.sha256, digest(b""))
        self.assertTrue(verify_file(self.source, manifest))

    def test_rejects_invalid_settings(self):
        for piece_size, batch_size in ((0, 6), (3, 7), (6, 3), (True, 6)):
            with self.subTest(piece_size=piece_size, batch_size=batch_size):
                with self.assertRaises(ValueError):
                    build_manifest(self.source, piece_size=piece_size, batch_size=batch_size)

    def test_rejects_malformed_json_fields(self):
        for name, value in (("version", True), ("name", "../bad"), ("sha256", "abc"),
                            ("pieces", []), ("batches", [{"index": 0}])):
            with self.subTest(name=name, value=value):
                fields = json.loads(self.manifest.to_json())
                fields[name] = value
                with self.assertRaises(ValueError):
                    Manifest.from_json(json.dumps(fields))
