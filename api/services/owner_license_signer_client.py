"""Authenticated API client for the isolated owner license signer."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit

import httpx


class OwnerLicenseSignerError(RuntimeError):
    """The isolated owner signer could not safely complete the requested operation."""


class OwnerLicenseSignerPolicyError(OwnerLicenseSignerError):
    """The signer rejected claims that do not satisfy owner issuance policy."""


def _signer_configuration() -> tuple[str, str]:
    base_url = os.getenv("KODEWAVES_OWNER_LICENSE_SIGNER_URL", "").rstrip("/")
    token = os.getenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "")
    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except ValueError as exc:
        raise OwnerLicenseSignerError("Owner license signer is not configured") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "owner-license-signer"
        or port != 8765
        or parsed.path
        or parsed.query
        or parsed.fragment
        or len(token) < 32
    ):
        raise OwnerLicenseSignerError("Owner license signer is not configured")
    return base_url, token


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url, token = _signer_configuration()
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.post(
                f"{base_url}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            raise OwnerLicenseSignerPolicyError("Owner license claims violate signing policy") from exc
        raise OwnerLicenseSignerError("Owner license signer is unavailable") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise OwnerLicenseSignerError("Owner license signer is unavailable") from exc
    if not isinstance(result, dict):
        raise OwnerLicenseSignerError("Owner license signer returned an invalid response")
    return result


async def owner_license_public_keys() -> tuple[str, ...]:
    base_url, token = _signer_configuration()
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(
                f"{base_url}/v1/public-keys",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OwnerLicenseSignerError("Owner license signer is unavailable") from exc
    values = result.get("public_keys") if isinstance(result, dict) else None
    if not isinstance(values, list) or not values or not all(isinstance(key, str) for key in values):
        raise OwnerLicenseSignerError("Owner license signer returned invalid verification keys")
    return tuple(values)


async def sign_client_license(claims: dict[str, Any]) -> tuple[str, str]:
    result = await _post("/v1/sign-license", {"claims": claims})
    token, public_key = result.get("token"), result.get("public_key")
    if not isinstance(token, str) or not isinstance(public_key, str):
        raise OwnerLicenseSignerError("Owner license signer returned an invalid license")
    return token, public_key


async def sign_installation_status(
    claims: dict[str, Any], license_token: str
) -> str:
    result = await _post(
        "/v1/sign-status",
        {"claims": claims, "license_token": license_token},
    )
    signed_status = result.get("signed_status")
    if not isinstance(signed_status, str):
        raise OwnerLicenseSignerError("Owner license signer returned an invalid status")
    return signed_status
