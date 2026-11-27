import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import unittest

from ratatoss.manifest import Manifest
from ratatoss.node_offer_manifest import (
    DUPLICATE_JSON_KEY,
    INVALID_MANIFEST,
    INVALID_MANIFEST_DIGEST,
    INVALID_OFFER_JSON,
    INVALID_OFFER_PAYLOAD,
    MANIFEST_DIGEST_MISMATCH,
    MISSING_MANIFEST,
    MISSING_MANIFEST_DIGEST,
    OFFER_METADATA_MISMATCH,
    OfferManifestError,
    VerifiedOfferManifest,
    verify_offer_manifest,
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_manifest(
    data: bytes,
    *,
    name: str = "report.bin",
    piece_size: int = 3,
    batch_size: int = 6,
) -> Manifest:
    pieces = []
    batches = []
    offset = 0
    while offset < len(data):
        batch_end = min(offset + batch_size, len(data))
        batch_start = offset
        while offset < batch_end:
            piece_end = min(offset + piece_size, batch_end)
            chunk = data[offset:piece_end]
            pieces.append((len(pieces), offset, len(chunk), _sha256_hex(chunk)))
            offset = piece_end
        batches.append((len(batches), batch_start, batch_end - batch_start, _sha256_hex(data[batch_start:batch_end])))

    from ratatoss.manifest import Segment

    return Manifest(
        name=name,
        size=len(data),
        piece_size=piece_size,
        batch_size=batch_size,
        sha256=_sha256_hex(data),
        pieces=tuple(Segment(*item) for item in pieces),
        batches=tuple(Segment(*item) for item in batches),
    )


def _make_offer(
    manifest: Manifest,
    *,
    manifest_sha256: str | None = None,
    include_envelope: bool = True,
) -> dict[str, object]:
    manifest_dict = json.loads(manifest.to_json())
    offer: dict[str, object] = {
        "manifest": manifest_dict,
        "manifest_sha256": manifest.manifest_sha256() if manifest_sha256 is None else manifest_sha256,
    }
    if include_envelope:
        offer.update(
            {
                "offer_id": "00000000-0000-4000-8000-000000000007",
                "job_id": "00000000-0000-4000-8000-000000000006",
                "source_device_id": "00000000-0000-4000-8000-000000000001",
                "source_display_name": "Atlas",
                "file_name": manifest.name,
                "size": manifest.size,
                "expires_at": "2026-11-19T12:00:00Z",
                "state": "PENDING",
            }
        )
    return offer


def _repo_examples_dir() -> Path:
    root = Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1])
    return root / "spec" / "api" / "examples"


class NodeOfferManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = _make_manifest(b"abcdefghij")
        self.offer = _make_offer(self.manifest)

    def assert_offer_error(self, payload: object, expected_code: str) -> OfferManifestError:
        with self.assertRaises(OfferManifestError) as ctx:
            verify_offer_manifest(payload)
        self.assertEqual(ctx.exception.code, expected_code)
        return ctx.exception

    @unittest.skipUnless(
        (_repo_examples_dir() / "offer-detail-response.json").is_file()
        and (_repo_examples_dir() / "offer-accept-request.json").is_file(),
        "repository API fixtures unavailable",
    )
    def test_repo_offer_detail_fixture_and_accept_digest(self) -> None:
        examples = _repo_examples_dir()
        raw_bytes = (examples / "offer-detail-response.json").read_bytes()
        raw_text = raw_bytes.decode("utf-8")
        parsed = json.loads(raw_text)
        accept_req = json.loads((examples / "offer-accept-request.json").read_bytes())

        expected_metadata_digest = "166d130902115c21f249e2432f4cf605926cfdff345f38d573f13fea37e6b756"
        expected_file_digest = "de541afdc888a29e740aa4fb394b67ff725f17279e083812fc61b85af73276ee"

        for payload in (raw_bytes, raw_text, parsed):
            with self.subTest(kind=type(payload).__name__):
                verified = verify_offer_manifest(payload)
                self.assertIsInstance(verified, VerifiedOfferManifest)
                self.assertEqual(verified.manifest_sha256, expected_metadata_digest)
                self.assertEqual(verified.file_sha256, expected_file_digest)
                self.assertEqual(verified.file_sha256, verified.manifest.sha256)
                self.assertNotEqual(verified.manifest_sha256, verified.file_sha256)
                self.assertEqual(verified.manifest_sha256, accept_req["manifest_sha256"])
                self.assertEqual(_sha256_hex(verified.canonical_bytes), verified.manifest_sha256)

    def test_self_contained_valid_offers_empty_unicode_and_formatting_invariance(self) -> None:
        empty_manifest = _make_manifest(b"", name="empty.bin", piece_size=4096, batch_size=8192)
        empty_offer = _make_offer(empty_manifest, include_envelope=False)
        empty_verified = verify_offer_manifest(empty_offer)
        self.assertEqual(empty_verified.file_sha256, _sha256_hex(b""))
        self.assertEqual(empty_verified.manifest_sha256, empty_manifest.manifest_sha256())
        self.assertNotEqual(empty_verified.manifest_sha256, empty_verified.file_sha256)

        unicode_name = "Cafe\u0301-\U0001f680.bin"
        unicode_manifest = _make_manifest(b"abcdefghij", name=unicode_name)
        unicode_offer = _make_offer(unicode_manifest)

        pretty_ascii = json.dumps(unicode_offer, ensure_ascii=True, indent=2)
        reordered_manifest = dict(reversed(list(unicode_offer["manifest"].items())))
        reordered_offer = dict(reversed(list((unicode_offer | {"manifest": reordered_manifest}).items())))
        compact_utf8 = json.dumps(reordered_offer, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        from_pretty = verify_offer_manifest(pretty_ascii)
        from_compact = verify_offer_manifest(compact_utf8)
        self.assertEqual(from_pretty, from_compact)
        self.assertEqual(from_pretty.manifest.name, unicode_name)
        self.assertIn(f'"name":"{unicode_name}"'.encode("utf-8"), from_pretty.canonical_bytes)
        self.assertEqual(from_pretty.canonical_bytes, unicode_manifest.canonical_bytes())

        with self.assertRaises(FrozenInstanceError):
            from_pretty.manifest_sha256 = "0" * 64  # type: ignore[misc]

    def test_rejects_tampered_metadata_and_file_sha256_confusion(self) -> None:
        # Using whole-file sha256 as manifest_sha256 must fail.
        confused = copy.deepcopy(self.offer)
        confused["manifest_sha256"] = confused["manifest"]["sha256"]
        self.assert_offer_error(confused, MANIFEST_DIGEST_MISMATCH)

        # Mutating any manifest field without updating manifest_sha256 must fail.
        mutations = (
            ("name", lambda m, o: (m.__setitem__("name", "tampered.bin"), o.__setitem__("file_name", "tampered.bin"))),
            ("piece_size", lambda m, o: self._replace_manifest(o, _make_manifest(b"abcdefghij", piece_size=5, batch_size=10))),
            ("batch_size", lambda m, o: self._replace_manifest(o, _make_manifest(b"abcdefghij", piece_size=3, batch_size=9))),
            ("size_and_file", lambda m, o: self._replace_manifest(o, _make_manifest(b"abcdefghi"))),
            ("file_sha256", lambda m, o: m.__setitem__("sha256", "0" * 64)),
            ("piece_sha256", lambda m, o: m["pieces"][0].__setitem__("sha256", "0" * 64)),
            ("batch_sha256", lambda m, o: m["batches"][1].__setitem__("sha256", "f" * 64)),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                tampered = copy.deepcopy(self.offer)
                mutate(tampered["manifest"], tampered)
                self.assert_offer_error(tampered, MANIFEST_DIGEST_MISMATCH)

    @staticmethod
    def _replace_manifest(offer: dict[str, object], replacement: Manifest) -> None:
        offer["manifest"] = json.loads(replacement.to_json())
        offer["file_name"] = replacement.name
        offer["size"] = replacement.size

    def test_rejects_missing_or_invalid_manifest_digest(self) -> None:
        missing_key = copy.deepcopy(self.offer)
        del missing_key["manifest_sha256"]
        self.assert_offer_error(missing_key, MISSING_MANIFEST_DIGEST)

        none_digest = copy.deepcopy(self.offer)
        none_digest["manifest_sha256"] = None
        self.assert_offer_error(none_digest, MISSING_MANIFEST_DIGEST)

        valid_digest = self.offer["manifest_sha256"]
        assert isinstance(valid_digest, str)
        invalid_values: tuple[object, ...] = (
            "",
            "abc",
            valid_digest[:-1],
            valid_digest + "0",
            valid_digest.upper(),
            valid_digest + "\n",
            "g" * 64,
            12345,
            [],
            {},
        )
        for bad_digest in invalid_values:
            with self.subTest(bad_digest=bad_digest):
                broken = copy.deepcopy(self.offer)
                broken["manifest_sha256"] = bad_digest
                self.assert_offer_error(broken, INVALID_MANIFEST_DIGEST)

    def test_rejects_missing_or_invalid_manifest_structure(self) -> None:
        missing_key = copy.deepcopy(self.offer)
        del missing_key["manifest"]
        self.assert_offer_error(missing_key, MISSING_MANIFEST)

        none_manifest = copy.deepcopy(self.offer)
        none_manifest["manifest"] = None
        self.assert_offer_error(none_manifest, MISSING_MANIFEST)

        for non_dict in ("{}", [], 123, True):
            with self.subTest(non_dict=non_dict):
                broken = copy.deepcopy(self.offer)
                broken["manifest"] = non_dict
                self.assert_offer_error(broken, INVALID_MANIFEST)

        invalid_manifest_cases = (
            ("version_2", lambda m: m.__setitem__("version", 2)),
            ("version_bool", lambda m: m.__setitem__("version", True)),
            ("name_parent", lambda m: m.__setitem__("name", "../bad.bin")),
            ("name_slash", lambda m: m.__setitem__("name", "dir/bad.bin")),
            ("name_nul", lambda m: m.__setitem__("name", "bad\x00.bin")),
            ("name_surrogate", lambda m: m.__setitem__("name", "bad\ud800.bin")),
            ("extra_key", lambda m: m.__setitem__("extra", 1)),
            ("bad_piece_size", lambda m: m.__setitem__("piece_size", 0)),
            ("bad_batch_multiple", lambda m: m.__setitem__("batch_size", 5)),
            ("missing_pieces", lambda m: m.__setitem__("pieces", [])),
            ("bad_segment_layout", lambda m: m["batches"][0].__setitem__("offset", 1)),
            ("extra_segment_key", lambda m: m["pieces"][0].__setitem__("extra", 0)),
        )
        for label, mutate in invalid_manifest_cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(self.offer)
                mutate(broken["manifest"])
                broken["manifest_sha256"] = "0" * 64
                self.assert_offer_error(broken, INVALID_MANIFEST)

        # Empty file with non-empty SHA-256 must fail manifest validation.
        empty_bad = _make_offer(_make_manifest(b"", name="empty.bin", piece_size=4, batch_size=8))
        empty_bad["manifest"]["sha256"] = _sha256_hex(b"x")
        self.assert_offer_error(empty_bad, INVALID_MANIFEST)

    def test_rejects_duplicate_json_keys_and_invalid_raw_json_or_payload(self) -> None:
        raw = json.dumps(self.offer)
        duplicate_cases = (
            ("envelope", raw.replace('"state": "PENDING"', '"state": "PENDING", "state": "EXPIRED"', 1)),
            ("manifest_key", raw.replace('"version": 1', '"version": 2, "\\u0076ersion": 1', 1)),
            ("piece_key", raw.replace('"index": 0', '"index": 1, "index": 0', 1)),
            ("batch_key", raw.replace('"size": 6', '"size": 6, "size": 5', 1)),
        )
        for label, payload in duplicate_cases:
            with self.subTest(label=label):
                self.assert_offer_error(payload, DUPLICATE_JSON_KEY)
                self.assert_offer_error(payload.encode("utf-8"), DUPLICATE_JSON_KEY)

        invalid_json_cases: tuple[tuple[str, str | bytes], ...] = (
            ("syntax_error", '{"manifest": '),
            ("invalid_utf8", b"\xff\xfe{}"),
            ("utf8_bom", b"\xef\xbb\xbf" + raw.encode("utf-8")),
            ("non_object_list", "[]"),
            ("non_object_string", '"hello"'),
            ("nan_constant", raw.replace('"size": 10', '"size": NaN', 1)),
            ("inf_constant", raw.replace('"size": 10', '"size": Infinity', 1)),
            ("neg_inf_constant", raw.replace('"size": 10', '"size": -Infinity', 1)),
        )
        for label, payload in invalid_json_cases:
            with self.subTest(label=label):
                self.assert_offer_error(payload, INVALID_OFFER_JSON)

        for non_mapping in (None, [], 123, True):
            with self.subTest(non_mapping=non_mapping):
                self.assert_offer_error(non_mapping, INVALID_OFFER_PAYLOAD)

    def test_rejects_offer_envelope_metadata_mismatch(self) -> None:
        mismatch_cases = (
            ("file_name_mismatch", {"file_name": "other.bin"}),
            ("file_name_non_str", {"file_name": 123}),
            ("size_mismatch", {"size": 999}),
            ("size_bool_true", {"size": True}),
            ("size_bool_false", {"size": False}),
            ("size_non_int", {"size": "10"}),
        )
        for label, override in mismatch_cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(self.offer)
                broken.update(override)
                self.assert_offer_error(broken, OFFER_METADATA_MISMATCH)
