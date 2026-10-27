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
from api.routes.admin import client_installations
from api.services.installation_license import load_license


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
