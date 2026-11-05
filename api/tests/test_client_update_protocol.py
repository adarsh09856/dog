"""Focused tests for signed client release and rollout contracts."""

import base64
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI

from api.routes.admin import client_installations as admin_client_installations
from api.routes.admin import client_release_control
from api.services import client_update_protocol as protocol
from api.services.auth import depends as auth_depends


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _release_envelope(monkeypatch) -> tuple[dict[str, str], Ed25519PrivateKey]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setattr(protocol, "trusted_release_public_key", lambda: _b64url(public))
    payload = protocol.release_signature_payload(
        release_id="release-2.1.0",
        version="2.1.0",
        archive_url="https://updates.example.com/client-2.1.0.tar.zst",
        archive_sha256="a" * 64,
        min_current_version="2.0.0",
        notes="  Security and reliability fixes  ",
    )
    envelope = {
        **payload,
        "archive_signature": _b64url(private.sign(protocol.canonical_json(payload))),
    }
    return envelope, private


def test_release_signature_covers_normalized_metadata(monkeypatch):
    envelope, _ = _release_envelope(monkeypatch)
    verified = protocol.verify_release_envelope(envelope)
    assert verified["notes"] == "Security and reliability fixes"
    assert protocol.release_update_is_eligible("2.0.0", verified)
    assert not protocol.release_update_is_eligible("2.1.0", verified)
    assert not protocol.release_update_is_eligible("1.9.9", verified)


def test_owner_signed_status_covers_update_envelope_and_verifies_detached_signature(monkeypatch):
    from api.services.installation_license import issue_license_token, verify_installation_status_claims

    envelope, _ = _release_envelope(monkeypatch)
    release = protocol.verify_release_envelope(envelope)
    owner_license_key = Ed25519PrivateKey.generate()
    public = _b64url(owner_license_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ))
    now = 1_800_000_000
    owner_private_bytes = owner_license_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    license_token = issue_license_token({
        "installation_id": "client-123",
        "customer_id": "customer-123",
        "edition": "client",
        "domains": ["client.example.com"],
        "iat": now - 10,
        "exp": now + 3600,
        "features": ["voice"],
        "limits": {},
    }, owner_private_bytes)
    status = {
        "kind": "installation_status",
        "installation_id": "client-123",
        "license_sha256": hashlib.sha256(license_token.encode("ascii")).hexdigest(),
        "nonce": "b" * 43,
        "revoked": False,
        "binding_valid": True,
        "issued_at": now,
        "expires_at": now + 300,
        "update": {
            **release,
            "rollout_id": "12345678-1234-4234-8234-123456789abc",
            "target_status": "applying",
            "rollout_state": "active",
        },
    }
    signed_status = issue_license_token(status, owner_private_bytes)
    claims = verify_installation_status_claims(
        signed_status,
        public_key=public,
        installation_id="client-123",
        license_token=license_token,
        nonce="b" * 43,
        now=now + 1,
    )
    assert claims["update"]["version"] == "2.1.0"
    assert claims["update"]["rollout_state"] == "active"
    invalid_status = {**status, "update": {**status["update"], "archive_sha256": "b" * 64}}
    from api.services.installation_license import InstallationLicenseError

    with pytest.raises(InstallationLicenseError):
        verify_installation_status_claims(
            issue_license_token(invalid_status, owner_private_bytes),
            public_key=public,
            installation_id="client-123",
            license_token=license_token,
            nonce="b" * 43,
            now=now + 1,
        )


@pytest.mark.parametrize(("rollout_state", "target_status"), [
    ("paused", "staged"),
    ("stopped", "downloading"),
    ("completed", "applying"),
    ("unknown", "applying"),
])
def test_owner_signed_update_status_rejects_inconsistent_rollout_state(
    monkeypatch, rollout_state, target_status,
):
    from api.services.installation_license import (
        InstallationLicenseError,
        issue_license_token,
        verify_installation_status_claims,
    )

    envelope, _ = _release_envelope(monkeypatch)
    owner = Ed25519PrivateKey.generate()
    owner_private = owner.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    owner_public = _b64url(owner.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ))
    now = 1_800_000_000
    token = issue_license_token({
        "installation_id": "client-123", "customer_id": "customer-123",
        "edition": "client", "domains": ["client.example.com"],
        "iat": now - 10, "exp": now + 3600, "features": ["voice"], "limits": {},
    }, owner_private)
    status = {
        "kind": "installation_status", "installation_id": "client-123",
        "license_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
        "nonce": "b" * 43, "revoked": False, "binding_valid": True,
        "issued_at": now, "expires_at": now + 300,
        "update": {
            **envelope,
            "rollout_id": "12345678-1234-4234-8234-123456789abc",
            "target_status": target_status, "rollout_state": rollout_state,
        },
    }

    with pytest.raises(InstallationLicenseError):
        verify_installation_status_claims(
            issue_license_token(status, owner_private), public_key=owner_public,
            installation_id="client-123", license_token=token, nonce="b" * 43,
            now=now + 1,
        )


@pytest.mark.parametrize("url", [
    "http://updates.example.com/client.tgz",
    "https://user:password@updates.example.com/client.tgz",
    "https://127.0.0.1/client.tgz",
    "https://updates.local/client.tgz",
    "https://updates.example.com:8443/client.tgz",
    "https://updates.example.com/client.tgz#fragment",
])
def test_release_rejects_unsafe_archive_urls(monkeypatch, url):
    envelope, _ = _release_envelope(monkeypatch)
    envelope["archive_url"] = url
    with pytest.raises(protocol.ClientUpdateProtocolError):
        protocol.verify_release_envelope(envelope)


def test_update_report_is_installation_signed_fresh_and_bound_to_all_fields():
    private = Ed25519PrivateKey.generate()
    public = _b64url(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ))
    fields = {
        "installation_id": "client-123",
        "license_token": "signed-license-token",
        "rollout_id": "12345678-1234-4234-8234-123456789abc",
        "release_id": "release-2.1.0",
        "version": "2.1.0",
        "nonce": "a" * 43,
        "issued_at": 1_800_000_000,
        "status": "applied",
        "detail": "health check passed",
    }
    signature = _b64url(private.sign(protocol.update_report_message(**fields)))
    protocol.verify_update_report(public, signature, now=1_800_000_010, **fields)
    with pytest.raises(protocol.ClientUpdateProtocolError):
        protocol.verify_update_report(public, signature, now=1_800_000_010, **{**fields, "status": "failed"})
    with pytest.raises(protocol.ClientUpdateProtocolError):
        protocol.verify_update_report(public, signature, now=1_800_000_400, **fields)


def test_rollback_installed_version_is_signed_and_legacy_reports_stay_compatible():
    fields = {
        "installation_id": "client-123",
        "license_token": "signed-license-token",
        "rollout_id": "12345678-1234-4234-8234-123456789abc",
        "release_id": "release-2.1.0",
        "version": "2.1.0",
        "nonce": "a" * 43,
        "issued_at": 1_800_000_000,
        "status": "rolled_back",
        "detail": "restored previous release",
    }
    legacy = protocol.update_report_message(**fields)
    signed_rollback = protocol.update_report_message(**fields, installed_version="2.0.0")
    assert legacy != signed_rollback
    assert b'"installed_version":"2.0.0"' in signed_rollback
    with pytest.raises(protocol.ClientUpdateProtocolError):
        protocol.update_report_message(**fields, installed_version="v2.0.0")


def test_completed_rollout_allows_last_rollback_only_before_newer_rollout():
    allowed = protocol.update_report_transition_allowed(
        rollout_state="completed", current_status="applied",
        requested_status="rolled_back", has_newer_rollout=False,
    )
    assert allowed
    assert not protocol.update_report_transition_allowed(
        rollout_state="completed", current_status="applied",
        requested_status="rolled_back", has_newer_rollout=True,
    )
    assert not protocol.update_report_transition_allowed(
        rollout_state="completed", current_status="rolled_back",
        requested_status="applied", has_newer_rollout=False,
    )


@pytest.mark.parametrize("rollout_state", ["paused", "stopped"])
@pytest.mark.parametrize("final_status", ["applied", "failed", "rolled_back"])
def test_paused_or_stopped_rollout_accepts_final_report_from_inflight_target(rollout_state, final_status):
    assert protocol.update_report_transition_allowed(
        rollout_state=rollout_state,
        current_status="applying",
        requested_status=final_status,
        has_newer_rollout=True,
    )
    assert not protocol.update_report_transition_allowed(
        rollout_state=rollout_state,
        current_status="downloading",
        requested_status=final_status,
        has_newer_rollout=False,
    )
    assert not protocol.update_report_transition_allowed(
        rollout_state=rollout_state,
        current_status="applying",
        requested_status="downloading",
        has_newer_rollout=False,
    )


def test_owner_check_current_version_is_optional_but_signed_when_present():
    from api.services.installation_identity import owner_check_message

    base = {
        "installation_id": "client-123",
        "license_token": "signed-license-token",
        "nonce": "a" * 43,
        "issued_at": 1_800_000_000,
        "integrity_ok": True,
        "integrity_finding": None,
    }
    legacy = owner_check_message(**base)
    with_version = owner_check_message(**base, current_version="2.0.0")
    assert legacy != with_version
    assert b'"current_version":"2.0.0"' in with_version
    from api.services.installation_identity import InstallationIdentityError

    with pytest.raises(InstallationIdentityError):
        owner_check_message(**base, current_version="v2.0.0")


@pytest.mark.asyncio
async def test_release_admin_routes_require_superuser_and_reject_api_keys(monkeypatch):
    app = FastAPI()
    app.include_router(admin_client_installations.router, prefix="/admin")
    monkeypatch.setattr(client_release_control, "list_releases", _empty_releases)
    monkeypatch.setattr(auth_depends, "get_user", _auth_user(False))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        forbidden = await client.get("/admin/client-installations/releases")
        assert forbidden.status_code == 403
        api_key_denied = await client.get(
            "/admin/client-installations/releases", headers={"X-API-Key": "org-key"}
        )
        assert api_key_denied.status_code == 403
        monkeypatch.setattr(auth_depends, "get_user", _auth_user(True))
        allowed = await client.get("/admin/client-installations/releases")
        assert allowed.status_code == 200
        assert allowed.json() == []


async def _empty_releases():
    return []


def _auth_user(is_superuser: bool):
    async def get_user(*_args, **_kwargs):
        return SimpleNamespace(id=7, is_superuser=is_superuser, is_active=True)

    return get_user
