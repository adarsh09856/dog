"""Cryptographic proof format for a future enrolled client installation.

Verification alone does not prevent replay: the owner must also atomically
consume each nonce before accepting a signed request.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

_DOMAIN = b"kodewaves-owner-check-v1\n"
_ENROLLMENT_DOMAIN = b"kodewaves-installation-enrollment-v1\n"
_REASONS = frozenset({
    "unknown", "modified_file", "missing_file", "added_file",
    "invalid_manifest", "missing_manifest", "missing_trust_root",
})


class InstallationIdentityError(ValueError):
    """An installation key or proof is malformed, expired or invalid."""


def _decode_urlsafe(value: str, length: int) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InstallationIdentityError("Invalid installation identity encoding")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError as exc:
        raise InstallationIdentityError("Invalid installation identity encoding") from exc
    if len(decoded) != length or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
        raise InstallationIdentityError("Invalid installation identity encoding")
    return decoded


def _encode_urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def owner_check_message(
    *, installation_id: str, license_token: str, nonce: str, issued_at: int,
    integrity_ok: bool, integrity_finding: dict[str, Any] | None,
) -> bytes:
    """Build the canonical, domain-separated bytes signed by an installation."""
    if not isinstance(installation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", installation_id):
        raise InstallationIdentityError("Invalid installation ID")
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", nonce):
        raise InstallationIdentityError("Invalid owner-check nonce")
    if isinstance(issued_at, bool) or not isinstance(issued_at, int) or not 0 <= issued_at <= 2**53 - 1:
        raise InstallationIdentityError("Invalid owner-check timestamp")
    if not isinstance(integrity_ok, bool) or (integrity_ok and integrity_finding is not None):
        raise InstallationIdentityError("Invalid integrity result")
    if not isinstance(license_token, str) or not license_token or not license_token.isascii():
        raise InstallationIdentityError("Invalid installation license token")

    finding = None
    if integrity_finding is not None:
        if not isinstance(integrity_finding, dict) or set(integrity_finding) - {
            "reason", "component", "expected_sha256", "observed_sha256",
        }:
            raise InstallationIdentityError("Invalid integrity finding")
        reason = integrity_finding.get("reason")
        component = integrity_finding.get("component")
        if not isinstance(reason, str) or reason not in _REASONS or not isinstance(component, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,500}", component):
            raise InstallationIdentityError("Invalid integrity finding")
        finding = {"reason": reason, "component": component}
        for field in ("expected_sha256", "observed_sha256"):
            value = integrity_finding.get(field)
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)):
                raise InstallationIdentityError("Invalid integrity finding digest")
            finding[field] = value

    payload = {
        "installation_id": installation_id,
        "license_sha256": hashlib.sha256(license_token.encode("ascii")).hexdigest(),
        "nonce": nonce,
        "issued_at": issued_at,
        "integrity_ok": integrity_ok,
        "integrity_finding": finding,
    }
    return _DOMAIN + json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_owner_check(private_key: bytes, **fields: Any) -> str:
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (TypeError, ValueError) as exc:
        raise InstallationIdentityError("Invalid installation private key") from exc
    return _encode_urlsafe(key.sign(owner_check_message(**fields)))


def owner_check_payload(
    *, installation_id: str, license_token: str, nonce: str, integrity_ok: bool,
    integrity_finding: dict[str, Any] | None, private_key_path: str = "", issued_at: int | None = None,
) -> dict[str, Any]:
    """Attach a proof when configured; never fall back to bearer-only on key errors."""
    payload = {"nonce": nonce, "integrity_ok": integrity_ok, "integrity_finding": integrity_finding}
    if not private_key_path:
        return payload
    try:
        private_key = Path(private_key_path).read_bytes()
    except OSError as exc:
        raise InstallationIdentityError("Installation private key is unavailable") from exc
    timestamp = int(time.time()) if issued_at is None else issued_at
    payload["proof_issued_at"] = timestamp
    payload["proof_signature"] = sign_owner_check(
        private_key, installation_id=installation_id, license_token=license_token,
        nonce=nonce, issued_at=timestamp, integrity_ok=integrity_ok, integrity_finding=integrity_finding,
    )
    return payload


def enrollment_message(
    *, installation_id: str, license_token: str, enrollment_token: str,
    public_key: str, nonce: str, issued_at: int,
) -> bytes:
    """Bind a one-time enrollment token to a license and a public key."""
    owner_check_message(
        installation_id=installation_id, license_token=license_token, nonce=nonce,
        issued_at=issued_at, integrity_ok=True, integrity_finding=None,
    )
    if not isinstance(enrollment_token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", enrollment_token):
        raise InstallationIdentityError("Invalid enrollment token")
    _decode_urlsafe(public_key, 32)
    payload = {
        "installation_id": installation_id,
        "license_sha256": hashlib.sha256(license_token.encode("ascii")).hexdigest(),
        "enrollment_sha256": hashlib.sha256(enrollment_token.encode("ascii")).hexdigest(),
        "public_key": public_key,
        "nonce": nonce,
        "issued_at": issued_at,
    }
    return _ENROLLMENT_DOMAIN + json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_enrollment(private_key: bytes, **fields: Any) -> str:
    try:
        key = Ed25519PrivateKey.from_private_bytes(private_key)
    except (TypeError, ValueError) as exc:
        raise InstallationIdentityError("Invalid installation private key") from exc
    return _encode_urlsafe(key.sign(enrollment_message(**fields)))


def verify_enrollment(public_key: str, signature: str, *, now: int | None = None, **fields: Any) -> None:
    """Verify key possession; the owner must atomically consume the token."""
    message = enrollment_message(public_key=public_key, **fields)
    current = int(time.time()) if now is None else now
    if not current - 90 <= fields["issued_at"] <= current + 30:
        raise InstallationIdentityError("Enrollment proof is outside its validity window")
    try:
        Ed25519PublicKey.from_public_bytes(_decode_urlsafe(public_key, 32)).verify(
            _decode_urlsafe(signature, 64), message
        )
    except InvalidSignature as exc:
        raise InstallationIdentityError("Enrollment proof signature is invalid") from exc


def verify_owner_check(
    public_key: str, signature: str, *, now: int | None = None,
    max_age_seconds: int = 90, future_skew_seconds: int = 30, **fields: Any,
) -> None:
    """Verify proof contents and freshness; the caller must also reject nonce replay."""
    message = owner_check_message(**fields)
    current = int(time.time()) if now is None else now
    if not current - max_age_seconds <= fields["issued_at"] <= current + future_skew_seconds:
        raise InstallationIdentityError("Installation proof is outside its validity window")
    try:
        Ed25519PublicKey.from_public_bytes(_decode_urlsafe(public_key, 32)).verify(
            _decode_urlsafe(signature, 64), message
        )
    except InvalidSignature as exc:
        raise InstallationIdentityError("Installation proof signature is invalid") from exc
