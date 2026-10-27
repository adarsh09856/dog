"""Exercise owner checks with SQLAlchemy's real expire-on-commit behavior."""

import base64
import hashlib
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import client_installations
from api.db.kodewaves_models import ClientInstallationModel, ClientInstallationNonceModel
from api.routes.admin import client_installation_check, client_installations as owner_routes
from api.services.installation_identity import sign_enrollment, sign_owner_check
from api.services.installation_license import issue_license_token, verify_installation_status

@pytest_asyncio.fixture
async def owner_database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: ClientInstallationModel.__table__.create(sync))
        await connection.run_sync(lambda sync: ClientInstallationNonceModel.__table__.create(sync))
    sessions = async_sessionmaker(engine)  # Mirrors the production default: expire_on_commit=True.
    monkeypatch.setattr(client_installations.kodewaves_db_client, "get_session", sessions)
    async with sessions() as session:
        session.add(ClientInstallationModel(
            installation_id="client-test", customer_id="customer-test",
            domains=["customer.example"], ip_ranges=[], features=[], limits={},
            expires_at=datetime.now(UTC) + timedelta(days=1),
            token_fingerprint="a" * 64, issued_by_user_id=1,
        ))
        await session.commit()
    yield sessions
    await engine.dispose()


@pytest.mark.asyncio
async def test_owner_heartbeat_returns_status_after_real_session_commit(owner_database):
    result = await client_installations.record_client_installation_check(
        "client-test", "a" * 64, integrity_ok=True, observed_ip="203.0.113.7",
    )
    assert result["installation_id"] == "client-test"
    assert result["revoked_at"] is None
    assert result["expires_at"] > 0
    async with owner_database() as session:
        stored = await session.get(ClientInstallationModel, "client-test")
        assert stored.observed_ip == "203.0.113.7"
        assert stored.last_seen_at is not None


@pytest.mark.asyncio
async def test_owner_revocation_returns_status_and_is_idempotent_after_commit(owner_database):
    first = await client_installations.revoke_client_installation_record("client-test", 1)
    second = await client_installations.revoke_client_installation_record("client-test", 2)
    assert first["installation_id"] == second["installation_id"]
    # SQLite does not preserve timezone offsets; PostgreSQL does.
    assert datetime.fromisoformat(first["revoked_at"]).replace(tzinfo=None) == (
        datetime.fromisoformat(second["revoked_at"]).replace(tzinfo=None)
    )
    assert first["revoked_at"]
    async with owner_database() as session:
        stored = await session.get(ClientInstallationModel, "client-test")
        assert stored.revoked_by_user_id == 1


@pytest.mark.asyncio
async def test_signed_owner_check_and_revocation_use_committed_database_state(owner_database, monkeypatch):
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-test", "customer_id": "customer-test",
        "domains": ["customer.example"], "features": [], "limits": {},
    }, private)
    async with owner_database() as session:
        record = await session.get(ClientInstallationModel, "client-test")
        record.token_fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        await session.commit()
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(private, public)])
    request = client_installation_check.InstallationCheckRequest(nonce="n" * 43, integrity_ok=True)
    http_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"), headers={})

    async def check():
        response = await client_installation_check.check_client_installation(
            http_request, request, f"Bearer {token}"
        )
        return verify_installation_status(
            response["signed_status"], public_key=public, installation_id="client-test",
            license_token=token, nonce=request.nonce,
        )

    assert await check() is False
    await client_installations.revoke_client_installation_record("client-test", 1)
    assert await check() is True


@pytest.mark.asyncio
async def test_enrollment_token_binds_one_public_key_once(owner_database):
    expiry = await client_installations.issue_installation_enrollment("client-test", "b" * 64)
    assert datetime.now(UTC) < expiry <= datetime.now(UTC) + timedelta(minutes=15)
    listed = (await client_installations.list_client_installation_records())[0]
    assert listed["identity_enrolled"] is False
    assert listed["enrollment_expires_at"] is not None
    assert "enrollment_token_fingerprint" not in listed
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "c" * 64, "A" * 43
    )
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "d" * 64, "b" * 64, "A" * 43
    )
    assert await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "b" * 64, "A" * 43
    )
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "b" * 64, "B" * 43
    )
    assert await client_installations.issue_installation_enrollment("client-test", "d" * 64) is None
    assert (await client_installations.list_client_installation_records())[0]["identity_enrolled"] is True
    async with owner_database() as session:
        stored = await session.get(ClientInstallationModel, "client-test")
        assert stored.installation_public_key == "A" * 43
        assert stored.enrollment_token_fingerprint is None
        assert stored.enrollment_expires_at is None
        assert stored.enrolled_at is not None


@pytest.mark.asyncio
async def test_enrollment_reissue_invalidates_previous_token_and_expired_token_is_rejected(owner_database):
    assert await client_installations.issue_installation_enrollment("client-test", "b" * 64)
    assert await client_installations.issue_installation_enrollment("client-test", "c" * 64)
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "b" * 64, "A" * 43
    )
    async with owner_database() as session:
        stored = await session.get(ClientInstallationModel, "client-test")
        stored.enrollment_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "c" * 64, "A" * 43
    )


@pytest.mark.asyncio
async def test_revoked_installation_cannot_receive_or_consume_enrollment(owner_database):
    assert await client_installations.issue_installation_enrollment("client-test", "b" * 64)
    await client_installations.revoke_client_installation_record("client-test", 1)
    assert await client_installations.issue_installation_enrollment("client-test", "c" * 64) is None
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "b" * 64, "A" * 43
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["expired", "integrity_failed"])
async def test_expired_or_integrity_failed_installations_cannot_enroll(owner_database, condition):
    assert await client_installations.issue_installation_enrollment("client-test", "b" * 64)
    async with owner_database() as session:
        stored = await session.get(ClientInstallationModel, "client-test")
        if condition == "expired":
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            stored.integrity_failed_at = datetime.now(UTC)
        await session.commit()
    assert await client_installations.issue_installation_enrollment("client-test", "c" * 64) is None
    assert not await client_installations.consume_installation_enrollment(
        "client-test", "a" * 64, "b" * 64, "A" * 43
    )


@pytest.mark.asyncio
async def test_enrollment_and_signed_checks_reject_replays_and_bearer_only(owner_database, monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    owner_private = owner_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    owner_public = base64.urlsafe_b64encode(owner_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    client_key = Ed25519PrivateKey.generate()
    client_private = client_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    client_public = base64.urlsafe_b64encode(client_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-test", "customer_id": "customer-test",
        "domains": ["customer.example"], "features": [], "limits": {},
    }, owner_private)
    async with owner_database() as session:
        record = await session.get(ClientInstallationModel, "client-test")
        record.token_fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        await session.commit()
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(owner_private, owner_public)])
    issued = await owner_routes.create_installation_enrollment_token("client-test", _user=SimpleNamespace(id=1))
    secret = issued["enrollment_token"]
    fields = {
        "installation_id": "client-test", "license_token": token, "enrollment_token": secret,
        "public_key": client_public, "nonce": "e" * 43, "issued_at": now,
    }
    request = client_installation_check.InstallationEnrollmentRequest(
        enrollment_token=secret, public_key=client_public, nonce=fields["nonce"],
        issued_at=now, signature=sign_enrollment(client_private, **fields),
    )
    with pytest.raises(HTTPException) as bad_enrollment:
        await client_installation_check.enroll_client_installation(
            request.model_copy(update={"enrollment_token": "x" * 43}), f"Bearer {token}"
        )
    assert bad_enrollment.value.status_code == 401
    assert await client_installation_check.enroll_client_installation(request, f"Bearer {token}") == {"enrolled": True}
    with pytest.raises(HTTPException) as replay:
        await client_installation_check.enroll_client_installation(request, f"Bearer {token}")
    assert replay.value.status_code == 401

    http_request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"), headers={})
    unsigned = client_installation_check.InstallationCheckRequest(nonce="n" * 43, integrity_ok=True)
    with pytest.raises(HTTPException) as missing:
        await client_installation_check.check_client_installation(http_request, unsigned, f"Bearer {token}")
    assert missing.value.status_code == 401
    proof = {
        "installation_id": "client-test", "license_token": token, "nonce": "n" * 43,
        "issued_at": now, "integrity_ok": True, "integrity_finding": None,
    }
    signed = client_installation_check.InstallationCheckRequest(
        nonce=proof["nonce"], integrity_ok=True, proof_issued_at=now,
        proof_signature=sign_owner_check(client_private, **proof),
    )
    with pytest.raises(HTTPException) as altered:
        await client_installation_check.check_client_installation(
            http_request, signed.model_copy(update={"integrity_ok": False}), f"Bearer {token}"
        )
    assert altered.value.status_code == 401
    response = await client_installation_check.check_client_installation(http_request, signed, f"Bearer {token}")
    assert verify_installation_status(
        response["signed_status"], public_key=owner_public, installation_id="client-test",
        license_token=token, nonce=signed.nonce,
    ) is False
    with pytest.raises(HTTPException) as reused:
        await client_installation_check.check_client_installation(http_request, signed, f"Bearer {token}")
    assert reused.value.status_code == 401
