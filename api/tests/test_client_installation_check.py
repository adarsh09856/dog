import base64
import hashlib
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from api.db import client_installations as installation_records
from api.routes.admin import client_installation_check
from api.services.installation_license import (
    InstallationLicenseError,
    issue_license_token,
    verify_installation_status,
    verify_installation_status_claims,
)


def _http_request(peer="203.0.113.7", forwarded=""):
    return SimpleNamespace(
        client=SimpleNamespace(host=peer),
        headers={"x-forwarded-for": forwarded} if forwarded else {},
    )


def test_owner_ip_ignores_untrusted_forwarded_header_and_honors_trusted_proxy(monkeypatch):
    monkeypatch.delenv("KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS", raising=False)
    spoofed = client_installation_check._observed_client_ip(
        _http_request("198.51.100.9", "203.0.113.44")
    )
    assert spoofed == "198.51.100.9"
    monkeypatch.setenv("KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS", "198.51.100.0/24")
    proxied = client_installation_check._observed_client_ip(
        _http_request("198.51.100.9", "203.0.113.44, 198.51.100.12")
    )
    assert proxied == "203.0.113.44"


@pytest.mark.asyncio
async def test_owner_status_is_signed_and_bound_to_token_and_nonce(monkeypatch):
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = base64.urlsafe_b64encode(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(raw, public_key)])
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 2, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": [], "limits": {},
    }, raw)
    async def status(installation_id, fingerprint, *, integrity_ok, integrity_finding, observed_ip):
        assert installation_id == "client-1"
        assert fingerprint == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert integrity_ok is True
        assert integrity_finding is None
        assert observed_ip == "203.0.113.7"
        return {"revoked_at": "2026-01-01T00:00:00Z", "integrity_failed_at": None, "expires_at": now + 3600}
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", status)
    nonce = "abc1234567890abc1234567890abc12345"
    response = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(nonce=nonce, integrity_ok=True),
        f"Bearer {token}",
    )
    assert verify_installation_status(
        response["signed_status"], public_key=public_key,
        installation_id="client-1", license_token=token, nonce=nonce,
    ) is True
    with pytest.raises(InstallationLicenseError):
        verify_installation_status(
            response["signed_status"], public_key=public_key,
            installation_id="client-1", license_token=token, nonce="different-nonce",
        )
    with pytest.raises(InstallationLicenseError):
        verify_installation_status(
            response["signed_status"], public_key=public_key,
            installation_id="client-1", license_token="another-token", nonce=nonce,
        )
    with pytest.raises(InstallationLicenseError):
        verify_installation_status(
            response["signed_status"], public_key=public_key,
            installation_id="client-1", license_token=token, nonce=nonce,
            now=now + 301,
        )

    new_key = Ed25519PrivateKey.generate()
    new_raw = new_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    new_public = base64.urlsafe_b64encode(new_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(
        client_installation_check, "_owner_verification_signers",
        lambda: [(new_raw, new_public), (raw, public_key)],
    )
    legacy_response = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(nonce=nonce, integrity_ok=True),
        f"Bearer {token}",
    )
    assert verify_installation_status(
        legacy_response["signed_status"], public_key=public_key,
        installation_id="client-1", license_token=token, nonce=nonce,
    ) is True


@pytest.mark.asyncio
async def test_owner_status_rejects_missing_bearer():
    with pytest.raises(HTTPException) as error:
        await client_installation_check.check_client_installation(
            _http_request(),
            client_installation_check.InstallationCheckRequest(
                nonce="abc1234567890abc1234567890abc12345", integrity_ok=True
            ), None,
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_owner_records_integrity_alert_and_does_not_clear_it(monkeypatch):
    record = SimpleNamespace(
        installation_id="client-1", revoked_at=None, integrity_failed_at=None,
        last_seen_at=None, updated_at=None,
        expires_at=datetime.now(UTC),
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(installation_records.kodewaves_db_client, "get_session", lambda: SessionContext())
    first = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=False,
        integrity_finding={
            "reason": "modified_file", "component": "api/app.py",
            "expected_sha256": "a" * 64, "observed_sha256": "b" * 64,
        },
    )
    assert first["integrity_failed_at"] is not None
    second = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=True
    )
    assert second["integrity_failed_at"] == first["integrity_failed_at"]
    assert session.commit.await_count == 2
    assert session.execute.await_count == 3  # Select, alert upsert, then select.
    upsert = session.execute.await_args_list[1].args[0]
    assert "ON CONFLICT" in str(upsert.compile(dialect=postgresql.dialect()))

    record.previous_token_fingerprint = "fingerprint"
    record.previous_token_valid_until = datetime.now(UTC) + timedelta(hours=1)
    record.expires_at = datetime.now(UTC) + timedelta(days=30)
    overlap = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=True
    )
    assert overlap["expires_at"] == int(record.previous_token_valid_until.timestamp())


def test_owner_rejects_inconsistent_or_unsafe_integrity_reports():
    nonce = "a" * 43
    with pytest.raises(ValidationError):
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=True,
            integrity_finding={"reason": "modified_file", "component": "api/app.py"},
        )
    with pytest.raises(ValidationError):
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=False,
            integrity_finding={"reason": "modified_file", "component": "../../secret key", "observed_sha256": "not-a-hash"},
        )
    with pytest.raises(ValidationError):
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=False,
            integrity_finding={"reason": "unknown", "component": "release", "call_content": "private audio"},
        )


@pytest.mark.asyncio
async def test_owner_records_bounded_component_finding(monkeypatch):
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(raw, public)])
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": [], "limits": {},
    }, raw)
    stored = AsyncMock(return_value={
        "revoked_at": None, "integrity_failed_at": datetime.now(UTC).isoformat(),
        "expires_at": now + 3600,
    })
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", stored)
    finding = client_installation_check.IntegrityFinding(
        reason="modified_file", component="api/app.py",
        expected_sha256="a" * 64, observed_sha256="b" * 64,
    )
    result = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(
            nonce="n" * 43, integrity_ok=False, integrity_finding=finding,
        ),
        f"Bearer {token}",
    )
    assert stored.await_args.kwargs["integrity_finding"] == finding.model_dump()
    assert verify_installation_status(
        result["signed_status"], public_key=public, installation_id="client-1",
        license_token=token, nonce="n" * 43,
    ) is True


@pytest.mark.asyncio
async def test_owner_signs_ip_binding_failure_without_revoking_license(monkeypatch):
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(raw, public)])
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "ip_ranges": ["192.0.2.0/24"],
        "features": [], "limits": {},
    }, raw)
    stored = AsyncMock(return_value={
        "revoked_at": None, "integrity_failed_at": None, "expires_at": now + 3600,
    })
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", stored)
    result = await client_installation_check.check_client_installation(
        _http_request("203.0.113.7"),
        client_installation_check.InstallationCheckRequest(nonce="n" * 43, integrity_ok=True),
        f"Bearer {token}",
    )
    status = verify_installation_status_claims(
        result["signed_status"], public_key=public, installation_id="client-1",
        license_token=token, nonce="n" * 43,
    )
    assert status["revoked"] is False
    assert status["binding_valid"] is False
    assert status["observed_ip"] == "203.0.113.7"
    assert stored.await_args.kwargs["observed_ip"] == "203.0.113.7"
