"""Validation helpers for owner-signed client update releases and reports.

The owner API stores public release metadata only. Release signatures are
created out of band with the release private key and verified here with the
public key baked into the approved client/API trust configuration.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import re
import time
import uuid
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from api.services.owner_trust import OwnerTrustError, trusted_release_public_key

_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,99}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
_STATUS_DOMAIN = b"kodewaves-client-update-report-v1\n"
UPDATE_REPORT_STATUSES = frozenset({
    "staged", "downloading", "applying", "applied", "failed", "rolled_back",
})
TERMINAL_UPDATE_REPORT_STATUSES = frozenset({"failed", "rolled_back"})
UPDATE_REPORT_TRANSITIONS = {
    "staged": frozenset({"downloading", "failed"}),
    "downloading": frozenset({"applying", "failed"}),
    "applying": frozenset({"applied", "failed", "rolled_back"}),
    "applied": frozenset({"rolled_back"}),
    "failed": frozenset(),
    "rolled_back": frozenset(),
}


class ClientUpdateProtocolError(ValueError):
    """An update release or installation report violates the signed contract."""


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def parse_release_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ClientUpdateProtocolError("Release versions must use canonical X.Y.Z format")
    match = _VERSION_RE.fullmatch(value)
    if match is None:
        raise ClientUpdateProtocolError("Release versions must use canonical X.Y.Z format")
    parts = tuple(int(part) for part in match.groups())
    if any(part > 2**31 - 1 for part in parts):
        raise ClientUpdateProtocolError("Release version component is too large")
    return parts


def validate_current_version(value: str) -> str:
    parse_release_version(value)
    return value


def _decode_urlsafe(value: str, expected_bytes: int) -> bytes:
    if not isinstance(value, str) or not _SIGNATURE_RE.fullmatch(value):
        raise ClientUpdateProtocolError("Release signature is invalid")
    try:
        decoded = base64.b64decode(value + "==", altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ClientUpdateProtocolError("Release signature is invalid") from exc
    if len(decoded) != expected_bytes or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise ClientUpdateProtocolError("Release signature is invalid")
    return decoded


def _validate_archive_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048 or any(ord(ch) < 33 for ch in value):
        raise ClientUpdateProtocolError("Archive URL must be a valid HTTPS URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise ClientUpdateProtocolError("Archive URL must be a valid HTTPS URL") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not parsed.path
        or value.endswith(":")
        or (port is not None and port != 443)
    ):
        raise ClientUpdateProtocolError("Archive URL must be a valid HTTPS URL")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").lower()
        ipaddress.ip_address(ascii_hostname)
    except UnicodeError as exc:
        raise ClientUpdateProtocolError("Archive URL hostname is invalid") from exc
    except ValueError:
        pass
    else:
        raise ClientUpdateProtocolError("Archive URL must use a DNS hostname")
    labels = ascii_hostname.split(".")
    if len(labels) < 2 or ascii_hostname.endswith((".local", ".internal", ".localhost")) or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ClientUpdateProtocolError("Archive URL hostname is invalid")
    return value


def release_signature_payload(
    *, release_id: str, version: str, archive_url: str, archive_sha256: str,
    min_current_version: str, notes: str,
) -> dict[str, str]:
    """Canonical public fields covered by the detached release signature.

    The detached Ed25519 signature covers canonical UTF-8 JSON for this object;
    the archive digest therefore binds the downloaded bytes. The envelope is
    also included inside each owner-signed installation status response.
    """
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        raise ClientUpdateProtocolError("Release ID is invalid")
    version_tuple = parse_release_version(version)
    min_tuple = parse_release_version(min_current_version)
    if min_tuple > version_tuple:
        raise ClientUpdateProtocolError("Minimum current version cannot exceed the release version")
    if not isinstance(archive_sha256, str) or not _DIGEST_RE.fullmatch(archive_sha256):
        raise ClientUpdateProtocolError("Archive SHA-256 must be lowercase hexadecimal")
    if not isinstance(notes, str) or len(notes) > 4000 or "\x00" in notes:
        raise ClientUpdateProtocolError("Release notes must be at most 4000 characters")
    return {
        "release_id": release_id,
        "version": version,
        "archive_url": _validate_archive_url(archive_url),
        "archive_sha256": archive_sha256,
        "min_current_version": min_current_version,
        "notes": notes.strip(),
    }


def verify_release_envelope(envelope: dict[str, object]) -> dict[str, str]:
    """Validate immutable metadata and verify its detached Ed25519 signature."""
    required = {
        "release_id", "version", "archive_url", "archive_sha256",
        "archive_signature", "min_current_version", "notes",
    }
    if not isinstance(envelope, dict) or set(envelope) != required:
        raise ClientUpdateProtocolError("Release envelope fields do not match the update contract")
    payload = release_signature_payload(
        release_id=envelope["release_id"],
        version=envelope["version"],
        archive_url=envelope["archive_url"],
        archive_sha256=envelope["archive_sha256"],
        min_current_version=envelope["min_current_version"],
        notes=envelope["notes"],
    )
    signature = _decode_urlsafe(envelope["archive_signature"], 64)
    try:
        public_key = base64.b64decode(
            trusted_release_public_key() + "=", altchars=b"-_", validate=True
        )
        if len(public_key) != 32:
            raise ValueError("invalid release key")
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, canonical_json(payload))
    except OwnerTrustError as exc:
        raise ClientUpdateProtocolError("Approved release verification key is unavailable") from exc
    except (ValueError, base64.binascii.Error, InvalidSignature) as exc:
        raise ClientUpdateProtocolError("Release envelope signature is invalid") from exc
    return {**payload, "archive_signature": envelope["archive_signature"]}


def release_update_is_eligible(current_version: str, release: dict[str, str]) -> bool:
    """Only offer forward updates from a compatible installed version."""
    current = parse_release_version(current_version)
    target = parse_release_version(release["version"])
    minimum = parse_release_version(release["min_current_version"])
    return minimum <= current < target


def update_report_transition_allowed(
    *, rollout_state: str, current_status: str, requested_status: str,
    has_newer_rollout: bool,
) -> bool:
    """Prevent status regression while permitting a last safe rollback report.

    Once a rollout completed, only an applied target may report rollback, and
    only until any newer rollout has been staged for that installation. A
    paused/stopped rollout may still receive the final result for a target
    that had already entered applying when the owner changed rollout state.
    """
    if rollout_state == "active":
        return requested_status in UPDATE_REPORT_TRANSITIONS.get(current_status, ())
    if rollout_state in {"paused", "stopped"}:
        return current_status == "applying" and requested_status in {"applied", "failed", "rolled_back"}
    return (
        rollout_state == "completed"
        and current_status == "applied"
        and requested_status == "rolled_back"
        and not has_newer_rollout
    )


def update_report_message(
    *, installation_id: str, license_token: str, rollout_id: str, release_id: str,
    version: str, nonce: str, issued_at: int, status: str, detail: str = "",
) -> bytes:
    if not isinstance(installation_id, str) or not _RELEASE_ID_RE.fullmatch(installation_id):
        raise ClientUpdateProtocolError("Installation ID is invalid")
    if not isinstance(license_token, str) or not license_token.isascii() or not license_token:
        raise ClientUpdateProtocolError("Installation license token is invalid")
    try:
        if not isinstance(rollout_id, str) or str(uuid.UUID(rollout_id)) != rollout_id:
            raise ValueError("non-canonical UUID")
    except (ValueError, AttributeError) as exc:
        raise ClientUpdateProtocolError("Rollout ID is invalid")
    if not isinstance(release_id, str) or not _RELEASE_ID_RE.fullmatch(release_id):
        raise ClientUpdateProtocolError("Release ID is invalid")
    parse_release_version(version)
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", nonce):
        raise ClientUpdateProtocolError("Update report nonce is invalid")
    if type(issued_at) is not int or not 0 <= issued_at <= 2**53 - 1:
        raise ClientUpdateProtocolError("Update report timestamp is invalid")
    if status not in UPDATE_REPORT_STATUSES:
        raise ClientUpdateProtocolError("Update report status is invalid")
    if not isinstance(detail, str) or len(detail) > 1000:
        raise ClientUpdateProtocolError("Update report detail is invalid")
    payload = {
        "installation_id": installation_id,
        "license_sha256": hashlib.sha256(license_token.encode("ascii")).hexdigest(),
        "rollout_id": rollout_id,
        "release_id": release_id,
        "version": version,
        "nonce": nonce,
        "issued_at": issued_at,
        "status": status,
        "detail": detail.strip(),
    }
    return _STATUS_DOMAIN + canonical_json(payload)


def verify_update_report(
    public_key: str, signature: str, *, now: int | None = None,
    max_age_seconds: int = 300, future_skew_seconds: int = 30, **fields: object,
) -> None:
    message = update_report_message(**fields)
    current = time.time() if now is None else now
    issued_at = fields["issued_at"]
    if type(issued_at) is not int or not current - max_age_seconds <= issued_at <= current + future_skew_seconds:
        raise ClientUpdateProtocolError("Update report is outside its validity window")
    try:
        key = base64.b64decode(public_key + "=", altchars=b"-_", validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(_decode_urlsafe(signature, 64), message)
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise ClientUpdateProtocolError("Update report signature is invalid") from exc
