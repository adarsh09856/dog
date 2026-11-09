"""Authenticated owner status check for a deployed client installation."""

from __future__ import annotations

import hashlib
import ipaddress
import time
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.background import BackgroundTask

from api.routes.client_installation_update_report import router as update_report_router
from api.db.client_installations import (
    consume_installation_enrollment,
    get_client_installation_record,
    record_client_installation_check,
)
from api.db.client_releases import pending_update
from api.services.installation_license import (
    InstallationLicenseError,
    load_license,
)
from api.services.client_binding_requests import accept_binding_request
from api.services.installation_binding import license_ip_binding_valid as _license_ip_binding_valid
from api.services.owner_license_signer_client import (
    OwnerLicenseSignerError,
    owner_license_public_keys,
    sign_installation_status,
)
from api.services.installation_identity import (
    InstallationIdentityError,
    verify_enrollment,
    verify_owner_check,
)
from api.services.installation_license import _canonical_domain
from api.services.client_update_protocol import (
    ClientUpdateProtocolError,
    validate_current_version,
)
from api.tasks.client_integrity_email import enqueue_client_integrity_alert_email
from api.services.installation_client_ip import observed_client_ip as _observed_client_ip

router = APIRouter(prefix="/client-installations", tags=["client-installation-check"])
router.include_router(update_report_router)


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
    current_version: str | None = None

    @field_validator("current_version")
    @classmethod
    def canonical_current_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_current_version(value)
        except ClientUpdateProtocolError as exc:
            raise ValueError(str(exc)) from exc

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


class InstallationBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    issued_at: int = Field(strict=True, ge=0, le=2**53 - 1)
    signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")
    domains: list[str] = Field(min_length=1, max_length=20)
    ip_ranges: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def canonical_bindings(self):
        try:
            domains = sorted({_canonical_domain(item) for item in self.domains})
            ip_ranges = sorted({str(ipaddress.ip_network(item.strip(), strict=False)) for item in self.ip_ranges})
        except (InstallationLicenseError, ValueError, AttributeError) as exc:
            raise ValueError("Binding request domains or IP ranges are invalid") from exc
        self.domains = domains
        self.ip_ranges = ip_ranges
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("A reason is required")
        return self


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
    try:
        verification_keys = await owner_license_public_keys()
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    license_data = None
    for owner_public_key in verification_keys:
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
    try:
        verification_keys = await owner_license_public_keys()
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    license_data = None
    for public_key in verification_keys:
        try:
            license_data = load_license(token, public_key)
            break
        except InstallationLicenseError:
            continue
    if license_data is None:
        raise HTTPException(status_code=401, detail="Invalid installation token")

    if request.proof_signature is None:
        raise HTTPException(
            status_code=401,
            detail="Installation identity proof is required; enroll this installation with its owner",
        )

    observed_ip = _observed_client_ip(http_request)
    binding_valid = _license_ip_binding_valid(license_data.ip_ranges, observed_ip)

    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    installation = await get_client_installation_record(license_data.installation_id)
    public_key = installation.get("installation_public_key") if installation else None
    if not public_key:
        raise HTTPException(status_code=401, detail="Installation identity is not enrolled; ask the owner to enroll it")
    try:
        verify_owner_check(
            public_key, request.proof_signature,
            installation_id=license_data.installation_id, license_token=token,
            nonce=request.nonce, issued_at=request.proof_issued_at,
            integrity_ok=request.integrity_ok,
            integrity_finding=request.integrity_finding.model_dump() if request.integrity_finding else None,
            current_version=request.current_version,
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
        # Use the canonical owner-side row returned under the same lock that
        # consumes this one-time check nonce. Renewals therefore reach an
        # installation without replacing its bootstrap license file.
        "entitlement_version": record["entitlement_version"],
        "features": record["features"],
        "feature_version": record["feature_version"],
        "limits": record["limits"],
    }
    if (
        request.current_version is not None
        and record["revoked_at"] is None
        and record["integrity_failed_at"] is None
        and record["expires_at"] > now
        and binding_valid
    ):
        update = await pending_update(license_data.installation_id, request.current_version)
        if update is not None:
            # The owner's installation-status signature covers every update
            # field and the rollout ID; the detached release signature is
            # separately verified by the client using its baked release key.
            status["update"] = update
    try:
        signed_status = await sign_installation_status(status, token)
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    response = {"signed_status": signed_status}
    if record.get("integrity_alert_notification"):
        alert_id = record.get("integrity_alert_notification_id")
        if alert_id is not None:
            return JSONResponse(
                response,
                background=BackgroundTask(
                    enqueue_client_integrity_alert_email,
                    alert_id=alert_id,
                    attempt=1,
                ),
            )
        # The alert row is the durable queue; the periodic sweeper recovers the
        # rare case where RETURNING did not provide its identifier.
        return JSONResponse(response)
    return response


@router.post("/binding-requests", status_code=201)
async def submit_client_binding_request(
    request: InstallationBindingRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Accept a domain/IP request only from the enrolled installation key."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Installation bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        verification_keys = await owner_license_public_keys()
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    return await accept_binding_request(request.model_dump(), token, verification_keys)
