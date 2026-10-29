"""Opt-in real PostgreSQL checks for client release controls.

Set KODEWAVES_CLIENT_RELEASE_TEST_DATABASE_URL to a loopback PostgreSQL
database named kodewaves_client_release_test. This uses a temporary schema with
only the tables needed for each check, not a fully migrated installation.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.client_installations import (
    acknowledge_client_integrity_alert,
    create_client_installation_record,
    get_client_binding_request,
    get_client_installation_record,
    issue_installation_enrollment,
    list_client_integrity_alerts,
    record_client_installation_check,
    resolve_client_binding_request,
    renew_client_installation_record,
    revoke_client_installation_record,
)
from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    ClientBindingRequestModel,
    ClientDomainChallengeModel,
    ClientInstallationModel,
    ClientInstallationNonceModel,
    ClientIntegrityAlertModel,
)
from api.db.user_client import UserClient
from api.db.client_user_management import list_workspace_users, set_workspace_user_active
from api.db import db_client
from api.services import bootstrap_client_admin
from api.services import client_creation_limits
from api.services import installation_license
from api.services.client_binding_requests import accept_binding_request, approve_binding_request
from api.routes.admin import client_installation_check
from api.services.installation_identity import sign_binding_request, sign_enrollment, sign_owner_check
from api.services.installation_license import issue_license_token, verify_installation_status_claims


def _disposable_database_url() -> str:
    database_url = os.getenv("KODEWAVES_CLIENT_RELEASE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Disposable client-release PostgreSQL database was not supplied")
    parsed = make_url(database_url)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or parsed.database != "kodewaves_client_release_test"
    ):
        pytest.fail("Client release tests require a loopback database named kodewaves_client_release_test")
    return database_url


@pytest.mark.asyncio
async def test_concurrent_first_signups_create_exactly_one_owner(monkeypatch):
    database_url = _disposable_database_url()

    schema = f"owner_race_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE organizations (id SERIAL PRIMARY KEY)"))
            await conn.execute(text("""CREATE TABLE users (
                id SERIAL PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ,
                selected_organization_id INTEGER REFERENCES organizations(id),
                is_superuser BOOLEAN, is_active BOOLEAN NOT NULL,
                email VARCHAR, password_hash VARCHAR
            )"""))
            await conn.execute(text(
                "CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email)) WHERE email IS NOT NULL"
            ))

        # Exercise the shared owner lock, independently of separate client-seat
        # license checks. Delay the count while its transaction lock is held.
        monkeypatch.setattr("api.services.client_creation_limits.KODEWAVES_EDITION", "saas")
        factory = async_sessionmaker(engine)

        @asynccontextmanager
        async def delayed_session():
            async with factory() as session:
                original = session.execute

                async def execute(statement, *args, **kwargs):
                    result = await original(statement, *args, **kwargs)
                    if "count(" in str(statement).lower():
                        await asyncio.sleep(0.05)
                    return result

                session.execute = execute
                yield session

        client = UserClient.__new__(UserClient)
        client.async_session = delayed_session
        users = await asyncio.wait_for(
            asyncio.gather(*(
                client.create_user_with_email(f"user{i}@example.test", "test-hash")
                for i in range(12)
            )),
            timeout=45,
        )
        async with engine.connect() as conn:
            persisted = (await conn.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE is_superuser) FROM users"
            ))).one()
        assert len(users) == 12
        assert sum(bool(user.is_superuser) for user in users) == 1
        assert tuple(persisted) == (12, 1)
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_enrolled_identity_replay_and_integrity_alert_persist(monkeypatch):
    database_url = _disposable_database_url()
    schema = f"client_license_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("INSERT INTO users (id) VALUES (1)"))
            for model in (ClientInstallationModel, ClientInstallationNonceModel, ClientIntegrityAlertModel):
                await conn.run_sync(lambda sync_conn, table=model.__table__: table.create(sync_conn))

        monkeypatch.setattr(kodewaves_db_client, "async_session", async_sessionmaker(engine))
        monkeypatch.delenv("KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS", raising=False)
        owner = Ed25519PrivateKey.generate()
        client = Ed25519PrivateKey.generate()

        def private_bytes(key):
            return key.private_bytes(
                serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )

        def public_string(key):
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            return base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")

        owner_private, owner_public = private_bytes(owner), public_string(owner)
        client_private, client_public = private_bytes(client), public_string(client)
        monkeypatch.setattr(
            client_installation_check, "_owner_verification_signers",
            lambda: [(owner_private, owner_public)],
        )
        now = int(time.time())
        installation_id = "client-integration-1"
        token = issue_license_token({
            "iat": now - 1, "exp": now + 3600, "edition": "client",
            "installation_id": installation_id, "customer_id": "buyer-1",
            "domains": ["customer.example"], "ip_ranges": ["203.0.113.0/24"],
            "features": ["voice"], "limits": {"max_concurrent_calls": 2},
        }, owner_private)
        await create_client_installation_record(
            installation_id=installation_id, customer_id="buyer-1",
            domains=["customer.example"], ip_ranges=["203.0.113.0/24"],
            features=["voice"], limits={"max_concurrent_calls": 2},
            expires_at=datetime.fromtimestamp(now + 3600, UTC),
            token_fingerprint=hashlib.sha256(token.encode("ascii")).hexdigest(),
            issued_by_user_id=1,
        )
        assert await record_client_installation_check(
            installation_id,
            hashlib.sha256(token.encode("ascii")).hexdigest(),
            integrity_ok=True,
        ) is None
        enrollment_token = secrets.token_urlsafe(32)
        assert await issue_installation_enrollment(
            installation_id, hashlib.sha256(enrollment_token.encode("ascii")).hexdigest()
        )
        nonce = secrets.token_urlsafe(32)
        enrollment = {
            "enrollment_token": enrollment_token, "public_key": client_public,
            "nonce": nonce, "issued_at": now,
            "signature": sign_enrollment(
                client_private, installation_id=installation_id, license_token=token,
                enrollment_token=enrollment_token, public_key=client_public,
                nonce=nonce, issued_at=now,
            ),
        }
        app = FastAPI()
        app.include_router(client_installation_check.router)
        headers = {"Authorization": f"Bearer {token}"}
        bad_transport = httpx.ASGITransport(app=app, client=("198.51.100.7", 1234))
        async with httpx.AsyncClient(transport=bad_transport, base_url="http://owner") as http:
            denied = await http.post("/client-installations/enroll", json=enrollment, headers=headers)
            assert denied.status_code == 401

        transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://owner") as http:
            unsigned = await http.post(
                "/client-installations/check",
                json={"nonce": secrets.token_urlsafe(32), "integrity_ok": True},
                headers=headers,
            )
            assert unsigned.status_code == 401
            assert "enroll this installation" in unsigned.json()["detail"]
            enrolled = await http.post("/client-installations/enroll", json=enrollment, headers=headers)
            assert enrolled.status_code == 200 and enrolled.json() == {"enrolled": True}
            assert (await http.post("/client-installations/enroll", json=enrollment, headers=headers)).status_code == 401

            async def check(integrity_ok, finding=None, http_client=http):
                nonce = secrets.token_urlsafe(32)
                issued_at = int(time.time())
                payload = {
                    "nonce": nonce, "integrity_ok": integrity_ok, "integrity_finding": finding,
                    "proof_issued_at": issued_at,
                    "proof_signature": sign_owner_check(
                        client_private, installation_id=installation_id, license_token=token,
                        nonce=nonce, issued_at=issued_at, integrity_ok=integrity_ok,
                        integrity_finding=finding,
                    ),
                }
                response = await http_client.post("/client-installations/check", json=payload, headers=headers)
                assert response.status_code == 200, response.text
                status = verify_installation_status_claims(
                    response.json()["signed_status"], public_key=owner_public,
                    installation_id=installation_id, license_token=token, nonce=nonce,
                )
                return payload, status

            good_payload, good_status = await check(True)
            assert good_status["revoked"] is False and good_status["binding_valid"] is True
            assert (await http.post("/client-installations/check", json=good_payload, headers=headers)).status_code == 401
            assert (await http.post(
                "/client-installations/check",
                json={"nonce": secrets.token_urlsafe(32), "integrity_ok": True}, headers=headers,
            )).status_code == 401
            async with httpx.AsyncClient(transport=bad_transport, base_url="http://owner") as bad_http:
                _, bad_status = await check(True, http_client=bad_http)
                assert bad_status["binding_valid"] is False
            finding = {"reason": "modified_file", "component": ".next/server/app.js"}
            _, tampered_status = await check(False, finding)
            assert tampered_status["revoked"] is True
            alerts = await list_client_integrity_alerts()
            assert len(alerts) == 1
            assert alerts[0]["installation_id"] == installation_id
            assert alerts[0]["reason"] == "modified_file" and alerts[0]["component"] == finding["component"]
            assert await acknowledge_client_integrity_alert(alerts[0]["id"], 1)
            assert await list_client_integrity_alerts() == []
            _, repeated_tamper_status = await check(False, finding)
            assert repeated_tamper_status["revoked"] is True
            active_alerts = await list_client_integrity_alerts()
            assert len(active_alerts) == 1
            assert active_alerts[0]["occurrence_count"] == 2
            assert active_alerts[0]["acknowledged_at"] is None
            _, later_status = await check(True)
            assert later_status["revoked"] is True
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_renewal_handover_and_revocation_persist(monkeypatch):
    database_url = _disposable_database_url()
    schema = f"client_renewal_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(database_url, connect_args={"server_settings": {"search_path": schema}})
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("INSERT INTO users (id) VALUES (1)"))
            await conn.run_sync(ClientInstallationModel.__table__.create)
            await conn.run_sync(ClientInstallationNonceModel.__table__.create)
        monkeypatch.setattr(kodewaves_db_client, "async_session", async_sessionmaker(engine))

        installation_id = "client-renewal-1"
        old_fingerprint = hashlib.sha256(b"old-signed-token").hexdigest()
        new_fingerprint = hashlib.sha256(b"new-signed-token").hexdigest()
        initial_expiry = datetime.now(UTC) + timedelta(days=7)
        extended_expiry = initial_expiry + timedelta(days=30)
        await create_client_installation_record(
            installation_id=installation_id, customer_id="buyer-1",
            domains=["customer.example"], ip_ranges=[], features=["voice"],
            limits={"max_concurrent_calls": 2}, expires_at=initial_expiry,
            token_fingerprint=old_fingerprint, issued_by_user_id=1,
            installation_public_key="A" * 43,
        )

        assert await renew_client_installation_record(
            installation_id, old_fingerprint, new_fingerprint, extended_expiry, 1,
        )
        assert not await renew_client_installation_record(
            installation_id, old_fingerprint, new_fingerprint, extended_expiry, 1,
        )
        old_status = await record_client_installation_check(
            installation_id, old_fingerprint, integrity_ok=True,
            expected_public_key="A" * 43,
            nonce_fingerprint=hashlib.sha256(b"old-token-check").hexdigest(),
            nonce_expires_at=datetime.now(UTC) + timedelta(seconds=91),
        )
        new_status = await record_client_installation_check(
            installation_id, new_fingerprint, integrity_ok=True,
            expected_public_key="A" * 43,
            nonce_fingerprint=hashlib.sha256(b"new-token-check").hexdigest(),
            nonce_expires_at=datetime.now(UTC) + timedelta(seconds=91),
        )
        assert old_status is not None and new_status is not None
        assert old_status["expires_at"] <= int(initial_expiry.timestamp())
        assert new_status["expires_at"] == int(extended_expiry.timestamp())

        assert await revoke_client_installation_record(installation_id, 1)
        old_status = await record_client_installation_check(
            installation_id, old_fingerprint, integrity_ok=True,
            expected_public_key="A" * 43,
            nonce_fingerprint=hashlib.sha256(b"old-token-revoked-check").hexdigest(),
            nonce_expires_at=datetime.now(UTC) + timedelta(seconds=91),
        )
        new_status = await record_client_installation_check(
            installation_id, new_fingerprint, integrity_ok=True,
            expected_public_key="A" * 43,
            nonce_fingerprint=hashlib.sha256(b"new-token-revoked-check").hexdigest(),
            nonce_expires_at=datetime.now(UTC) + timedelta(seconds=91),
        )
        assert old_status is not None and old_status["revoked_at"] is not None
        assert new_status is not None and new_status["revoked_at"] is not None
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_binding_request_nonce_conflict_and_atomic_approval_persist(monkeypatch):
    """Exercise binding proof replay, pending conflicts and approval on PostgreSQL."""
    database_url = _disposable_database_url()
    schema = f"client_binding_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(database_url, connect_args={"server_settings": {"search_path": schema}})
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("INSERT INTO users (id) VALUES (1)"))
            for model in (
                ClientInstallationModel,
                ClientInstallationNonceModel,
                ClientBindingRequestModel,
                ClientDomainChallengeModel,
            ):
                await conn.run_sync(model.__table__.create)
        monkeypatch.setattr(kodewaves_db_client, "async_session", async_sessionmaker(engine))

        owner = Ed25519PrivateKey.generate()
        client = Ed25519PrivateKey.generate()

        def private_bytes(key):
            return key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )

        def public_string(key):
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            return base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")

        owner_private, owner_public = private_bytes(owner), public_string(owner)
        client_private, client_public = private_bytes(client), public_string(client)
        now = int(time.time())
        installation_id = "client-binding-integration-1"
        old_domains = ["old-customer.example"]
        old_ip_ranges = ["192.0.2.0/24"]
        token = issue_license_token({
            "iat": now - 1,
            "exp": now + 3600,
            "edition": "client",
            "installation_id": installation_id,
            "customer_id": "buyer-binding-1",
            "domains": old_domains,
            "ip_ranges": old_ip_ranges,
            "features": ["voice"],
            "limits": {"max_concurrent_calls": 2},
        }, owner_private)
        old_fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        await create_client_installation_record(
            installation_id=installation_id,
            customer_id="buyer-binding-1",
            domains=old_domains,
            ip_ranges=old_ip_ranges,
            features=["voice"],
            limits={"max_concurrent_calls": 2},
            expires_at=datetime.fromtimestamp(now + 3600, UTC),
            token_fingerprint=old_fingerprint,
            issued_by_user_id=1,
            installation_public_key=client_public,
        )

        requested = client_installation_check.InstallationBindingRequest(
            nonce=secrets.token_urlsafe(32),
            issued_at=now,
            signature="A" * 86,
            domains=["Voice.New-Customer.Example", "new-customer.example"],
            ip_ranges=["198.51.100.10", "203.0.113.0/24"],
            reason="Move to a new server",
        )
        fields = {
            "installation_id": installation_id,
            "license_token": token,
            "nonce": requested.nonce,
            "issued_at": requested.issued_at,
            "domains": requested.domains,
            "ip_ranges": requested.ip_ranges,
            "reason": requested.reason,
        }

        async def submit(proof_fields):
            request = {
                "nonce": proof_fields["nonce"],
                "issued_at": proof_fields["issued_at"],
                "domains": proof_fields["domains"],
                "ip_ranges": proof_fields["ip_ranges"],
                "reason": proof_fields["reason"],
                "signature": sign_binding_request(client_private, **proof_fields),
            }
            return await accept_binding_request(request, token, [(owner_private, owner_public)])

        accepted = await submit(fields)
        assert accepted["status"] == "pending"
        request_id = accepted["id"]

        # A valid signature and nonce are one-use even before approval.
        with pytest.raises(HTTPException) as replay:
            await submit(fields)
        assert replay.value.status_code == 401

        # A distinct valid proof conflicts with the pending request, but its
        # nonce is consumed so the same proof cannot be retried after resolution.
        conflicting_fields = {**fields, "nonce": secrets.token_urlsafe(32)}
        with pytest.raises(HTTPException) as conflict:
            await submit(conflicting_fields)
        assert conflict.value.status_code == 409
        with pytest.raises(HTTPException) as consumed_conflict:
            await submit(conflicting_fields)
        assert consumed_conflict.value.status_code == 401

        async with engine.begin() as conn:
            verified_at = datetime.now(UTC)
            for domain in requested.domains:
                await conn.execute(text("""INSERT INTO client_domain_challenges
                    (customer_id, domain, token_sha256, expires_at, verified_at, created_at)
                    VALUES (:customer_id, :domain, :token_sha256, :expires_at, :verified_at, :created_at)
                """), {
                    "customer_id": "buyer-binding-1",
                    "domain": domain,
                    "token_sha256": hashlib.sha256(domain.encode("ascii")).hexdigest(),
                    "expires_at": verified_at + timedelta(days=1),
                    "verified_at": verified_at,
                    "created_at": verified_at,
                })

        approved = await approve_binding_request(
            request_id, 1, lambda: (owner_private, owner_public),
        )
        assert approved["status"] == "approved"
        replacement = installation_license.load_license(
            approved["token"], owner_public, now=int(time.time()),
        )
        assert replacement.domains == tuple(requested.domains)
        assert replacement.ip_ranges == tuple(requested.ip_ranges)
        assert replacement.installation_id == installation_id

        async with engine.connect() as conn:
            installation = (await conn.execute(text("""SELECT token_fingerprint,
                previous_token_fingerprint, domains, ip_ranges
                FROM client_installations WHERE installation_id = :installation_id
            """), {"installation_id": installation_id})).one()
        assert installation.token_fingerprint == hashlib.sha256(
            approved["token"].encode("ascii")
        ).hexdigest()
        assert installation.previous_token_fingerprint == old_fingerprint
        assert installation.domains == requested.domains
        assert installation.ip_ranges == requested.ip_ranges
        persisted_request = await get_client_binding_request(request_id)
        assert persisted_request["status"] == "approved"
        assert persisted_request["requested_domains"] == requested.domains
        assert persisted_request["requested_ip_ranges"] == requested.ip_ranges
        token_claims = json.loads(installation_license._b64url_decode(approved["token"].split(".", 1)[0]))
        assert persisted_request["license_issued_at"] == token_claims["iat"]

        # Resolution is one-shot; a second approval cannot change the token or
        # the binding after the first transaction has committed.
        with pytest.raises(HTTPException) as second_resolution:
            await approve_binding_request(
                request_id, 1, lambda: (owner_private, owner_public),
            )
        assert second_resolution.value.status_code == 404
        assert not await resolve_client_binding_request(
            request_id, outcome="rejected", user_id=1,
        )
        unchanged = await get_client_installation_record(installation_id)
        assert unchanged["token_fingerprint"] == installation.token_fingerprint
        assert unchanged["domains"] == requested.domains
        assert unchanged["ip_ranges"] == requested.ip_ranges
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_client_user_changes_are_scoped_to_workspace(monkeypatch):
    database_url = _disposable_database_url()
    schema = f"client_tenants_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(database_url, connect_args={"server_settings": {"search_path": schema}})
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE organizations (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("""CREATE TABLE users (
                id INTEGER PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ, selected_organization_id INTEGER REFERENCES organizations(id),
                is_superuser BOOLEAN, is_active BOOLEAN NOT NULL, email VARCHAR, password_hash VARCHAR
            )"""))
            await conn.execute(text("""CREATE TABLE organization_users (
                user_id INTEGER NOT NULL REFERENCES users(id),
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                PRIMARY KEY (user_id, organization_id)
            )"""))
            await conn.execute(text("INSERT INTO organizations (id) VALUES (1), (2)"))
            await conn.execute(text("INSERT INTO users (id, provider_id, selected_organization_id, is_superuser, is_active) VALUES (1, 'one', 1, false, true), (2, 'two', 2, false, true), (3, 'shared', 1, false, true)"))
            await conn.execute(text("INSERT INTO organization_users (user_id, organization_id) VALUES (1, 1), (2, 2), (3, 1), (3, 2)"))
        monkeypatch.setattr(db_client, "async_session", async_sessionmaker(engine))
        assert {user.id for user in await list_workspace_users(1)} == {1, 3}
        with pytest.raises(HTTPException) as foreign:
            await set_workspace_user_active(1, 2, active=False)
        assert foreign.value.status_code == 404
        with pytest.raises(HTTPException) as shared:
            await set_workspace_user_active(1, 3, active=False)
        assert shared.value.status_code == 409
        assert (await set_workspace_user_active(1, 1, active=False)).is_active is False
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT is_active FROM users WHERE id = 2"))).scalar_one() is True
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_client_signups_cannot_exceed_signed_seat_limit(monkeypatch):
    database_url = _disposable_database_url()
    schema = f"client_seats_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(database_url, connect_args={"server_settings": {"search_path": schema}})
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE organizations (id SERIAL PRIMARY KEY)"))
            await conn.execute(text("""CREATE TABLE users (
                id SERIAL PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ, selected_organization_id INTEGER REFERENCES organizations(id),
                is_superuser BOOLEAN, is_active BOOLEAN NOT NULL, email VARCHAR, password_hash VARCHAR
            )"""))
        monkeypatch.setattr(client_creation_limits, "KODEWAVES_EDITION", "client")
        key = Ed25519PrivateKey.generate()
        private_key = key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )
        public_key = base64.urlsafe_b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )).rstrip(b"=").decode("ascii")
        now = int(time.time())
        token = issue_license_token({
            "iat": now - 1, "exp": now + 3600, "edition": "client",
            "installation_id": "seat-test-1", "customer_id": "customer-1",
            "domains": ["customer.example"], "features": ["voice"],
            "limits": {"max_seats": 2},
        }, private_key)
        monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
        monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "seat-test-1")
        monkeypatch.setattr(installation_license, "runtime_edition", lambda: "client")
        monkeypatch.setattr(installation_license, "trusted_license_public_keys", lambda: (public_key,))
        monkeypatch.setattr(installation_license, "get_installation_binding", lambda: "customer.example")
        monkeypatch.setattr(client_creation_limits, "require_current_owner_status", AsyncMock())
        client = UserClient.__new__(UserClient)
        client.async_session = async_sessionmaker(engine)

        async def signup(index):
            try:
                return await client.create_user_with_email(f"seat{index}@example.test", "test-hash")
            except HTTPException as exc:
                assert exc.status_code == 403 and "max_seats" in exc.detail
                return None

        users = await asyncio.wait_for(asyncio.gather(*(signup(i) for i in range(8))), timeout=45)
        assert sum(user is not None for user in users) == 2
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one() == 2
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()


@pytest.mark.asyncio
async def test_signed_client_license_bootstraps_first_admin_and_workspace_in_postgres(monkeypatch):
    """Exercise the real first-admin transaction with a verified client license."""
    database_url = _disposable_database_url()
    schema = f"client_bootstrap_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TYPE quota_type AS ENUM ('monthly', 'annual')"
            ))
            await conn.execute(text("""CREATE TABLE organizations (
                id SERIAL PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ, status VARCHAR NOT NULL DEFAULT 'active',
                quota_type quota_type NOT NULL DEFAULT 'monthly',
                quota_dograh_tokens INTEGER NOT NULL DEFAULT 0,
                quota_reset_day INTEGER NOT NULL DEFAULT 1,
                quota_start_date TIMESTAMPTZ,
                quota_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                price_per_second_usd FLOAT
            )"""))
            await conn.execute(text("""CREATE TABLE users (
                id SERIAL PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ,
                selected_organization_id INTEGER REFERENCES organizations(id),
                is_superuser BOOLEAN, is_active BOOLEAN NOT NULL,
                email VARCHAR, password_hash VARCHAR
            )"""))
            await conn.execute(text("""CREATE TABLE organization_users (
                user_id INTEGER NOT NULL REFERENCES users(id),
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                PRIMARY KEY (user_id, organization_id)
            )"""))

        key = Ed25519PrivateKey.generate()
        private_key = key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        public_key = base64.urlsafe_b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )).rstrip(b"=").decode("ascii")
        now = int(time.time())
        installation_id = "bootstrap-integration-1"
        token = issue_license_token({
            "iat": now - 1, "exp": now + 3600, "edition": "client",
            "installation_id": installation_id, "customer_id": "customer-1",
            "domains": ["customer.example"], "features": ["voice"],
            "limits": {"max_seats": 3, "max_workspaces": 1},
        }, private_key)
        monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", installation_id)
        verified_license = installation_license.load_license(
            token, public_key=public_key, now=now,
        )
        monkeypatch.setattr(bootstrap_client_admin, "KODEWAVES_EDITION", "client")
        monkeypatch.setattr(bootstrap_client_admin, "AUTH_PROVIDER", "local")
        monkeypatch.setattr(bootstrap_client_admin, "load_license", lambda: verified_license)
        monkeypatch.setattr(
            bootstrap_client_admin, "validate_installation_license",
            lambda license_data: installation_license.validate_installation_license(
                license_data, request_hostname="customer.example",
            ),
        )
        monkeypatch.setattr(bootstrap_client_admin, "verify_configured_release", lambda: None)
        monkeypatch.setattr(
            bootstrap_client_admin, "enforce_client_creation_limit", AsyncMock(),
        )
        monkeypatch.setattr(bootstrap_client_admin.db_client, "async_session", async_sessionmaker(engine))
        administrator_id = await bootstrap_client_admin.bootstrap_client_admin(
            "Admin@Customer.Example", "long-enough-password-123",
        )

        async with engine.connect() as conn:
            user = (await conn.execute(text(
                "SELECT email, is_superuser, is_active, selected_organization_id "
                "FROM users WHERE id = :id"
            ), {"id": administrator_id})).one()
            workspace = (await conn.execute(text(
                "SELECT provider_id FROM organizations WHERE id = :id"
            ), {"id": user.selected_organization_id})).one()
            membership_count = (await conn.execute(text(
                "SELECT count(*) FROM organization_users "
                "WHERE user_id = :user_id AND organization_id = :organization_id"
            ), {"user_id": administrator_id, "organization_id": user.selected_organization_id})).scalar_one()
            assert tuple(user[:3]) == ("admin@customer.example", True, True)
            assert workspace.provider_id.startswith("org_oss_bootstrap_")
            assert membership_count == 1
            assert (await conn.execute(text("SELECT count(*) FROM users"))).scalar_one() == 1
            assert (await conn.execute(text("SELECT count(*) FROM organizations"))).scalar_one() == 1

        with pytest.raises(ValueError, match="only before the first account"):
            await bootstrap_client_admin.bootstrap_client_admin(
                "second@customer.example", "long-enough-password-123",
            )
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()
