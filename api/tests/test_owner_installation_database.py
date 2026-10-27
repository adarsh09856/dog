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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import client_installations
from api.db.kodewaves_models import ClientInstallationModel
from api.routes.admin import client_installation_check
from api.services.installation_license import issue_license_token, verify_installation_status

@pytest_asyncio.fixture
async def owner_database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: ClientInstallationModel.__table__.create(sync))
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
