"""Signed client binding requests and owner approval orchestration."""

import hashlib
import os
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException

from api.db.client_installations import (
    create_client_binding_request,
    get_client_binding_request,
    get_client_installation_record,
    resolve_client_binding_request,
    unverified_license_domains,
)
from api.services.installation_identity import (
    InstallationIdentityError, sign_binding_request, verify_binding_request,
)
from api.services.installation_license import (
    InstallationLicenseError, load_license,
)
from api.services.owner_license_signer_client import (
    OwnerLicenseSignerError,
    OwnerLicenseSignerPolicyError,
)
from api.services.owner_trust import OwnerTrustError, trusted_owner_status_url


def _owner_binding_request_url() -> str:
    url = trusted_owner_status_url()
    parsed = urlsplit(url)
    if not parsed.path.endswith("/check"):
        raise OwnerTrustError("Approved owner status URL has an unsupported path")
    return urlunsplit((parsed.scheme, parsed.netloc, f"{parsed.path[:-len('check')]}binding-requests", parsed.query, ""))


async def send_binding_request(request: dict) -> dict:
    token = os.getenv("KODEWAVES_LICENSE_TOKEN", "")
    private_key_path = os.getenv("KODEWAVES_INSTALLATION_KEY_FILE", "")
    try:
        if not token or not private_key_path:
            raise InstallationLicenseError("Installation identity is not configured")
        license_data = load_license(token)
        expected_id = os.getenv("KODEWAVES_INSTALLATION_ID", "").strip()
        if license_data.installation_id != expected_id:
            raise InstallationLicenseError("Installation license identity does not match this server")
        issued_at = int(time.time())
        nonce = secrets.token_urlsafe(32)
        fields = {
            "installation_id": license_data.installation_id,
            "license_token": token,
            "nonce": nonce,
            "issued_at": issued_at,
            "domains": request["domains"],
            "ip_ranges": request["ip_ranges"],
            "reason": request["reason"],
        }
        signature = sign_binding_request(Path(private_key_path).read_bytes(), **fields)
        owner_url = _owner_binding_request_url()
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                owner_url,
                json={
                    "nonce": nonce,
                    "issued_at": issued_at,
                    "signature": signature,
                    "domains": request["domains"],
                    "ip_ranges": request["ip_ranges"],
                    "reason": request["reason"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code == 409:
            raise HTTPException(status_code=409, detail="A binding change request is already awaiting owner review")
        response.raise_for_status()
        result = response.json()
        return {
            "request_id": result["id"],
            "status": result["status"],
            "submitted_at": result["created_at"],
            "message": "Your binding change request was sent to Kodewaves for owner review.",
        }
    except HTTPException:
        raise
    except (InstallationLicenseError, InstallationIdentityError, OwnerTrustError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Kodewaves owner service rejected the binding request") from exc
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="Unable to contact Kodewaves owner service") from exc


async def accept_binding_request(
    request: dict, token: str, verification_keys: Sequence[str],
) -> dict:
    license_data = None
    for owner_public_key in verification_keys:
        try:
            license_data = load_license(token, owner_public_key)
            break
        except InstallationLicenseError:
            continue
    if license_data is None:
        raise HTTPException(status_code=401, detail="Invalid installation token")
    record = await get_client_installation_record(license_data.installation_id)
    public_key = record.get("installation_public_key") if record else None
    if not public_key:
        raise HTTPException(status_code=401, detail="Installation identity is not enrolled")
    try:
        verify_binding_request(
            public_key, request["signature"],
            installation_id=license_data.installation_id,
            license_token=token,
            nonce=request["nonce"],
            issued_at=request["issued_at"],
            domains=request["domains"],
            ip_ranges=request["ip_ranges"],
            reason=request["reason"],
        )
    except InstallationIdentityError as exc:
        raise HTTPException(status_code=401, detail="Invalid installation binding request") from exc
    result = await create_client_binding_request(
        installation_id=license_data.installation_id,
        token_fingerprint=hashlib.sha256(token.encode("ascii")).hexdigest(),
        public_key=public_key,
        nonce_fingerprint=hashlib.sha256(request["nonce"].encode("ascii")).hexdigest(),
        nonce_expires_at=datetime.fromtimestamp(request["issued_at"] + 301, UTC),
        domains=request["domains"],
        ip_ranges=request["ip_ranges"],
        reason=request["reason"],
    )
    if result is None:
        raise HTTPException(status_code=401, detail="Installation is not active or proof was already used")
    if result.pop("conflict", False):
        raise HTTPException(status_code=409, detail="A binding request is already pending for this installation")
    return result


async def approve_binding_request(
    request_id: int,
    user_id: int,
    sign_license: Callable[[dict], Awaitable[tuple[str, str]]],
) -> dict:
    request = await get_client_binding_request(request_id)
    if request is None or request["status"] != "pending":
        raise HTTPException(status_code=404, detail="Pending binding request not found")
    installation_id = request["installation_id"]
    existing = await get_client_installation_record(installation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Installation not found")
    if existing["revoked_at"] or existing["integrity_failed_at"]:
        raise HTTPException(status_code=409, detail="Revoked or integrity-failed installations cannot change bindings")
    if existing.get("previous_token_valid_until") and existing["previous_token_valid_until"] > datetime.now(UTC):
        raise HTTPException(status_code=409, detail="A previous license handover is still active")
    unverified = await unverified_license_domains(existing["customer_id"], request["requested_domains"])
    if unverified:
        raise HTTPException(
            status_code=409,
            detail=f"Verify domain control before approval: {', '.join(unverified)}",
        )
    timestamp = int(time.time())
    if existing["expires_at"] <= timestamp:
        raise HTTPException(status_code=409, detail="Expired installations must be renewed before changing bindings")
    claims = {
        "iat": timestamp,
        "exp": existing["expires_at"],
        "installation_id": installation_id,
        "customer_id": existing["customer_id"],
        "edition": "client",
        "domains": request["requested_domains"],
        "ip_ranges": request["requested_ip_ranges"],
        "features": existing["features"],
        "limits": existing["limits"],
    }
    try:
        token, public_key = await sign_license(claims)
        load_license(token, public_key, now=timestamp)
    except OwnerLicenseSignerPolicyError as exc:
        raise HTTPException(status_code=422, detail="License claims violate owner issuance policy") from exc
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    except (InstallationLicenseError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    accepted = await resolve_client_binding_request(
        request_id,
        outcome="approved",
        user_id=user_id,
        expected_fingerprint=existing["token_fingerprint"],
        new_fingerprint=hashlib.sha256(token.encode("ascii")).hexdigest(),
        domains=request["requested_domains"],
        ip_ranges=request["requested_ip_ranges"],
        license_issued_at=timestamp,
    )
    if not accepted:
        raise HTTPException(status_code=409, detail="Installation or request changed; refresh before approval")
    return {
        "request_id": request_id,
        "installation_id": installation_id,
        "status": "approved",
        "token": token,
        "public_key": public_key,
        "expires_at": existing["expires_at"],
    }


async def recover_approved_binding_token(
    request_id: int,
    sign_license: Callable[[dict], Awaitable[tuple[str, str]]],
) -> dict:
    """Recreate the exact deterministic license token issued by an approved request."""
    request = await get_client_binding_request(request_id)
    if request is None or request["status"] != "approved" or request.get("license_issued_at") is None:
        raise HTTPException(status_code=404, detail="Approved binding request is not recoverable")
    installation = await get_client_installation_record(request["installation_id"])
    if installation is None:
        raise HTTPException(status_code=404, detail="Installation not found")
    if installation["revoked_at"] or installation["integrity_failed_at"]:
        raise HTTPException(status_code=409, detail="Revoked or integrity-failed installations cannot recover a license")
    if installation["expires_at"] <= int(time.time()):
        raise HTTPException(status_code=409, detail="Expired installations must be renewed instead")
    if (
        installation["domains"] != request["requested_domains"]
        or installation["ip_ranges"] != request["requested_ip_ranges"]
    ):
        raise HTTPException(status_code=409, detail="Installation bindings changed after approval; use the current renewal flow")

    claims = {
        "iat": request["license_issued_at"],
        "exp": installation["expires_at"],
        "installation_id": installation["installation_id"],
        "customer_id": installation["customer_id"],
        "edition": "client",
        "domains": request["requested_domains"],
        "ip_ranges": request["requested_ip_ranges"],
        "features": installation["features"],
        "limits": installation["limits"],
    }
    try:
        token, public_key = await sign_license(claims)
        load_license(token, public_key)
    except OwnerLicenseSignerPolicyError as exc:
        raise HTTPException(status_code=409, detail="The approved license cannot be recreated by the current signer policy") from exc
    except OwnerLicenseSignerError as exc:
        raise HTTPException(status_code=503, detail="Owner license signer is unavailable") from exc
    except InstallationLicenseError as exc:
        raise HTTPException(status_code=409, detail="The current owner signing key cannot validate this recovered license") from exc
    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
    if not secrets.compare_digest(fingerprint, installation["token_fingerprint"]):
        raise HTTPException(status_code=409, detail="Signing key or license state changed; use the current renewal flow")
    return {
        "request_id": request_id,
        "installation_id": installation["installation_id"],
        "status": "approved",
        "token": token,
        "public_key": public_key,
        "expires_at": installation["expires_at"],
        "recovered": True,
    }
