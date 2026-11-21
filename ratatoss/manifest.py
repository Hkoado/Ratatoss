"""Versioned manifests for contiguous pieces and batches."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import BinaryIO

DEFAULT_PIECE_SIZE = 4 * 1024**2
DEFAULT_BATCH_SIZE = 64 * 1024**2
READ_SIZE = 1024**2


@dataclass(frozen=True, slots=True)
class Segment:
    index: int
    offset: int
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Manifest:
    name: str
    size: int
    piece_size: int
    batch_size: int
    sha256: str
    pieces: tuple[Segment, ...]
    batches: tuple[Segment, ...]
    version: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def canonical_bytes(self) -> bytes:
        """Return the validated v1 manifest's canonical UTF-8 encoding."""
        self.validate()
        return json.dumps(
            asdict(self), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")

    def manifest_sha256(self) -> str:
        """Return the SHA-256 of the manifest metadata's canonical bytes."""
        return sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Manifest":
        """Validate raw manifest JSON while retaining duplicate-key detection."""
        return cls.from_dict(decode_manifest_object(raw))

    @classmethod
    def from_dict(cls, fields: dict) -> "Manifest":
        """Validate a JSON object from a decoder that rejects duplicate keys."""
        if not isinstance(fields, dict):
            raise ValueError("Expected a manifest object")
        fields = fields.copy()
        try:
            if type(fields["version"]) is not int or fields["version"] != 1:
                raise ValueError("Unsupported manifest version")
            for key in ("pieces", "batches"):
                if not isinstance(fields[key], list):
                    raise ValueError(f"Expected a list for {key}")
                fields[key] = tuple(Segment(**item) for item in fields[key])
            result = cls(**fields)
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid manifest fields") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise ValueError("Unsupported manifest version")
        if not isinstance(self.name, str) or self.name in ("", ".", ".."):
            raise ValueError("Invalid manifest filename")
        if any(char in self.name for char in ("/", "\\", "\x00")):
            raise ValueError("Invalid manifest filename")
        if any("\ud800" <= char <= "\udfff" for char in self.name):
            raise ValueError("Invalid Unicode surrogate in manifest filename")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("Invalid file size")
        _validate_sizes(self.piece_size, self.batch_size)
        _validate_digest(self.sha256)
        if self.size == 0 and self.sha256 != sha256(b"").hexdigest():
            raise ValueError("Invalid SHA-256 for an empty file")
        for segments, span in ((self.pieces, self.piece_size), (self.batches, self.batch_size)):
            if len(segments) != (self.size + span - 1) // span:
                raise ValueError("Invalid segment count")
            for index, segment in enumerate(segments):
                offset = index * span
                expected = (index, offset, min(span, self.size - offset))
                coordinates = (segment.index, segment.offset, segment.size)
                if any(type(value) is not int for value in coordinates) or coordinates != expected:
                    raise ValueError(f"Invalid segment layout at index {index}")
                _validate_digest(segment.sha256)


def decode_manifest_object(raw: str | bytes) -> dict:
    """Decode a manifest or its API envelope before keys can be collapsed."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    result = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _validate_sizes(piece_size: int, batch_size: int) -> None:
    if type(piece_size) is not int or piece_size <= 0:
        raise ValueError("Piece size must be a positive integer")
    if type(batch_size) is not int or batch_size <= 0 or batch_size % piece_size:
        raise ValueError("Batch size must be a positive multiple of piece size")


def _validate_digest(digest: str) -> None:
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("Invalid SHA-256 digest")


def _scan(source: BinaryIO, path: Path, piece_size: int, batch_size: int) -> Manifest:
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Expected a regular file")
    pieces = []
    batches = []
    whole_hash = sha256()
    cursor = 0
    while cursor < before.st_size:
        batch_start = cursor
        batch_end = min(batch_start + batch_size, before.st_size)
        batch_hash = sha256()
        while cursor < batch_end:
            piece_start = cursor
            piece_end = min(piece_start + piece_size, batch_end)
            piece_hash = sha256()
            while cursor < piece_end:
                block = source.read(min(READ_SIZE, piece_end - cursor))
                if not block:
                    raise ValueError("File size changed while reading")
                cursor += len(block)
                whole_hash.update(block)
                batch_hash.update(block)
                piece_hash.update(block)
            pieces.append(Segment(len(pieces), piece_start, cursor - piece_start, piece_hash.hexdigest()))
        batches.append(Segment(len(batches), batch_start, cursor - batch_start, batch_hash.hexdigest()))
    after = os.fstat(source.fileno())
    if source.read(1) or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("File changed while reading")
    return Manifest(path.name, cursor, piece_size, batch_size, whole_hash.hexdigest(),
                    tuple(pieces), tuple(batches))


def build_manifest(path: Path, *, piece_size: int = DEFAULT_PIECE_SIZE,
                   batch_size: int = DEFAULT_BATCH_SIZE) -> Manifest:
    """Read content once with bounded buffers and retain segment metadata."""
    _validate_sizes(piece_size, batch_size)
    path = Path(path)
    if not path.is_file():
        raise ValueError("Expected a regular file")
    with path.open("rb") as source:
        result = _scan(source, path, piece_size, batch_size)
    result.validate()
    return result


def verify_file(path: Path, manifest: Manifest) -> bool:
    """Compare file size and every hash, allowing a different local filename."""
    manifest.validate()
    found = build_manifest(path, piece_size=manifest.piece_size, batch_size=manifest.batch_size)
    return (found.size, found.sha256, found.pieces, found.batches) == (
        manifest.size, manifest.sha256, manifest.pieces, manifest.batches
    )


def verify_batch(path: Path, manifest: Manifest, index: int) -> bool:
    """Check a standalone staged batch against its batch and piece hashes."""
    manifest.validate()
    if type(index) is not int or not 0 <= index < len(manifest.batches):
        raise ValueError("Batch index out of range")
    target = manifest.batches[index]
    found = build_manifest(path, piece_size=manifest.piece_size, batch_size=manifest.batch_size)
    start = target.offset // manifest.piece_size
    count = (target.size + manifest.piece_size - 1) // manifest.piece_size
    expected = manifest.pieces[start:start + count]
    return (found.size == target.size and found.sha256 == target.sha256
            and tuple(piece.sha256 for piece in found.pieces)
            == tuple(piece.sha256 for piece in expected))
