"""Signed client-installation update reports accepted by the owner API."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.db.client_installations import get_client_installation_record
from api.db.client_releases import report_update_status
from api.services.client_update_protocol import (
    ClientUpdateProtocolError,
    validate_current_version,
    verify_update_report,
)
from api.services.installation_binding import license_ip_binding_valid
from api.services.installation_client_ip import observed_client_ip
from api.services.installation_license import InstallationLicenseError, load_license
from api.services.owner_license_signer_client import OwnerLicenseSignerError, owner_license_public_keys

router = APIRouter(tags=["client-installation-updates"])


class InstallationUpdateReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rollout_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    release_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,99}$")
    version: str
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    issued_at: int = Field(strict=True, ge=0, le=2**53 - 1)
    status: Literal["staged", "downloading", "applying", "applied", "failed", "rolled_back"]
    detail: str = Field(default="", max_length=1000)
    installed_version: str | None = None
    proof_signature: str = Field(pattern=r"^[A-Za-z0-9_-]{86}$")

    @field_validator("version")
    @classmethod
    def canonical_version(cls, value: str) -> str:
        try:
            return validate_current_version(value)
        except ClientUpdateProtocolError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("installed_version")
    @classmethod
    def canonical_installed_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_current_version(value)
        except ClientUpdateProtocolError as exc:
            raise ValueError(str(exc)) from exc


@router.post("/update-status")
async def report_client_update_status(
    http_request: Request,
    request: InstallationUpdateReportRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Accept fresh reports signed by the enrolled installation key.

    This is a client data-plane endpoint, not an owner browser control. Its
    installation bearer and enrolled-key proof provide its authorization.
    """
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
    observed_ip = observed_client_ip(http_request)
    if not license_ip_binding_valid(license_data.ip_ranges, observed_ip):
        raise HTTPException(status_code=401, detail="Installation binding check failed")
    record = await get_client_installation_record(license_data.installation_id)
    public_key = record.get("installation_public_key") if record else None
    if not public_key:
        raise HTTPException(status_code=401, detail="Installation identity is not enrolled")
    try:
        verify_update_report(
            public_key, request.proof_signature,
            installation_id=license_data.installation_id,
            license_token=token,
            rollout_id=request.rollout_id,
            release_id=request.release_id,
            version=request.version,
            nonce=request.nonce,
            issued_at=request.issued_at,
            status=request.status,
            detail=request.detail,
            installed_version=request.installed_version,
        )
    except ClientUpdateProtocolError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired installation update proof") from exc
    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    result = await report_update_status(
        installation_id=license_data.installation_id,
        license_fingerprint=fingerprint,
        public_key=public_key,
        rollout_id=request.rollout_id,
        release_id=request.release_id,
        version=request.version,
        nonce_fingerprint=hashlib.sha256(request.nonce.encode("ascii")).hexdigest(),
        nonce_expires_at=datetime.fromtimestamp(request.issued_at + 91, UTC),
        status=request.status,
        detail=request.detail.strip(),
        installed_version=request.installed_version,
    )
    if result is None:
        raise HTTPException(status_code=409, detail="Update report is stale, replayed, or not valid for this rollout")
    return result
