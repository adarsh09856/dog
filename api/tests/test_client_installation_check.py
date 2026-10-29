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
from api.services.installation_identity import sign_enrollment, sign_owner_check
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


def _owner_check_proof(private_key, *, installation_id, token, nonce, integrity_ok=True, finding=None):
    issued_at = int(time.time())
    return issued_at, sign_owner_check(
        private_key,
        installation_id=installation_id,
        license_token=token,
        nonce=nonce,
        issued_at=issued_at,
        integrity_ok=integrity_ok,
        integrity_finding=finding,
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
@pytest.mark.parametrize(
    ("peer", "ip_ranges", "allowed"),
    [
        ("203.0.113.7", ["198.51.100.0/24"], False),
        ("198.51.100.7", ["198.51.100.0/24"], True),
        ("203.0.113.7", [], True),
    ],
)
async def test_owner_applies_optional_ip_policy_before_consuming_enrollment_token(
    monkeypatch, peer, ip_ranges, allowed,
):
    owner_key = Ed25519PrivateKey.generate()
    owner_private = owner_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    owner_public = base64.urlsafe_b64encode(owner_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    client_key = Ed25519PrivateKey.generate()
    client_private = client_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    client_public = base64.urlsafe_b64encode(client_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "ip_ranges": ip_ranges,
        "features": [], "limits": {},
    }, owner_private)
    enrollment_token = "enrollment-token-" + "x" * 32
    nonce = "nonce-" + "y" * 32
    request = client_installation_check.InstallationEnrollmentRequest(
        enrollment_token=enrollment_token,
        public_key=client_public,
        nonce=nonce,
        issued_at=now,
        signature=sign_enrollment(
            client_private,
            installation_id="client-1",
            license_token=token,
            enrollment_token=enrollment_token,
            public_key=client_public,
            nonce=nonce,
            issued_at=now,
        ),
    )
    consume = AsyncMock(return_value=True)
    monkeypatch.setattr(
        client_installation_check,
        "_owner_verification_signers",
        lambda: [(owner_private, owner_public)],
    )
    monkeypatch.setattr(client_installation_check, "consume_installation_enrollment", consume)

    call = client_installation_check.enroll_client_installation(
        _http_request(peer),
        request,
        f"Bearer {token}",
    )
    if allowed:
        assert await call == {"enrolled": True}
        consume.assert_awaited_once()
    else:
        with pytest.raises(HTTPException) as error:
            await call
        assert error.value.status_code == 401
        consume.assert_not_awaited()


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
    installation_key = Ed25519PrivateKey.generate()
    installation_private = installation_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    installation_public = base64.urlsafe_b64encode(installation_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(
        client_installation_check, "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": installation_public}),
    )
    async def status(
        installation_id, fingerprint, *, integrity_ok, integrity_finding,
        observed_ip, expected_public_key, nonce_fingerprint, nonce_expires_at,
    ):
        assert installation_id == "client-1"
        assert fingerprint == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert integrity_ok is True
        assert integrity_finding is None
        assert observed_ip == "203.0.113.7"
        assert expected_public_key == installation_public
        assert nonce_fingerprint == hashlib.sha256(nonce.encode("ascii")).hexdigest()
        assert nonce_expires_at > datetime.now(UTC)
        return {"revoked_at": "2026-01-01T00:00:00Z", "integrity_failed_at": None, "expires_at": now + 3600}
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", status)
    nonce = "abc1234567890abc1234567890abc12345"
    proof_issued_at, proof_signature = _owner_check_proof(
        installation_private, installation_id="client-1", token=token, nonce=nonce,
    )
    response = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=True,
            proof_issued_at=proof_issued_at, proof_signature=proof_signature,
        ),
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
    proof_issued_at, proof_signature = _owner_check_proof(
        installation_private, installation_id="client-1", token=token, nonce=nonce,
    )
    legacy_response = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=True,
            proof_issued_at=proof_issued_at, proof_signature=proof_signature,
        ),
        f"Bearer {token}",
    )
    assert verify_installation_status(
        legacy_response["signed_status"], public_key=public_key,
        installation_id="client-1", license_token=token, nonce=nonce,
    ) is True


@pytest.mark.asyncio
async def test_owner_status_rejects_unsigned_unenrolled_check(monkeypatch):
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(raw, public)])
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": [], "limits": {},
    }, raw)
    with pytest.raises(HTTPException, match="Installation identity proof is required") as unsigned:
        await client_installation_check.check_client_installation(
            _http_request(),
            client_installation_check.InstallationCheckRequest(
                nonce="u" * 43, integrity_ok=True,
            ),
            f"Bearer {token}",
        )
    assert unsigned.value.status_code == 401

    installation_key = Ed25519PrivateKey.generate()
    installation_private = installation_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    installation_public = base64.urlsafe_b64encode(installation_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(
        client_installation_check, "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": None}),
    )
    nonce = "e" * 43
    issued_at, signature = _owner_check_proof(
        installation_private, installation_id="client-1", token=token, nonce=nonce,
    )
    with pytest.raises(HTTPException, match="Installation identity is not enrolled") as unenrolled:
        await client_installation_check.check_client_installation(
            _http_request(),
            client_installation_check.InstallationCheckRequest(
                nonce=nonce, integrity_ok=True,
                proof_issued_at=issued_at, proof_signature=signature,
            ),
            f"Bearer {token}",
        )
    assert unenrolled.value.status_code == 401


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
        expires_at=datetime.now(UTC), installation_public_key="A" * 43,
    )
    async def execute(_statement):
        return SimpleNamespace(scalar_one_or_none=lambda: record, rowcount=1)
    session = SimpleNamespace(execute=AsyncMock(side_effect=execute), commit=AsyncMock())

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(installation_records.kodewaves_db_client, "get_session", lambda: SessionContext())
    now = datetime.now(UTC)
    first = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=False,
        expected_public_key="A" * 43, nonce_fingerprint="1" * 64,
        nonce_expires_at=now + timedelta(seconds=91),
        integrity_finding={
            "reason": "modified_file", "component": "api/app.py",
            "expected_sha256": "a" * 64, "observed_sha256": "b" * 64,
        },
    )
    assert first["integrity_failed_at"] is not None
    second = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=True,
        expected_public_key="A" * 43, nonce_fingerprint="2" * 64,
        nonce_expires_at=now + timedelta(seconds=91),
    )
    assert second["integrity_failed_at"] == first["integrity_failed_at"]
    assert session.commit.await_count == 2
    assert session.execute.await_count == 7  # Two select/delete/nonce groups plus the alert upsert.
    upsert = session.execute.await_args_list[3].args[0]
    assert "ON CONFLICT" in str(upsert.compile(dialect=postgresql.dialect()))
    alert_updates = dict(upsert._post_values_clause.update_values_to_set)
    assert alert_updates["acknowledged_at"] is None
    assert alert_updates["acknowledged_by_user_id"] is None

    record.previous_token_fingerprint = "fingerprint"
    record.previous_token_valid_until = datetime.now(UTC) + timedelta(hours=1)
    record.expires_at = datetime.now(UTC) + timedelta(days=30)
    overlap = await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=True,
        expected_public_key="A" * 43, nonce_fingerprint="3" * 64,
        nonce_expires_at=now + timedelta(seconds=91),
    )
    assert overlap["expires_at"] == int(record.previous_token_valid_until.timestamp())
    assert await installation_records.record_client_installation_check(
        "client-1", "fingerprint", integrity_ok=True,
    ) is None


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
    installation_key = Ed25519PrivateKey.generate()
    installation_private = installation_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    installation_public = base64.urlsafe_b64encode(installation_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(
        client_installation_check, "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": installation_public}),
    )
    stored = AsyncMock(return_value={
        "revoked_at": None, "integrity_failed_at": datetime.now(UTC).isoformat(),
        "expires_at": now + 3600,
    })
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", stored)
    finding = client_installation_check.IntegrityFinding(
        reason="modified_file", component="api/app.py",
        expected_sha256="a" * 64, observed_sha256="b" * 64,
    )
    nonce = "n" * 43
    issued_at, signature = _owner_check_proof(
        installation_private, installation_id="client-1", token=token,
        nonce=nonce, integrity_ok=False, finding=finding.model_dump(),
    )
    result = await client_installation_check.check_client_installation(
        _http_request(),
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=False, integrity_finding=finding,
            proof_issued_at=issued_at, proof_signature=signature,
        ),
        f"Bearer {token}",
    )
    assert stored.await_args.kwargs["integrity_finding"] == finding.model_dump()
    assert verify_installation_status(
        result["signed_status"], public_key=public, installation_id="client-1",
        license_token=token, nonce=nonce,
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
    installation_key = Ed25519PrivateKey.generate()
    installation_private = installation_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    installation_public = base64.urlsafe_b64encode(installation_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(
        client_installation_check, "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": installation_public}),
    )
    stored = AsyncMock(return_value={
        "revoked_at": None, "integrity_failed_at": None, "expires_at": now + 3600,
    })
    monkeypatch.setattr(client_installation_check, "record_client_installation_check", stored)
    nonce = "n" * 43
    issued_at, signature = _owner_check_proof(
        installation_private, installation_id="client-1", token=token, nonce=nonce,
    )
    result = await client_installation_check.check_client_installation(
        _http_request("203.0.113.7"),
        client_installation_check.InstallationCheckRequest(
            nonce=nonce, integrity_ok=True,
            proof_issued_at=issued_at, proof_signature=signature,
        ),
        f"Bearer {token}",
    )
    status = verify_installation_status_claims(
        result["signed_status"], public_key=public, installation_id="client-1",
        license_token=token, nonce=nonce,
    )
    assert status["revoked"] is False
    assert status["binding_valid"] is False
    assert status["observed_ip"] == "203.0.113.7"
    assert stored.await_args.kwargs["observed_ip"] == "203.0.113.7"
