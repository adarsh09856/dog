"""Offline-verifiable client installation licenses.

The distributable receives only the Ed25519 public key and signed license. The
private signing key belongs in the Kodewaves owner service and must never ship
with a client image.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from api.services.deployment_edition import runtime_edition
from api.services.owner_trust import OwnerTrustError, trusted_license_public_keys


class InstallationLicenseError(ValueError):
    """License is missing, invalid, expired, unbound or lacks an entitlement."""


class InstallationFeatureError(InstallationLicenseError):
    """The signed license does not grant a requested product feature."""


@dataclass(frozen=True)
class InstallationLicense:
    installation_id: str
    customer_id: str
    edition: str
    domains: tuple[str, ...]
    expires_at: int
    features: frozenset[str]
    limits: dict[str, int]
    ip_ranges: tuple[str, ...] = ()


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("invalid URL-safe Base64")
    unpadded = value.rstrip("=")
    padding = len(value) - len(unpadded)
    required_padding = -len(unpadded) % 4
    if len(unpadded) % 4 == 1 or padding not in (0, required_padding):
        raise ValueError("invalid URL-safe Base64 length")
    padded = unpadded + "=" * required_padding
    decoded = base64.b64decode(padded, altchars=b"-_", validate=True)
    if _b64url_encode(decoded) != unpadded:
        raise ValueError("non-canonical URL-safe Base64")
    return decoded


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _canonical_domain(value: str) -> str:
    domain = value.strip().rstrip(".").lower()
    if not domain or "*" in domain or "/" in domain:
        raise InstallationLicenseError("License contains an invalid domain")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InstallationLicenseError("License contains an invalid domain") from exc
    if len(ascii_domain) > 253 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in ascii_domain.split(".")
    ):
        raise InstallationLicenseError("License contains an invalid domain")
    return ascii_domain


def get_installation_binding() -> str:
    """Read the public hostname configured by the installation operator."""
    from api.constants import PUBLIC_BASE_URL, PUBLIC_HOST

    configured_origin = PUBLIC_BASE_URL or PUBLIC_HOST or ""
    parsed = urlsplit(
        configured_origin if "://" in configured_origin else f"//{configured_origin}"
    )
    hostname = parsed.hostname or ""
    if not hostname:
        raise InstallationLicenseError(
            "Set PUBLIC_BASE_URL or PUBLIC_HOST to the licensed installation domain"
        )
    return hostname


def issue_license_token(claims: dict[str, Any], private_key: bytes) -> str:
    """Sign normalized JSON claims; intended for the owner-side issuer only."""
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = Ed25519PrivateKey.from_private_bytes(private_key).sign(payload)
    return f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"


def load_license(
    token: str | None = None,
    public_key: str | tuple[str, ...] | None = None,
    *,
    now: int | None = None,
) -> InstallationLicense:
    token = token if token is not None else os.getenv("KODEWAVES_LICENSE_TOKEN", "")
    if public_key is None:
        if runtime_edition() == "client":
            try:
                public_key = trusted_license_public_keys()
            except OwnerTrustError as exc:
                raise InstallationLicenseError(str(exc)) from exc
        else:
            public_key = os.getenv("KODEWAVES_LICENSE_PUBLIC_KEY", "")
    if not token or not public_key:
        raise InstallationLicenseError("Installation license is not configured")
    candidate_keys = (public_key,) if isinstance(public_key, str) else public_key
    try:
        payload_part, signature_part = token.split(".", 1)
        payload = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
        for candidate in candidate_keys:
            try:
                Ed25519PublicKey.from_public_bytes(_b64url_decode(candidate)).verify(
                    signature, payload
                )
                break
            except InvalidSignature:
                continue
        else:
            raise InvalidSignature
        claims = json.loads(payload)
    except InstallationLicenseError:
        raise
    except (ValueError, TypeError, json.JSONDecodeError, InvalidSignature) as exc:
        raise InstallationLicenseError("Installation license signature is invalid") from exc

    if not isinstance(claims, dict):
        raise InstallationLicenseError("Installation license claims are incomplete")
    timestamp = int(time.time()) if now is None else now
    try:
        issued_at = claims["iat"]
        expires_at = claims["exp"]
        raw_domains = claims["domains"]
        raw_ip_ranges = claims.get("ip_ranges", [])
        raw_features = claims["features"]
        raw_limits = claims.get("limits", {})
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or not isinstance(raw_domains, list)
            or not all(isinstance(domain, str) for domain in raw_domains)
            or not isinstance(raw_ip_ranges, list)
            or not all(isinstance(value, str) for value in raw_ip_ranges)
            or not isinstance(raw_features, list)
            or not all(isinstance(feature, str) for feature in raw_features)
            or not isinstance(raw_limits, dict)
            or not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in raw_limits.values()
            )
        ):
            raise InstallationLicenseError("Installation license claims are incomplete")
        installation_id = str(claims["installation_id"]).strip()
        customer_id = str(claims["customer_id"]).strip()
        edition = str(claims["edition"]).strip().lower()
        domains = tuple(sorted({_canonical_domain(d) for d in raw_domains}))
        ip_ranges = tuple(str(ipaddress.ip_network(x, strict=False)) for x in raw_ip_ranges)
        features = frozenset(raw_features)
        limits = {str(k): value for k, value in raw_limits.items()}
    except InstallationLicenseError:
        raise
    except (KeyError, ValueError, TypeError) as exc:
        raise InstallationLicenseError("Installation license claims are incomplete") from exc

    if timestamp < issued_at:
        raise InstallationLicenseError("Installation license is not active yet")
    if timestamp >= expires_at:
        raise InstallationLicenseError("Installation license has expired")
    if not installation_id or not customer_id or edition != "client" or not domains:
        raise InstallationLicenseError("Installation license claims are incomplete")
    if any(value < 0 for value in limits.values()):
        raise InstallationLicenseError("Installation license limits are invalid")

    return InstallationLicense(
        installation_id=installation_id,
        customer_id=customer_id,
        edition=edition,
        domains=domains,
        expires_at=expires_at,
        features=features,
        limits=limits,
        ip_ranges=ip_ranges,
    )


def validate_request_binding(
    license_data: InstallationLicense,
    *,
    hostname: str,
    installation_ip: str | None,
) -> None:
    if _canonical_domain(hostname) not in license_data.domains:
        raise InstallationLicenseError("This domain is not licensed for this installation")
    if license_data.ip_ranges:
        try:
            address = ipaddress.ip_address(installation_ip or "")
        except ValueError as exc:
            raise InstallationLicenseError("A valid client IP is required by this license") from exc
        if not any(address in ipaddress.ip_network(network) for network in license_data.ip_ranges):
            raise InstallationLicenseError("This IP address is not licensed for this installation")


def validate_installation_license(
    license_data: InstallationLicense,
    *,
    request_hostname: str | None = None,
) -> None:
    expected_id = os.getenv("KODEWAVES_INSTALLATION_ID", "").strip()
    if not expected_id:
        raise InstallationLicenseError("KODEWAVES_INSTALLATION_ID is not configured")
    if license_data.installation_id != expected_id:
        raise InstallationLicenseError("The license belongs to a different installation")
    hostname = request_hostname if request_hostname is not None else get_installation_binding()
    # Protected requests bind the signed domain to the actual Host header.
    # Background checks have no request and use the configured public origin.
    # IP ranges are enforced by the owner service against the source address
    # it observes, never SERVER_IP.
    if _canonical_domain(hostname) not in license_data.domains:
        raise InstallationLicenseError("This domain is not licensed for this installation")


def require_feature(license_data: InstallationLicense, feature: str) -> None:
    if feature not in license_data.features:
        raise InstallationFeatureError(f"The installation license does not include '{feature}'")


def require_limit(license_data: InstallationLicense, limit: str) -> int:
    value = license_data.limits.get(limit)
    if value is None:
        raise InstallationLicenseError(f"The installation license does not define '{limit}'")
    return value


def verify_installation_status(
    signed_status: str,
    *,
    public_key: str | tuple[str, ...],
    installation_id: str,
    license_token: str,
    nonce: str,
    now: int | None = None,
    max_stale_seconds: int = 0,
) -> bool:
    """Verify a fresh owner response and return whether the license is revoked."""
    return verify_installation_status_claims(
        signed_status,
        public_key=public_key,
        installation_id=installation_id,
        license_token=license_token,
        nonce=nonce,
        now=now,
        max_stale_seconds=max_stale_seconds,
    )["revoked"]


def verify_installation_status_claims(
    signed_status: str,
    *,
    public_key: str | tuple[str, ...],
    installation_id: str,
    license_token: str,
    nonce: str,
    now: int | None = None,
    max_stale_seconds: int = 0,
) -> dict[str, Any]:
    """Verify a signed owner response and return its validated claims."""
    try:
        payload_part, signature_part = signed_status.split(".", 1)
        payload = _b64url_decode(payload_part)
        candidate_keys = (public_key,) if isinstance(public_key, str) else public_key
        signature = _b64url_decode(signature_part)
        for candidate in candidate_keys:
            try:
                Ed25519PublicKey.from_public_bytes(_b64url_decode(candidate)).verify(
                    signature, payload
                )
                break
            except InvalidSignature:
                continue
        else:
            raise InvalidSignature
        status = json.loads(payload)
        timestamp = int(time.time()) if now is None else now
        if (
            not isinstance(status, dict)
            or status.get("kind") != "installation_status"
            or status.get("installation_id") != installation_id
            or status.get("license_sha256") != hashlib.sha256(license_token.encode("ascii")).hexdigest()
            or status.get("nonce") != nonce
            or not isinstance(status.get("revoked"), bool)
            or ("binding_valid" in status and not isinstance(status.get("binding_valid"), bool))
            or ("observed_ip" in status and status.get("observed_ip") is not None and not isinstance(status.get("observed_ip"), str))
            or type(status.get("issued_at")) is not int
            or type(status.get("expires_at")) is not int
            or status["issued_at"] > timestamp
            or max_stale_seconds < 0
            or status["expires_at"] + max_stale_seconds <= timestamp
            or status["expires_at"] - status["issued_at"] > 300
        ):
            raise InstallationLicenseError("Owner installation status is invalid")
        return status
    except InstallationLicenseError:
        raise
    except (ValueError, TypeError, UnicodeError, InvalidSignature) as exc:
        raise InstallationLicenseError("Owner installation status signature is invalid") from exc
