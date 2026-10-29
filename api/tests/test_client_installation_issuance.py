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

from api.db import client_installations as installation_records
from api.routes.admin import client_installation_check, client_installations
from api.services import client_binding_requests as binding_service
from api.services.installation_identity import sign_binding_request
from api.services.installation_license import issue_license_token, load_license


@pytest.mark.parametrize(
    "changes",
    [
        {"features": ["voiec"]},
        {"features": ["voice"], "limits": {}},
        {"features": ["voice"], "limits": {"max_concurrent_calls": 0}},
        {"features": ["voice"], "limits": {"max_concurrent_calls": 2, "max_monthly_minutes": 100}},
        {"features": ["voice"], "limits": {"max_concurrent_calls": 2, "max_seats": 0}},
        {"features": ["voice"], "limits": {"max_concurrent_calls": 2, "max_workspaces": 0}},
        {"features": ["voice"], "limits": {"max_concurrent_calls": 2, "max_agents": True}},
        {"features": ["campaigns", "voice"], "limits": {"max_concurrent_calls": 2}},
        {"installation_id": "  "},
        {"installation_id": "ab"},
        {"installation_id": "client/invalid"},
    ],
)
def test_owner_issuance_rejects_unusable_entitlements(changes):
    data = {
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "domains": ["example.com"],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 2},
        "expires_at": int(time.time()) + 3600,
    }
    data.update(changes)
    with pytest.raises(ValidationError):
        client_installations.IssueClientInstallation.model_validate(data)


def test_owner_issuance_accepts_enforced_creation_caps():
    request = client_installations.IssueClientInstallation.model_validate({
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "domains": ["example.com"],
        "features": ["voice"],
        "limits": {
            "max_concurrent_calls": 2,
            "max_seats": 4,
            "max_workspaces": 2,
            "max_agents": 10,
            "max_campaigns": 20,
        },
        "expires_at": int(time.time()) + 3600,
    })
    assert request.limits["max_agents"] == 10
    assert request.limits["max_campaigns"] == 20


def test_owner_signer_preserves_raw_key_bytes_that_look_like_whitespace(monkeypatch, tmp_path):
    raw = b" " + bytes(range(1, 31)) + b"\n"
    key_path = tmp_path / "raw-private-key"
    key_path.write_bytes(raw)
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(key_path))
    loaded, _public = client_installations._owner_signing_key()
    assert loaded == raw


def test_owner_signer_rejects_overpadded_base64_private_key(monkeypatch, tmp_path):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "owner-private-key"
    key_path.write_bytes(base64.urlsafe_b64encode(raw) + b"=")
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(key_path))

    with pytest.raises(HTTPException) as error:
        client_installations._owner_signing_key()
    assert error.value.status_code == 503
    assert error.value.detail == "Owner license signer is unavailable"


@pytest.mark.asyncio
async def test_owner_binding_request_requires_enrolled_installation_proof(monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    owner_private = owner_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    owner_public = base64.urlsafe_b64encode(owner_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    installation_key = Ed25519PrivateKey.generate()
    installation_private = installation_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    installation_public = base64.urlsafe_b64encode(installation_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    issued_at = int(time.time())
    token = issue_license_token({
        "iat": issued_at - 1,
        "exp": issued_at + 3600,
        "edition": "client",
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "domains": ["old.example"],
        "ip_ranges": [],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 1},
    }, owner_private)
    fields = {
        "installation_id": "install-test",
        "license_token": token,
        "nonce": "r" * 43,
        "issued_at": issued_at,
        "domains": ["new.example"],
        "ip_ranges": ["203.0.113.9/32"],
        "reason": "Move to a new host",
    }
    signature = sign_binding_request(installation_private, **fields)
    monkeypatch.setattr(client_installation_check, "_owner_verification_signers", lambda: [(owner_private, owner_public)])
    monkeypatch.setattr(
        binding_service, "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": installation_public}),
    )
    create_request = AsyncMock(return_value={
        "id": 15,
        "installation_id": "install-test",
        "requested_domains": ["new.example"],
        "requested_ip_ranges": ["203.0.113.9/32"],
        "reason": "Move to a new host",
        "status": "pending",
        "created_at": "2026-10-29T00:00:00+00:00",
    })
    monkeypatch.setattr(binding_service, "create_client_binding_request", create_request)
    request = client_installation_check.InstallationBindingRequest(
        nonce=fields["nonce"],
        issued_at=issued_at,
        signature=signature,
        domains=fields["domains"],
        ip_ranges=fields["ip_ranges"],
        reason=fields["reason"],
    )

    result = await client_installation_check.submit_client_binding_request(request, f"Bearer {token}")

    assert result["id"] == 15
    assert result["status"] == "pending"
    assert create_request.await_args.kwargs["installation_id"] == "install-test"
    assert create_request.await_args.kwargs["public_key"] == installation_public
    assert create_request.await_args.kwargs["domains"] == ["new.example"]

    tampered = request.model_copy(update={"reason": "Changed after signing"})
    with pytest.raises(HTTPException) as error:
        await client_installation_check.submit_client_binding_request(tampered, f"Bearer {token}")
    assert error.value.status_code == 401
    assert create_request.await_count == 1


@pytest.mark.asyncio
async def test_binding_request_approval_requires_dns_proof_and_rotates_signed_claims(monkeypatch, tmp_path):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "owner-private-key"
    key_path.write_bytes(raw)
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(key_path))
    request = {
        "id": 31,
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "requested_domains": ["new.example"],
        "requested_ip_ranges": ["198.51.100.10/32"],
        "reason": "Moving servers",
        "status": "pending",
        "license_issued_at": None,
    }
    expires_at = int(time.time()) + 3600
    monkeypatch.setattr(binding_service, "get_client_binding_request", AsyncMock(return_value=request))
    monkeypatch.setattr(binding_service, "get_client_installation_record", AsyncMock(return_value={
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "domains": ["old.example"],
        "ip_ranges": [],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 2},
        "expires_at": expires_at,
        "token_fingerprint": "a" * 64,
        "previous_token_valid_until": None,
        "revoked_at": None,
        "integrity_failed_at": None,
    }))
    verify_domains = AsyncMock(return_value=[])
    monkeypatch.setattr(binding_service, "unverified_license_domains", verify_domains)
    resolve = AsyncMock(return_value=True)
    monkeypatch.setattr(binding_service, "resolve_client_binding_request", resolve)
    user = SimpleNamespace(id=9)

    result = await client_installations.approve_binding_request(31, user)

    assert result["status"] == "approved"
    assert result["installation_id"] == "install-test"
    licensed = load_license(result["token"], result["public_key"])
    assert list(licensed.domains) == ["new.example"]
    assert list(licensed.ip_ranges) == ["198.51.100.10/32"]
    assert resolve.await_args.kwargs["expected_fingerprint"] == "a" * 64
    assert resolve.await_args.kwargs["domains"] == ["new.example"]
    assert isinstance(resolve.await_args.kwargs["license_issued_at"], int)

    verify_domains.return_value = ["new.example"]
    resolve.reset_mock()
    with pytest.raises(HTTPException) as error:
        await client_installations.approve_binding_request(31, user)
    assert error.value.status_code == 409
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_binding_token_recovery_recreates_exact_token_without_rotation(monkeypatch):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")
    issued_at = int(time.time()) - 30
    expires_at = int(time.time()) + 3600
    claims = {
        "iat": issued_at,
        "exp": expires_at,
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "edition": "client",
        "domains": ["new.example"],
        "ip_ranges": ["198.51.100.10/32"],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 2},
    }
    token = issue_license_token(claims, raw)
    request = {
        "id": 31,
        "installation_id": "install-test",
        "customer_id": "customer-test",
        "requested_domains": ["new.example"],
        "requested_ip_ranges": ["198.51.100.10/32"],
        "status": "approved",
        "license_issued_at": issued_at,
    }
    installation = {
        **claims,
        "expires_at": expires_at,
        "token_fingerprint": hashlib.sha256(token.encode("ascii")).hexdigest(),
        "revoked_at": None,
        "integrity_failed_at": None,
    }
    monkeypatch.setattr(binding_service, "get_client_binding_request", AsyncMock(return_value=request))
    monkeypatch.setattr(binding_service, "get_client_installation_record", AsyncMock(return_value=installation))

    recovered = await binding_service.recover_approved_binding_token(31, lambda: (raw, public))

    assert recovered["token"] == token
    assert recovered["public_key"] == public
    assert recovered["recovered"] is True

    installation["token_fingerprint"] = "c" * 64
    with pytest.raises(HTTPException) as error:
        await binding_service.recover_approved_binding_token(31, lambda: (raw, public))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_owner_issues_signed_installation_without_storing_bearer_token(
    monkeypatch, tmp_path
):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = tmp_path / "owner-private-key"
    key_path.write_bytes(base64.urlsafe_b64encode(raw).rstrip(b"="))
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(key_path))

    session = SimpleNamespace(add=lambda item: captured.append(item), commit=AsyncMock())
    captured = []

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(installation_records.kodewaves_db_client, "get_session", lambda: SessionContext())
    monkeypatch.setattr(client_installations, "unverified_license_domains", AsyncMock(return_value=[]))
    result = await client_installations.issue_client_installation(
        client_installations.IssueClientInstallation(
            installation_id="install-test",
            customer_id="customer-test",
            domains=["EXAMPLE.COM."],
            features=["voice", "telephony"],
            limits={"max_concurrent_calls": 2},
            expires_at=int(time.time()) + 3600,
        ),
        SimpleNamespace(id=5),
    )

    issued = load_license(result["token"], result["public_key"])
    assert issued.installation_id == "install-test"
    assert issued.domains == ("example.com",)
    assert issued.limits["max_concurrent_calls"] == 2
    assert len(captured) == 1
    assert captured[0].installation_id == "install-test"
    assert captured[0].issued_by_user_id == 5
    assert "token" not in captured[0].__dict__
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_cannot_issue_unverified_domain(monkeypatch):
    monkeypatch.setattr(
        client_installations, "unverified_license_domains",
        AsyncMock(return_value=["example.com"]),
    )
    with pytest.raises(HTTPException) as error:
        await client_installations.issue_client_installation(
            client_installations.IssueClientInstallation(
                installation_id="install-test", customer_id="customer-test",
                domains=["EXAMPLE.COM."], features=["voice"],
                limits={"max_concurrent_calls": 2}, expires_at=int(time.time()) + 3600,
            ),
            SimpleNamespace(id=5),
        )
    assert error.value.status_code == 409
    assert "example.com" in error.value.detail


@pytest.mark.asyncio
async def test_owner_renews_existing_license_without_storing_replacement_token(monkeypatch):
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    monkeypatch.setattr(client_installations, "_owner_signing_key", lambda: (raw, public))
    current_expiry = int(time.time()) + 3600
    monkeypatch.setattr(client_installations, "get_client_installation_record", AsyncMock(return_value={
        "installation_id": "install-test", "customer_id": "customer-test",
        "domains": ["example.com"], "ip_ranges": [], "features": ["voice"],
        "limits": {"max_concurrent_calls": 2}, "expires_at": current_expiry,
        "token_fingerprint": "a" * 64, "revoked_at": None, "integrity_failed_at": None,
    }))
    monkeypatch.setattr(client_installations, "unverified_license_domains", AsyncMock(return_value=[]))
    replacement = AsyncMock(return_value=True)
    monkeypatch.setattr(client_installations, "renew_client_installation_record", replacement)
    renewed = await client_installations.renew_client_installation(
        "install-test", client_installations.RenewClientInstallation(expires_at=current_expiry + 86400),
        SimpleNamespace(id=5),
    )
    assert load_license(renewed["token"], public).expires_at == current_expiry + 86400
    assert replacement.await_args.args[0:2] == ("install-test", "a" * 64)
    assert replacement.await_args.args[2] == hashlib.sha256(renewed["token"].encode()).hexdigest()


@pytest.mark.asyncio
async def test_dns_challenge_must_match_exact_token(monkeypatch):
    import hashlib

    from api.services import domain_challenge

    expected = hashlib.sha256(b"correct-token").hexdigest()

    class TxtRecord:
        def __init__(self, text):
            self.strings = [text.encode("ascii")]

    records = [TxtRecord("unrelated=value"), TxtRecord("kodewaves-verification=wrong-token")]

    class FakeResolver:
        def __init__(self, *, configure):
            assert configure is False
            self.nameservers = []

        async def resolve(self, *args, **kwargs):
            assert self.nameservers == ["1.1.1.1", "8.8.8.8"]
            assert args[0] == "_kodewaves-verification.example.com."
            assert args[1] == "TXT"
            assert kwargs["lifetime"] == 5.0
            return records

    monkeypatch.setattr(domain_challenge.dns.asyncresolver, "Resolver", FakeResolver)
    assert not await domain_challenge.dns_proves_domain("example.com", expected)

    records[:] = [TxtRecord("kodewaves-verification=correct-token")]
    assert await domain_challenge.dns_proves_domain("example.com", expected)


@pytest.mark.asyncio
async def test_owner_domain_challenge_requires_dns_proof_before_verification(monkeypatch):
    expiry = datetime.now(UTC) + timedelta(hours=24)
    save = AsyncMock(return_value=expiry)
    monkeypatch.setattr(client_installations, "save_domain_challenge", save)
    request = client_installations.DomainChallengeRequest(
        customer_id="customer-test", domain="EXAMPLE.COM."
    )
    challenge = await client_installations.create_domain_challenge(request, SimpleNamespace(id=5))
    assert challenge["domain"] == "example.com"
    assert challenge["record_type"] == "TXT"
    assert challenge["record_value"].startswith("kodewaves-verification=")
    assert save.await_args.args[:2] == ("customer-test", "example.com")
    assert save.await_args.args[2] != challenge["record_value"].split("=", 1)[1]

    pending = AsyncMock(return_value={"token_sha256": save.await_args.args[2]})
    dns_check = AsyncMock(return_value=False)
    mark = AsyncMock(return_value=datetime.now(UTC))
    monkeypatch.setattr(client_installations, "get_pending_domain_challenge", pending)
    monkeypatch.setattr(client_installations, "dns_proves_domain", dns_check)
    monkeypatch.setattr(client_installations, "mark_domain_verified", mark)
    with pytest.raises(HTTPException) as absent:
        await client_installations.verify_domain_challenge(request, SimpleNamespace(id=5))
    assert absent.value.status_code == 409
    mark.assert_not_awaited()

    dns_check.return_value = True
    result = await client_installations.verify_domain_challenge(request, SimpleNamespace(id=5))
    assert result["domain"] == "example.com"
    mark.assert_awaited_once_with("customer-test", "example.com", save.await_args.args[2])


@pytest.mark.asyncio
async def test_owner_revocation_is_persistent_and_idempotent(monkeypatch):
    record = SimpleNamespace(
        installation_id="install-test", revoked_at=None,
        revoked_by_user_id=None, updated_at=None,
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
    first = await installation_records.revoke_client_installation_record("install-test", 5)
    second = await installation_records.revoke_client_installation_record("install-test", 6)
    assert first == second
    assert record.revoked_by_user_id == 5
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_revocation_rejects_unknown_installation(monkeypatch):
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        commit=AsyncMock(),
    )

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(installation_records.kodewaves_db_client, "get_session", lambda: SessionContext())
    with pytest.raises(HTTPException) as error:
        await client_installations.revoke_client_installation("missing", SimpleNamespace(id=5))
    assert error.value.status_code == 404
    session.commit.assert_not_awaited()
