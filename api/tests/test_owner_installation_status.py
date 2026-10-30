import asyncio
import base64
import hashlib
import threading
import time
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services import owner_installation_status as owner_status
from api.services.installation_license import (
    InstallationLicense,
    InstallationLicenseError,
    issue_license_token,
)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("invalid", 60), ("0", 1), ("-5", 1), ("5", 5), ("99999", 3600)],
)
def test_owner_status_poll_interval_is_bounded(configured, expected):
    assert owner_status._owner_status_poll_seconds(configured) == expected


class FakeRedis:
    def __init__(self):
        self.fields = {}

    async def hset(self, _key, mapping):
        self.fields.update({key.encode(): value.encode() for key, value in mapping.items()})

    async def hgetall(self, _key):
        return self.fields


@pytest.mark.asyncio
async def test_integrity_scan_leaves_the_event_loop_available(monkeypatch):
    loop = asyncio.get_running_loop()
    heartbeat = threading.Event()
    monkeypatch.setattr(owner_status, "_trusted_owner_key", lambda: ())
    monkeypatch.setattr(owner_status, "load_license", lambda *_: SimpleNamespace(installation_id="client-1", ip_ranges=()))
    monkeypatch.setattr(owner_status, "validate_installation_license", lambda _: None)
    monkeypatch.setattr(owner_status, "_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "verify_installation_status_claims", lambda *_, **__: {"revoked": False})
    async def allowed(_license, _redis):
        return None
    monkeypatch.setattr(owner_status, "require_current_owner_status", allowed)

    def slow_scan():
        # Completion of this synchronous scan requires the voice/API event loop
        # to process another callback while file verification is in progress.
        loop.call_soon_threadsafe(heartbeat.set)
        assert heartbeat.wait(timeout=2), "Integrity scan blocked the event loop"

    monkeypatch.setattr(owner_status, "verify_configured_release", slow_scan)

    class FakeHttp:
        async def post(self, _url, **kwargs):
            assert kwargs["json"]["integrity_ok"] is True
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"signed_status": "signed"})

    assert await owner_status.poll_owner_status_once(FakeRedis(), FakeHttp()) is False


def signing_keys():
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode()
    return raw, public


@pytest.mark.asyncio
async def test_owner_poll_signs_when_installation_key_is_configured(monkeypatch, tmp_path):
    from api.services.installation_identity import verify_owner_check

    owner_private, owner_public = signing_keys()
    client_private, client_public = signing_keys()
    key_path = tmp_path / "client.key"
    key_path.write_bytes(client_private)
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": [], "limits": {},
    }, owner_private)
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_INSTALLATION_KEY_FILE", str(key_path))
    monkeypatch.setattr(owner_status, "_trusted_owner_key", lambda: (owner_public,))
    monkeypatch.setattr(owner_status, "_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "validate_installation_license", lambda _license: None)
    monkeypatch.setattr(owner_status, "verify_configured_release", lambda: None)

    class FakeHttp:
        async def post(self, _url, **kwargs):
            body = kwargs["json"]
            verify_owner_check(
                client_public, body["proof_signature"], installation_id="client-1", license_token=token,
                nonce=body["nonce"], issued_at=body["proof_issued_at"], integrity_ok=True,
                integrity_finding=None,
            )
            signed = issue_license_token({
                "kind": "installation_status", "installation_id": "client-1",
                "license_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
                "nonce": body["nonce"], "revoked": True,
                "issued_at": now, "expires_at": now + 300,
            }, owner_private)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"signed_status": signed})

    assert await owner_status.poll_owner_status_once(FakeRedis(), FakeHttp()) is True


@pytest.mark.asyncio
async def test_owner_poll_saves_verified_response_and_revocation_blocks_new_calls(monkeypatch):
    monkeypatch.setattr(owner_status, "_logged_initial_owner_check", False)
    messages = []
    monkeypatch.setattr(owner_status.logger, "info", lambda message, *_args: messages.append(message))
    private, public = signing_keys()
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": ["voice"],
        "limits": {"max_concurrent_calls": 2},
    }, private)
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public)
    monkeypatch.setattr(owner_status, "trusted_license_public_keys", lambda: (public,))
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "validate_installation_license", lambda _license: None)
    monkeypatch.setattr(owner_status, "verify_configured_release", lambda: None)
    monkeypatch.setattr(owner_status.secrets, "token_urlsafe", lambda _length: "a" * 43)
    signed = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "a" * 43, "revoked": True,
        "issued_at": now, "expires_at": now + 300,
    }, private)

    class FakeHttp:
        async def post(self, _url, **kwargs):
            assert kwargs["headers"]["Authorization"] == f"Bearer {token}"
            assert kwargs["json"] == {"nonce": "a" * 43, "integrity_ok": True, "integrity_finding": None}
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"signed_status": signed})

    redis = FakeRedis()
    assert await owner_status.poll_owner_status_once(redis, FakeHttp()) is True
    assert messages == []
    assert owner_status._logged_initial_owner_check is False
    assert redis.fields[b"revoked_latched"] == b"1"
    license_data = InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), now + 3600,
        frozenset({"voice"}), {"max_concurrent_calls": 2},
    )
    with pytest.raises(InstallationLicenseError, match="revoked"):
        await owner_status.require_current_owner_status(license_data, redis)
    # A concurrent worker can return an older active response afterward.
    active = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "a" * 43, "revoked": False,
        "issued_at": now, "expires_at": now + 300,
    }, private)
    class ActiveHttp:
        async def post(self, _url, **_kwargs):
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"signed_status": active})
    assert await owner_status.poll_owner_status_once(redis, ActiveHttp()) is False
    assert messages == []
    assert owner_status._logged_initial_owner_check is False
    await redis.hset("ignored", {"signed_status": active, "nonce": "a" * 43})
    with pytest.raises(InstallationLicenseError, match="revoked"):
        await owner_status.require_current_owner_status(license_data, redis)


@pytest.mark.asyncio
async def test_owner_status_outage_grace_expires(monkeypatch):
    private, public = signing_keys()
    now = int(time.time())
    token = "issued-license-token"
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public)
    monkeypatch.setattr(owner_status, "trusted_license_public_keys", lambda: (public,))
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    license_data = InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), now + 3600,
        frozenset({"voice"}), {"max_concurrent_calls": 2},
    )
    redis = FakeRedis()
    with pytest.raises(InstallationLicenseError, match="not succeeded"):
        await owner_status.require_current_owner_status(license_data, redis)
    signed = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "nonce-1", "revoked": False,
        "issued_at": now - 400, "expires_at": now - 100,
    }, private)
    await redis.hset("ignored", {"signed_status": signed, "nonce": "nonce-1"})
    grace = await owner_status.require_current_owner_status(license_data, redis)
    assert grace.last_owner_check == now - 400
    assert grace.using_outage_grace is True
    current = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "nonce-1", "revoked": False,
        "issued_at": now, "expires_at": now + 300,
    }, private)
    await redis.hset("ignored", {"signed_status": current, "nonce": "nonce-1"})
    fresh = await owner_status.require_current_owner_status(license_data, redis)
    assert fresh.last_owner_check == now
    assert fresh.using_outage_grace is False
    too_old = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "nonce-1", "revoked": False,
        "issued_at": now - 87000, "expires_at": now - 86700,
    }, private)
    await redis.hset("ignored", {"signed_status": too_old, "nonce": "nonce-1"})
    with pytest.raises(InstallationLicenseError, match="invalid"):
        await owner_status.require_current_owner_status(license_data, redis)


@pytest.mark.asyncio
async def test_ip_binding_failure_blocks_new_calls_without_revocation_latch(monkeypatch):
    private, public = signing_keys()
    now = int(time.time())
    token = "issued-license-token"
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public)
    monkeypatch.setattr(owner_status, "trusted_license_public_keys", lambda: (public,))
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    license_data = InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), now + 3600,
        frozenset({"voice"}), {"max_concurrent_calls": 2}, ("192.0.2.0/24",),
    )
    redis = FakeRedis()
    signed = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "nonce-ip", "revoked": False, "binding_valid": False,
        "observed_ip": "203.0.113.7", "issued_at": now, "expires_at": now + 300,
    }, private)
    await redis.hset("ignored", {"signed_status": signed, "nonce": "nonce-ip"})
    with pytest.raises(InstallationLicenseError, match="source IP"):
        await owner_status.require_current_owner_status(license_data, redis)
    assert b"revoked_latched" not in redis.fields


@pytest.mark.asyncio
async def test_ip_allowlist_does_not_use_owner_outage_grace(monkeypatch):
    private, public = signing_keys()
    now = int(time.time())
    token = "issued-license-token"
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public)
    monkeypatch.setattr(owner_status, "trusted_license_public_keys", lambda: (public,))
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    license_data = InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), now + 3600,
        frozenset({"voice"}), {"max_concurrent_calls": 2}, ("192.0.2.0/24",),
    )
    signed = issue_license_token({
        "kind": "installation_status", "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "nonce": "nonce-old", "revoked": False, "binding_valid": True,
        "observed_ip": "192.0.2.15", "issued_at": now - 301, "expires_at": now - 1,
    }, private)
    redis = FakeRedis()
    await redis.hset("ignored", {"signed_status": signed, "nonce": "nonce-old"})
    with pytest.raises(InstallationLicenseError, match="invalid"):
        await owner_status.require_current_owner_status(license_data, redis)


@pytest.mark.asyncio
async def test_local_integrity_failure_latches_even_when_owner_unreachable(monkeypatch):
    private, public = signing_keys()
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-1", "customer_id": "buyer-1",
        "domains": ["example.com"], "features": ["voice"],
        "limits": {"max_concurrent_calls": 2},
    }, private)
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public)
    monkeypatch.setattr(owner_status, "trusted_license_public_keys", lambda: (public,))
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(owner_status, "validate_installation_license", lambda _license: None)
    def fail_integrity():
        raise owner_status.ReleaseIntegrityError("modified")
    monkeypatch.setattr(owner_status, "verify_configured_release", fail_integrity)

    class OfflineHttp:
        async def post(self, _url, **kwargs):
            assert kwargs["json"]["integrity_ok"] is False
            assert kwargs["json"]["integrity_finding"]["component"] == "release"
            raise RuntimeError("owner unavailable")

    redis = FakeRedis()
    with pytest.raises(RuntimeError, match="unavailable"):
        await owner_status.poll_owner_status_once(redis, OfflineHttp())
    assert redis.fields[b"integrity_failed_latched"] == b"1"
    license_data = InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), now + 3600,
        frozenset({"voice"}), {"max_concurrent_calls": 2},
    )
    with pytest.raises(InstallationLicenseError, match="Protected installation files were modified"):
        await owner_status.require_current_owner_status(license_data, redis)
    # Owner confirmation of the same failure also latches revocation. The
    # customer must still see the more specific locally verified cause.
    await redis.hset("ignored", {"revoked_latched": "1"})
    with pytest.raises(InstallationLicenseError, match="Protected installation files were modified"):
        await owner_status.require_current_owner_status(license_data, redis)
