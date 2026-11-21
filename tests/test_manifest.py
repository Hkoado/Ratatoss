import hashlib
import json
import os
from pathlib import Path
from shutil import rmtree
import subprocess
import sys
import unittest
from uuid import uuid4

from ratatoss.manifest import Manifest, Segment, build_manifest, decode_manifest_object, verify_batch, verify_file


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
        self.assertEqual(Manifest.from_json(manifest.canonical_bytes()), manifest)
        fields = json.loads(manifest.to_json())
        fields["sha256"] = digest(b"x")
        with self.assertRaisesRegex(ValueError, "empty file"):
            Manifest.from_dict(fields)

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

    def test_canonical_bytes_ignore_json_spelling_and_preserve_code_points(self):
        fields = json.loads(self.manifest.to_json())
        fields["name"] = "Cafe\u0301-\U0001f680.bin"
        reordered = dict(reversed(list(fields.items())))
        from_pretty = Manifest.from_json(json.dumps(fields, ensure_ascii=True, indent=2))
        from_reordered = Manifest.from_json(json.dumps(reordered, ensure_ascii=False).encode())
        canonical = from_pretty.canonical_bytes()
        self.assertEqual(canonical, from_reordered.canonical_bytes())
        self.assertEqual(list(json.loads(canonical)), sorted(fields))
        self.assertIn('"name":"Cafe\u0301-\U0001f680.bin"'.encode(), canonical)
        self.assertTrue(canonical.startswith(b"{") and canonical.endswith(b"}"))
        self.assertNotIn(b"\n", canonical)
        self.assertEqual(from_pretty.manifest_sha256(), digest(canonical))
        self.assertNotEqual(from_pretty.manifest_sha256(), from_pretty.sha256)
        fields["name"] = "Caf\u00e9-\U0001f680.bin"
        self.assertNotEqual(Manifest.from_dict(fields).manifest_sha256(), from_pretty.manifest_sha256())

    @unittest.skipUnless(
        (Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1])
         / "spec/api/examples/job-create-request.json").is_file(),
        "repository API fixtures unavailable",
    )
    def test_job_create_vector(self):
        root = Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1])
        examples = root / "spec/api/examples"
        request = decode_manifest_object((examples / "job-create-request.json").read_bytes())
        response = json.loads((examples / "job-create-response.json").read_bytes())
        manifest = Manifest.from_dict(request["manifest"])
        self.assertEqual(manifest.manifest_sha256(), response["manifest_sha256"])
        self.assertEqual(build_manifest(examples / "sample.txt"), manifest)

    def test_rejects_duplicate_object_keys_in_raw_json(self):
        raw = self.manifest.to_json()
        for envelope in ('{"manifest": {}, "manifest": {}}', '{"manifest": {"pieces": [{"size": 1, "size": 2}]}}'):
            with self.subTest(envelope=envelope), self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                decode_manifest_object(envelope)
        for original, replacement in (
            ('"version": 1', '"version": 2, "\\u0076ersion": 1'),
            ('"index": 0', '"index": 1, "index": 0'),
        ):
            with self.subTest(field=original):
                with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                    Manifest.from_json(raw.replace(original, replacement, 1))

    def test_rejects_unknown_keys_surrogates_and_invalid_numbers(self):
        raw = self.manifest.to_json()
        for original, replacement in (
            ('"version": 1', '"version": 1, "extra": 0'),
            ('"index": 0', '"index": 0, "extra": 0'),
            (json.dumps(self.manifest.name, ensure_ascii=False), '"\\ud800.bin"'),
            (json.dumps(self.manifest.name, ensure_ascii=False), '"\\udfff.bin"'),
            ('"version": 1', '"version": 1.0'),
            ('"piece_size": 3', '"piece_size": NaN'),
            ('"batch_size": 6', '"batch_size": Infinity'),
            ('"size": 10', '"size": -Infinity'),
            ('"size": 10', '"size": 1e1000'),
            ('"index": 0', '"index": false'),
            ('"offset": 0', '"offset": 0.0'),
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError):
                    Manifest.from_json(raw.replace(original, replacement, 1))

    def test_cli_verify_reads_pretty_and_canonical_and_rejects_duplicates(self):
        path = self.source.with_name("manifest.json")
        command = [sys.executable, "-m", "ratatoss", "verify", str(self.source), str(path)]
        pretty = (self.manifest.to_json() + "\n").encode()
        duplicate = pretty.replace(b'"index": 0', b'"index": 1, "index": 0', 1)
        for data, expected in ((pretty, 0), (self.manifest.canonical_bytes(), 0), (duplicate, 2)):
            with self.subTest(expected=expected):
                path.write_bytes(data)
                result = subprocess.run(command, capture_output=True, check=False)
                self.assertEqual(result.returncode, expected, result.stderr)
