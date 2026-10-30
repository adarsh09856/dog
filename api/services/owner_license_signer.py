"""Private owner-only signer service for hosted client-installation licenses."""

from __future__ import annotations

import base64
import hmac
import ipaddress
import os
import re
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from api.services.installation_license import (
    InstallationLicenseError,
    _b64url_decode,
    _canonical_domain,
    issue_license_token,
    load_license,
    verify_installation_status_claims,
)

app = FastAPI(title="Kodewaves owner license signer", docs_url=None, redoc_url=None, openapi_url=None)

_LICENSE_FIELDS = frozenset({
    "iat", "exp", "installation_id", "customer_id", "edition",
    "domains", "ip_ranges", "features", "limits",
})
_LICENSE_REQUIRED_FIELDS = _LICENSE_FIELDS - {"ip_ranges"}
_LICENSE_FEATURES = frozenset({
    "voice", "telephony", "campaigns", "crm", "appointments", "forms",
    "widgets", "knowledge_base", "billing",
})
_LICENSE_LIMITS = frozenset({
    "max_concurrent_calls", "max_seats", "max_workspaces", "max_agents", "max_campaigns",
})


class SignLicenseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: dict[str, Any]


class SignStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: dict[str, Any]
    license_token: str


def _signer_token() -> str:
    token = os.getenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(status_code=503, detail="Owner license signer is not configured")
    return token


def _authorize(authorization: str | None) -> None:
    expected = f"Bearer {_signer_token()}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Signer authentication required")


def _read_key(path: str) -> tuple[bytes, str]:
    if not path:
        raise HTTPException(status_code=503, detail="Owner license signer key is not configured")
    try:
        raw = Path(path).read_bytes()
        seed = raw if len(raw) == 32 else _b64url_decode(raw.strip().decode("ascii"))
        key = Ed25519PrivateKey.from_private_bytes(seed)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise HTTPException(status_code=503, detail="Owner license signer key is unavailable") from exc
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return seed, base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")


def _private_signers() -> list[tuple[bytes, str]]:
    """Load the current signer first, then transitional legacy signers."""
    current = _read_key(os.getenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", ""))
    signers = [current]
    legacy_paths = os.getenv("KODEWAVES_OWNER_LEGACY_LICENSE_SIGNING_KEY_FILES", "")
    for path in legacy_paths.split(os.pathsep):
        if path.strip():
            candidate = _read_key(path.strip())
            if candidate[1] not in {public for _private, public in signers}:
                signers.append(candidate)
    return signers


def _validate_license_claim_policy(claims: dict[str, Any]) -> None:
    """Apply the owner API's issuance policy again at the key boundary."""
    if (
        not _LICENSE_REQUIRED_FIELDS.issubset(claims)
        or set(claims) - _LICENSE_FIELDS
        or claims.get("edition") != "client"
        or not isinstance(claims.get("iat"), int)
        or isinstance(claims.get("iat"), bool)
        or not isinstance(claims.get("exp"), int)
        or isinstance(claims.get("exp"), bool)
        or claims["exp"] <= claims["iat"]
    ):
        raise HTTPException(status_code=422, detail="License claims violate owner issuance policy")
    installation_id = claims.get("installation_id")
    customer_id = claims.get("customer_id")
    if (
        not isinstance(installation_id, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", installation_id)
        or not isinstance(customer_id, str)
        or not customer_id.strip()
        or any(character.isspace() for character in customer_id)
    ):
        raise HTTPException(status_code=422, detail="License claims violate owner issuance policy")
    domains = claims.get("domains")
    if not isinstance(domains, list) or not domains:
        raise HTTPException(status_code=422, detail="License claims require domains")
    try:
        if (
            any(not isinstance(domain, str) or _canonical_domain(domain) != domain for domain in domains)
            or len(set(domains)) != len(domains)
        ):
            raise ValueError("non-canonical domain")
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="License claims contain an invalid domain") from exc
    ip_ranges = claims.get("ip_ranges", [])
    if not isinstance(ip_ranges, list):
        raise HTTPException(status_code=422, detail="License IP ranges are invalid")
    try:
        for network in ip_ranges:
            if not isinstance(network, str) or str(ipaddress.ip_network(network, strict=False)) != network:
                raise ValueError("non-canonical IP range")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="License IP ranges are invalid") from exc
    features = claims.get("features")
    limits = claims.get("limits")
    if (
        not isinstance(features, list)
        or any(not isinstance(feature, str) for feature in features)
        or set(features) - _LICENSE_FEATURES
        or not isinstance(limits, dict)
        or set(limits) - _LICENSE_LIMITS
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in limits.values())
        or ("voice" in features and limits.get("max_concurrent_calls", 0) < 1)
        or ("max_seats" in limits and limits["max_seats"] < 1)
        or ("max_workspaces" in limits and limits["max_workspaces"] < 1)
        or ({"telephony", "campaigns", "widgets"}.intersection(features) and "voice" not in features)
        or ("campaigns" in features and "telephony" not in features)
    ):
        raise HTTPException(status_code=422, detail="License claims violate owner entitlement policy")


@app.get("/health")
async def health() -> dict[str, str]:
    _signer_token()
    _private_signers()
    return {"status": "ok"}


@app.get("/v1/public-keys")
async def public_keys(authorization: str | None = Header(default=None)) -> dict[str, list[str]]:
    _authorize(authorization)
    return {"public_keys": [public for _private, public in _private_signers()]}


@app.post("/v1/sign-license")
async def sign_license(
    request: SignLicenseRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(authorization)
    _validate_license_claim_policy(request.claims)
    private, public = _private_signers()[0]
    token = issue_license_token(request.claims, private)
    try:
        load_license(token, public)
    except InstallationLicenseError as exc:
        raise HTTPException(status_code=422, detail="License claims are invalid") from exc
    return {"token": token, "public_key": public}


@app.post("/v1/sign-status")
async def sign_status(
    request: SignStatusRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _authorize(authorization)
    signers = _private_signers()
    verified = None
    for private, public in signers:
        try:
            verified = (load_license(request.license_token, public), private, public)
            break
        except InstallationLicenseError:
            continue
    if verified is None:
        raise HTTPException(status_code=422, detail="Installation status claims are invalid")
    license_data, private, public = verified
    try:
        token = issue_license_token(request.claims, private)
        verify_installation_status_claims(
            token,
            public_key=public,
            installation_id=license_data.installation_id,
            license_token=request.license_token,
            nonce=request.claims.get("nonce", ""),
        )
    except InstallationLicenseError as exc:
        raise HTTPException(status_code=422, detail="Installation status claims are invalid") from exc
    return {"signed_status": token}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8765, access_log=False)
