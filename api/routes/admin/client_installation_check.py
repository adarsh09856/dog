"""Authenticated owner status check for a deployed client installation."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import time
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.db.client_installations import record_client_installation_check
from api.routes.admin.client_installations import _owner_verification_signers
from api.services.installation_license import (
    InstallationLicenseError,
    issue_license_token,
    load_license,
)

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

    @model_validator(mode="after")
    def consistent_integrity(self):
        if self.integrity_ok and self.integrity_finding is not None:
            raise ValueError("A successful integrity check cannot report a finding")
        return self


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
    binding_valid = True
    if license_data.ip_ranges:
        try:
            address = ipaddress.ip_address(observed_ip or "")
            binding_valid = any(address in ipaddress.ip_network(value) for value in license_data.ip_ranges)
        except ValueError:
            binding_valid = False

    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    record = await record_client_installation_check(
        license_data.installation_id, fingerprint, integrity_ok=request.integrity_ok,
        integrity_finding=request.integrity_finding.model_dump() if request.integrity_finding else None,
        observed_ip=observed_ip,
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
