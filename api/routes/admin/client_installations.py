"""Owner-only issuance and inventory of client installation licenses."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError

from api.db.client_installations import (
    acknowledge_client_integrity_alert,
    create_client_installation_record,
    get_client_installation_record,
    get_pending_domain_challenge,
    issue_installation_enrollment,
    list_client_binding_requests,
    list_client_installation_records,
    list_client_integrity_alerts,
    mark_domain_verified,
    renew_client_installation_record,
    resolve_client_binding_request,
    revoke_client_installation_record,
    save_domain_challenge,
    unverified_license_domains,
)
from api.db.models import UserModel
from api.services.auth.depends import get_superuser
from api.services.client_binding_requests import (
    approve_binding_request as approve_binding_change,
    recover_approved_binding_token,
)
from api.services.domain_challenge import challenge_record_name, dns_proves_domain
from api.services.installation_license import (
    InstallationLicenseError,
    _canonical_domain,
    load_license,
)
from api.services.owner_license_signer_client import (
    OwnerLicenseSignerError,
    OwnerLicenseSignerPolicyError,
    sign_client_license,
)

router = APIRouter(prefix="/client-installations", tags=["admin-client-installations"])

SUPPORTED_FEATURES = frozenset({
    "voice", "telephony", "campaigns", "crm", "appointments", "forms",
    "widgets", "knowledge_base", "billing",
})
SUPPORTED_LIMITS = frozenset({
    "max_concurrent_calls", "max_seats", "max_workspaces", "max_agents", "max_campaigns",
})


class IssueClientInstallation(BaseModel):
    installation_id: str = Field(min_length=1, max_length=100)
    customer_id: str = Field(min_length=1, max_length=100)
    domains: list[str] = Field(min_length=1)
    ip_ranges: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    limits: dict[str, int] = Field(default_factory=dict)
    expires_at: int

    @field_validator("installation_id", "customer_id")
    @classmethod
    def clean_identity(cls, value: str) -> str:
        value = value.strip()
        if not value or any(character.isspace() for character in value):
            raise ValueError("IDs must be nonempty and contain no spaces")
        return value

    @field_validator("installation_id")
    @classmethod
    def portable_installation_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", value):
            raise ValueError("Installation ID must be 3–100 URL-safe identifier characters")
        return value

    @field_validator("features")
    @classmethod
    def known_features(cls, values: list[str]) -> list[str]:
        unknown = set(values) - SUPPORTED_FEATURES
        if unknown:
            raise ValueError(f"Unknown license features: {', '.join(sorted(unknown))}")
        return sorted(set(values))

    @field_validator("domains")
    @classmethod
    def canonical_domains(cls, values: list[str]) -> list[str]:
        return sorted({_canonical_domain(value) for value in values})

    @field_validator("ip_ranges")
    @classmethod
    def canonical_ip_ranges(cls, values: list[str]) -> list[str]:
        try:
            return sorted({str(ipaddress.ip_network(value.strip(), strict=False)) for value in values})
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Allowed IPs must be valid IP addresses or CIDR ranges") from exc

    @field_validator("limits", mode="before")
    @classmethod
    def integer_limits_only(cls, value):
        if not isinstance(value, dict) or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in value.values()
        ):
            raise ValueError("License limits must be integer values")
        return value

    @model_validator(mode="after")
    def usable_voice_license(self):
        unknown_limits = set(self.limits) - SUPPORTED_LIMITS
        if unknown_limits:
            raise ValueError(f"Unsupported license limits: {', '.join(sorted(unknown_limits))}")
        max_calls = self.limits.get("max_concurrent_calls")
        if "voice" in self.features and (max_calls is None or max_calls <= 0):
            raise ValueError("Voice licenses require a positive max_concurrent_calls limit")
        if any(value < 0 for value in self.limits.values()):
            raise ValueError("License limits cannot be negative")
        if "max_seats" in self.limits and self.limits["max_seats"] < 1:
            raise ValueError("Client administrator provisioning requires at least one seat")
        if "max_workspaces" in self.limits and self.limits["max_workspaces"] < 1:
            raise ValueError("Client administrator provisioning requires at least one workspace")
        if {"telephony", "campaigns", "widgets"}.intersection(self.features) and "voice" not in self.features:
            raise ValueError("Telephony, campaigns and widgets require the voice feature")
        if "campaigns" in self.features and "telephony" not in self.features:
            raise ValueError("Campaigns require the telephony feature")
        return self


class DomainChallengeRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=100)
    domain: str = Field(min_length=1, max_length=253)

    @field_validator("customer_id")
    @classmethod
    def clean_customer_id(cls, value: str) -> str:
        return IssueClientInstallation.clean_identity(value)

    @field_validator("domain")
    @classmethod
    def clean_domain(cls, value: str) -> str:
        return _canonical_domain(value)


class RenewClientInstallation(BaseModel):
    expires_at: int


class InstallationEnrollmentTokenResponse(BaseModel):
    installation_id: str
    enrollment_token: str
    expires_at: int


class RejectBindingRequest(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.get("")
async def list_client_installations(
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> list[dict]:
    return await list_client_installation_records()


@router.get("/alerts")
async def get_client_integrity_alerts(
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> list[dict]:
    return await list_client_integrity_alerts()


@router.get("/binding-requests")
async def get_binding_requests(
    _user: Annotated[UserModel, Depends(get_superuser)],
    include_resolved: bool = False,
) -> list[dict]:
    return await list_client_binding_requests(include_resolved=include_resolved)


@router.post("/binding-requests/{request_id}/reject")
async def reject_binding_request(
    request_id: int,
    _request: RejectBindingRequest,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    if not await resolve_client_binding_request(request_id, outcome="rejected", user_id=user.id):
        raise HTTPException(status_code=404, detail="Pending binding request not found")
    return {"request_id": request_id, "status": "rejected"}


@router.post("/binding-requests/{request_id}/approve")
async def approve_binding_request(
    request_id: int,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Approve only DNS-verified domains and issue the replacement token once."""
    return await approve_binding_change(request_id, user.id, sign_client_license)


@router.post("/binding-requests/{request_id}/recover-token")
async def recover_binding_request_token(
    request_id: int,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Recover the exact token from an approved request without rotating it."""
    return await recover_approved_binding_token(request_id, sign_client_license)


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_integrity_alert(
    alert_id: int,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    if not await acknowledge_client_integrity_alert(alert_id, user.id):
        raise HTTPException(status_code=404, detail="Integrity alert not found")
    return {"acknowledged": True}


@router.post("/domain-challenges", status_code=201)
async def create_domain_challenge(
    request: DomainChallengeRequest,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = await save_domain_challenge(
        request.customer_id, request.domain, hashlib.sha256(token.encode("ascii")).hexdigest()
    )
    return {
        "customer_id": request.customer_id,
        "domain": request.domain,
        "record_name": challenge_record_name(request.domain),
        "record_type": "TXT",
        "record_value": f"kodewaves-verification={token}",
        "expires_at": int(expires_at.timestamp()),
    }


@router.post("/domain-challenges/verify")
async def verify_domain_challenge(
    request: DomainChallengeRequest,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    pending = await get_pending_domain_challenge(request.customer_id, request.domain)
    if pending is None:
        raise HTTPException(status_code=404, detail="No active domain challenge")
    if not await dns_proves_domain(request.domain, pending["token_sha256"]):
        raise HTTPException(status_code=409, detail="Domain TXT challenge was not found")
    verified_at = await mark_domain_verified(
        request.customer_id, request.domain, pending["token_sha256"]
    )
    if verified_at is None:
        raise HTTPException(status_code=409, detail="Domain challenge changed or expired")
    return {"customer_id": request.customer_id, "domain": request.domain, "verified_at": verified_at.isoformat()}


@router.post("", status_code=201)
async def issue_client_installation(
    request: IssueClientInstallation,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Issue once and persist metadata; never store the bearer token or key."""
    timestamp = int(time.time())
    if request.expires_at <= timestamp:
        raise HTTPException(status_code=422, detail="Expiration must be in the future")
    unverified = await unverified_license_domains(request.customer_id, request.domains)
    if unverified:
        raise HTTPException(status_code=409, detail=f"Verify domain control before issuance: {', '.join(unverified)}")
    claims = {
        "iat": timestamp,
        "exp": request.expires_at,
        "installation_id": request.installation_id,
        "customer_id": request.customer_id,
        "edition": "client",
        "domains": request.domains,
        "ip_ranges": request.ip_ranges,
        "features": request.features,
        "limits": request.limits,
    }
    try:
        token, public_key = await sign_client_license(claims)
        license_data = load_license(token, public_key, now=timestamp)
    except OwnerLicenseSignerPolicyError as exc:
        raise HTTPException(status_code=422, detail="License claims violate owner issuance policy") from exc
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    except InstallationLicenseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record_fields = {
        "installation_id": license_data.installation_id,
        "customer_id": license_data.customer_id,
        "domains": list(license_data.domains),
        "ip_ranges": list(license_data.ip_ranges),
        "features": sorted(license_data.features),
        "limits": license_data.limits,
        "expires_at": datetime.fromtimestamp(license_data.expires_at, UTC),
        "token_fingerprint": hashlib.sha256(token.encode("ascii")).hexdigest(),
        "issued_by_user_id": user.id,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    try:
        await create_client_installation_record(**record_fields)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Installation ID already exists") from exc

    return {
        "installation_id": license_data.installation_id,
        "token": token,
        "public_key": public_key,
        "expires_at": license_data.expires_at,
    }


@router.post("/{installation_id}/renew")
async def renew_client_installation(
    installation_id: str,
    request: RenewClientInstallation,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Return a replacement token once; allow a bounded old-token handover."""
    existing = await get_client_installation_record(installation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Installation not found")
    if existing["revoked_at"] or existing["integrity_failed_at"]:
        raise HTTPException(status_code=409, detail="Revoked or integrity-failed installations cannot be renewed")
    if existing.get("previous_token_valid_until") and existing["previous_token_valid_until"] > datetime.now(UTC):
        raise HTTPException(status_code=409, detail="A previous renewal handover is still active")
    timestamp = int(time.time())
    if request.expires_at <= max(timestamp, existing["expires_at"]):
        raise HTTPException(status_code=422, detail="Renewal must extend the current expiration")
    unverified = await unverified_license_domains(existing["customer_id"], existing["domains"])
    if unverified:
        raise HTTPException(status_code=409, detail=f"Verify domain control before renewal: {', '.join(unverified)}")
    claims = {
        "iat": timestamp,
        "exp": request.expires_at,
        "installation_id": installation_id,
        "customer_id": existing["customer_id"],
        "edition": "client",
        "domains": existing["domains"],
        "ip_ranges": existing["ip_ranges"],
        "features": existing["features"],
        "limits": existing["limits"],
    }
    try:
        IssueClientInstallation.model_validate({**claims, "expires_at": request.expires_at})
        token, public_key = await sign_client_license(claims)
        load_license(token, public_key, now=timestamp)
    except OwnerLicenseSignerPolicyError as exc:
        raise HTTPException(status_code=422, detail="License claims violate owner issuance policy") from exc
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    except (InstallationLicenseError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    updated = await renew_client_installation_record(
        installation_id,
        existing["token_fingerprint"],
        hashlib.sha256(token.encode("ascii")).hexdigest(),
        datetime.fromtimestamp(request.expires_at, UTC),
        user.id,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="Installation changed while renewing; refresh and try again")
    return {
        "installation_id": installation_id,
        "token": token,
        "public_key": public_key,
        "expires_at": request.expires_at,
    }


@router.post("/{installation_id}/enrollment-token", response_model=InstallationEnrollmentTokenResponse)
async def create_installation_enrollment_token(
    installation_id: str,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Issue a short-lived one-time enrollment secret to the owner only."""
    token = secrets.token_urlsafe(32)
    expires_at = await issue_installation_enrollment(
        installation_id, hashlib.sha256(token.encode("ascii")).hexdigest()
    )
    if expires_at is None:
        raise HTTPException(status_code=409, detail="Installation cannot be enrolled")
    return {"installation_id": installation_id, "enrollment_token": token, "expires_at": int(expires_at.timestamp())}


@router.post("/{installation_id}/revoke")
async def revoke_client_installation(
    installation_id: str,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Record owner revocation; delivery to an offline installation is separate."""
    record = await revoke_client_installation_record(installation_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Installation not found")
    return record
