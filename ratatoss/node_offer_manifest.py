"""Verify an incoming offer's manifest before the Node allows user consent.

Callers in #9 should pass the raw UTF-8 HTTP response ``bytes`` or ``str`` from
``GET /v1/offers/{offer_id}`` directly into :func:`verify_offer_manifest` so
duplicate JSON object keys at any nesting level are detected before keys can be
collapsed by a standard JSON parser:

    try:
        verified = verify_offer_manifest(raw_offer_response_bytes)
    except OfferManifestError as exc:
        # Block user confirmation, skip NodeStore.register_target(...),
        # and do not send POST /v1/offers/{offer_id}/decision ACCEPT.
        ...

Distinct digests in :class:`VerifiedOfferManifest`:
- ``manifest_sha256``: SHA-256 of the validated v1 manifest's canonical UTF-8
  JSON metadata (sent in ``POST /v1/offers/{offer_id}/decision`` and stored
  in ``local_jobs.manifest_sha256``).
- ``file_sha256``: SHA-256 of the whole file payload (``manifest.sha256``).

Error codes raised via :class:`OfferManifestError`:
- ``DUPLICATE_JSON_KEY``: Raw JSON contains duplicate keys at any depth.
- ``INVALID_OFFER_JSON``: Raw JSON is malformed, invalid UTF-8, uses BOM,
  contains ``NaN``/``Infinity``, exceeds recursion depth, or is not an object.
- ``INVALID_OFFER_PAYLOAD``: Input is not ``str``, ``bytes``, or ``Mapping``.
- ``MISSING_MANIFEST_DIGEST``: ``manifest_sha256`` is absent or ``None``.
- ``INVALID_MANIFEST_DIGEST``: ``manifest_sha256`` is not 64 lowercase hex chars.
- ``MISSING_MANIFEST``: ``manifest`` is absent or ``None``.
- ``INVALID_MANIFEST``: ``manifest`` fails v1 schema or segment validation.
- ``MANIFEST_DIGEST_MISMATCH``: Computed ``manifest.manifest_sha256()`` differs
  from ``offer["manifest_sha256"]``.
- ``OFFER_METADATA_MISMATCH``: Optional envelope ``file_name`` or ``size`` does
  not match the validated manifest's ``name`` or ``size``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re

from .manifest import Manifest, decode_manifest_object

DUPLICATE_JSON_KEY = "DUPLICATE_JSON_KEY"
INVALID_OFFER_JSON = "INVALID_OFFER_JSON"
INVALID_OFFER_PAYLOAD = "INVALID_OFFER_PAYLOAD"
MISSING_MANIFEST_DIGEST = "MISSING_MANIFEST_DIGEST"
INVALID_MANIFEST_DIGEST = "INVALID_MANIFEST_DIGEST"
MISSING_MANIFEST = "MISSING_MANIFEST"
INVALID_MANIFEST = "INVALID_MANIFEST"
MANIFEST_DIGEST_MISMATCH = "MANIFEST_DIGEST_MISMATCH"
OFFER_METADATA_MISMATCH = "OFFER_METADATA_MISMATCH"

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class OfferManifestError(ValueError):
    """Raised when an offer's manifest or metadata fails verification."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class VerifiedOfferManifest:
    """Validated manifest alongside its canonical metadata digest and payload hash."""

    manifest: Manifest
    manifest_sha256: str
    file_sha256: str
    canonical_bytes: bytes


def verify_offer_manifest(offer: Mapping[str, object] | str | bytes) -> VerifiedOfferManifest:
    """Validate an offer's manifest and canonical metadata digest before consent.

    Prefer passing raw UTF-8 JSON ``bytes`` or ``str`` from
    ``GET /v1/offers/{offer_id}`` so duplicate keys are rejected before parsing.
    """
    if isinstance(offer, (str, bytes)):
        try:
            offer = decode_manifest_object(offer)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise OfferManifestError(INVALID_OFFER_JSON, f"Invalid offer JSON: {exc}") from exc
        except ValueError as exc:
            if str(exc) == "Duplicate JSON object key":
                raise OfferManifestError(DUPLICATE_JSON_KEY, str(exc)) from exc
            raise OfferManifestError(INVALID_OFFER_JSON, str(exc)) from exc
    elif not isinstance(offer, Mapping):
        raise OfferManifestError(
            INVALID_OFFER_PAYLOAD, "Expected an offer object or JSON payload"
        )

    if "manifest_sha256" not in offer or offer["manifest_sha256"] is None:
        raise OfferManifestError(MISSING_MANIFEST_DIGEST, "Offer is missing manifest_sha256")
    declared_digest = offer["manifest_sha256"]
    if not isinstance(declared_digest, str) or not _SHA256_HEX.fullmatch(declared_digest):
        raise OfferManifestError(
            INVALID_MANIFEST_DIGEST, "Offer manifest_sha256 must be 64 lowercase hex digits"
        )

    if "manifest" not in offer or offer["manifest"] is None:
        raise OfferManifestError(MISSING_MANIFEST, "Offer is missing manifest")
    raw_manifest = offer["manifest"]
    if not isinstance(raw_manifest, dict):
        raise OfferManifestError(INVALID_MANIFEST, "Offer manifest must be a JSON object")
    try:
        manifest = Manifest.from_dict(raw_manifest)
    except ValueError as exc:
        raise OfferManifestError(INVALID_MANIFEST, f"Invalid offer manifest: {exc}") from exc

    canonical = manifest.canonical_bytes()
    computed_digest = manifest.manifest_sha256()
    if computed_digest != declared_digest:
        raise OfferManifestError(
            MANIFEST_DIGEST_MISMATCH,
            "Offer manifest_sha256 does not match the manifest metadata digest",
        )

    if "file_name" in offer:
        file_name = offer["file_name"]
        if not isinstance(file_name, str) or file_name != manifest.name:
            raise OfferManifestError(
                OFFER_METADATA_MISMATCH,
                "Offer file_name does not match manifest name",
            )
    if "size" in offer:
        size = offer["size"]
        if type(size) is not int or size != manifest.size:
            raise OfferManifestError(
                OFFER_METADATA_MISMATCH,
                "Offer size does not match manifest size",
            )

    return VerifiedOfferManifest(
        manifest=manifest,
        manifest_sha256=computed_digest,
        file_sha256=manifest.sha256,
        canonical_bytes=canonical,
    )
