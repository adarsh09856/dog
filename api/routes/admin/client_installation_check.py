"""Authenticated owner status check for a deployed client installation."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.db.client_installations import (
    consume_installation_enrollment,
    get_client_installation_record,
    record_client_installation_check,
)
from api.routes.admin.client_installations import _owner_verification_signers
from api.services.installation_license import (
    InstallationLicenseError,
    issue_license_token,
    load_license,
)
from api.services.installation_identity import InstallationIdentityError, verify_enrollment, verify_owner_check

router = APIRouter(prefix="/client-installations", tags=["client-installation-check"])


def _observed_client_ip(request: Request) -> str | None:
    """Use the peer address; honor XFF only behind an explicitly trusted proxy."""
    peer = request.client.host if request.client else None
    if not peer:
        return None
    try:
        current = ipaddress.ip_address(peer)
        trusted = [
            ipaddress.ip_network(value.strip(), strict=False)
            for value in os.getenv("KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS", "").split(",")
            if value.strip()
        ]
    except ValueError:
        return None
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded or not any(current in network for network in trusted):
        return str(current)
    try:
        chain = [ipaddress.ip_address(value.strip()) for value in forwarded.split(",")]
    except ValueError:
        return None
    chain.append(current)
    while len(chain) > 1 and any(chain[-1] in network for network in trusted):
        chain.pop()
    return str(chain[-1])


def _license_ip_binding_valid(ip_ranges: tuple[str, ...], observed_ip: str | None) -> bool:
    """Match the owner's observed peer address against an optional license allowlist."""
    if not ip_ranges:
        return True
    try:
        address = ipaddress.ip_address(observed_ip or "")
        return any(address in ipaddress.ip_network(value) for value in ip_ranges)
    except ValueError:
        return False


class IntegrityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal[
        "unknown", "modified_file", "missing_file", "added_file",
        "invalid_manifest", "missing_manifest", "missing_trust_root",
    ]
    component: str = Field(min_length=1, max_length=500, pattern=r"^[A-Za-z0-9_./-]+$")
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class InstallationCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    integrity_ok: bool
    integrity_finding: IntegrityFinding | None = None
    proof_issued_at: int | None = Field(default=None, strict=True, ge=0, le=2**53 - 1)
    proof_signature: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{86}$")

    @model_validator(mode="after")
    def consistent_integrity(self):
        if self.integrity_ok and self.integrity_finding is not None:
            raise ValueError("A successful integrity check cannot report a finding")
        if (self.proof_issued_at is None) != (self.proof_signature is None):
            raise ValueError("Installation proof requires both a timestamp and signature")
        return self


class InstallationEnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrollment_token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    public_key: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    issued_at: int = Field(strict=True, ge=0, le=2**53 - 1)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")


@router.post("/enroll")
async def enroll_client_installation(
    http_request: Request,
    request: InstallationEnrollmentRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Bind a client key after verifying license, one-time secret and key possession."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Installation bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    license_data = None
    for _private_key, owner_public_key in _owner_verification_signers():
        try:
            license_data = load_license(token, owner_public_key)
            break
        except InstallationLicenseError:
            continue
    if license_data is None:
        raise HTTPException(status_code=401, detail="Invalid installation enrollment")
    try:
        verify_enrollment(
            public_key=request.public_key, signature=request.signature,
            installation_id=license_data.installation_id, license_token=token,
            enrollment_token=request.enrollment_token, nonce=request.nonce, issued_at=request.issued_at,
        )
    except InstallationIdentityError as exc:
        raise HTTPException(status_code=401, detail="Invalid installation enrollment") from exc
    if not _license_ip_binding_valid(license_data.ip_ranges, _observed_client_ip(http_request)):
        raise HTTPException(status_code=401, detail="Invalid installation enrollment")
    enrolled = await consume_installation_enrollment(
        license_data.installation_id, hashlib.sha256(token.encode("ascii")).hexdigest(),
        hashlib.sha256(request.enrollment_token.encode("ascii")).hexdigest(), request.public_key,
    )
    if not enrolled:
        raise HTTPException(status_code=401, detail="Invalid installation enrollment")
    return {"enrolled": True}


@router.post("/check")
async def check_client_installation(
    http_request: Request,
    request: InstallationCheckRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Return a short-lived signed status bound to this token and request nonce."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Installation bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    verified = None
    for private_key, public_key in _owner_verification_signers():
        try:
            license_data = load_license(token, public_key)
            verified = (license_data, private_key)
            break
        except InstallationLicenseError:
            continue
    if verified is None:
        raise HTTPException(status_code=401, detail="Invalid installation token")
    license_data, private_key = verified

    observed_ip = _observed_client_ip(http_request)
    binding_valid = _license_ip_binding_valid(license_data.ip_ranges, observed_ip)

    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    identity_args = {}
    if request.proof_signature is not None:
        installation = await get_client_installation_record(license_data.installation_id)
        public_key = installation.get("installation_public_key") if installation else None
        if not public_key:
            raise HTTPException(status_code=401, detail="Invalid installation proof")
        try:
            verify_owner_check(
                public_key, request.proof_signature,
                installation_id=license_data.installation_id, license_token=token,
                nonce=request.nonce, issued_at=request.proof_issued_at,
                integrity_ok=request.integrity_ok,
                integrity_finding=request.integrity_finding.model_dump() if request.integrity_finding else None,
            )
        except InstallationIdentityError as exc:
            raise HTTPException(status_code=401, detail="Invalid installation proof") from exc
        identity_args = {
            "expected_public_key": public_key,
            "nonce_fingerprint": hashlib.sha256(request.nonce.encode("ascii")).hexdigest(),
            "nonce_expires_at": datetime.fromtimestamp(request.proof_issued_at + 91, UTC),
        }
    record = await record_client_installation_check(
        license_data.installation_id, fingerprint, integrity_ok=request.integrity_ok,
        integrity_finding=request.integrity_finding.model_dump() if request.integrity_finding else None,
        observed_ip=observed_ip, **identity_args,
    )
    if record is None:
        raise HTTPException(status_code=401, detail="Installation token not registered")

    now = int(time.time())
    status = {
        "kind": "installation_status",
        "installation_id": license_data.installation_id,
        "license_sha256": fingerprint,
        "nonce": request.nonce,
        "revoked": record["revoked_at"] is not None or record["integrity_failed_at"] is not None,
        "binding_valid": binding_valid,
        "observed_ip": observed_ip,
        "issued_at": now,
        "expires_at": min(now + 300, record["expires_at"]),
    }
    return {"signed_status": issue_license_token(status, private_key)}
