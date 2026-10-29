import asyncio
import base64
import hashlib
import json
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from pydantic import ValidationError

from api.services.installation_license import (
    InstallationLicenseError,
    issue_license_token,
    load_license,
    require_feature,
    require_limit,
    validate_installation_license,
    validate_request_binding,
    verify_installation_status,
)


def _key_material():
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    return private_bytes, public_key


def _claims(**overrides):
    claims = {
        "iat": 100,
        "exp": 4_102_444_800,
        "installation_id": "install-123",
        "customer_id": "customer-456",
        "edition": "client",
        "domains": ["EXAMPLE.com."],
        "features": ["voice", "crm"],
        "limits": {"max_concurrent_calls": 4},
        "ip_ranges": ["203.0.113.0/24"],
    }
    claims.update(overrides)
    return claims


def test_client_branding_rejects_unsafe_color_and_logo_url():
    from api.routes.installation import ClientBranding

    for field, value in (
        ("primary_color", "red; background:url(evil)"),
        ("logo_url", "javascript:alert(1)"),
        ("logo_url", "//untrusted.example/logo.svg"),
        ("favicon_url", "javascript:alert(1)"),
        ("support_email", "support@example.com\r\nInjected: bad"),
        ("company_name", "   "),
    ):
        with pytest.raises(ValidationError):
            ClientBranding.model_validate({field: value})

    accepted = ClientBranding.model_validate({"company_name": " Client ", "primary_color": "#AABBCC"})
    assert accepted.company_name == "Client"
    assert accepted.primary_color == "#aabbcc"


@pytest.mark.asyncio
@pytest.mark.parametrize("edition,key", [("client", "client_branding"), ("saas", "branding")])
async def test_client_branding_can_change_without_editing_license(monkeypatch, edition, key):
    from api.routes import installation

    monkeypatch.setattr(installation, "KODEWAVES_EDITION", edition)
    saved = {}

    async def set_setting(key, value, *, category):
        saved[key] = (value, category)

    async def get_setting(key, *, raise_on_error=False):
        return saved.get(key, ({}, ""))[0]

    monkeypatch.setattr(installation.kodewaves_db_client, "set_setting", set_setting)
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", get_setting)
    branding = installation.ClientBranding(company_name="Client Voice", primary_color="#224466")
    await installation.update_client_branding(branding, SimpleNamespace(is_superuser=True))
    assert (await installation.get_client_branding()).company_name == "Client Voice"
    assert saved[key][1] == key
    assert "KODEWAVES_LICENSE_TOKEN" not in saved


@pytest.mark.asyncio
async def test_hosted_public_branding_uses_admin_record_without_exposing_secrets(monkeypatch):
    from unittest.mock import AsyncMock

    from api.routes import installation

    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "saas")
    getter = AsyncMock(return_value={
        "company_name": "Customer Brand", "tagline": "Customer conversations",
        "primary_color": "#123456", "support_email": "help@example.com",
        "smtp_password": "must-not-be-public",
    })
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", getter)
    result = await installation.get_client_branding()
    getter.assert_awaited_once_with("branding", raise_on_error=True)
    assert result.company_name == "Customer Brand"
    assert result.support_email == "help@example.com"
    assert "smtp_password" not in result.model_dump()


@pytest.mark.asyncio
async def test_admin_branding_rejects_invalid_values_before_writes(monkeypatch):
    from unittest.mock import AsyncMock

    from api.routes.admin import settings

    writer = AsyncMock()
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(settings.kodewaves_db_client, "set_setting", writer)
    with pytest.raises(HTTPException) as error:
        await settings.update_platform_settings({"company_name": "Customer", "primary_color": "not-a-color"}, SimpleNamespace(id=1))
    assert error.value.status_code == 422
    writer.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_branding_patch_preserves_other_platform_settings(monkeypatch):
    from unittest.mock import AsyncMock

    from api.routes.admin import settings

    writer = AsyncMock()
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(settings.kodewaves_db_client, "set_setting", writer)
    monkeypatch.setattr(settings.kodewaves_db_client, "record_audit_log", AsyncMock())
    monkeypatch.setattr(settings.catalog_service, "notify_changed", AsyncMock())

    await settings.update_platform_settings(
        {"company_name": "Customer Brand"}, SimpleNamespace(id=1, email="owner@example.com")
    )

    assert writer.await_count == 1
    assert writer.await_args.kwargs["key"] == "branding"
    assert writer.await_args.kwargs["value"]["company_name"] == "Customer Brand"


@pytest.mark.asyncio
async def test_admin_partial_payment_and_smtp_updates_preserve_secrets(monkeypatch):
    from unittest.mock import AsyncMock

    from api.routes.admin import settings

    stored = {
        "payments": {"razorpay_key_secret": "keep-razorpay", "stripe_secret_key": "keep-stripe"},
        "smtp": {"smtp_password": "keep-smtp", "smtp_host": "mail.example.com"},
    }
    writer = AsyncMock()
    monkeypatch.setattr(settings.kodewaves_db_client, "get_setting", AsyncMock(side_effect=lambda key: stored.get(key, {})))
    monkeypatch.setattr(settings.kodewaves_db_client, "set_setting", writer)
    monkeypatch.setattr(settings.kodewaves_db_client, "record_audit_log", AsyncMock())
    monkeypatch.setattr(settings.catalog_service, "notify_changed", AsyncMock())
    admin = SimpleNamespace(id=1, email="owner@example.com")

    await settings.update_platform_settings({"stripe_publishable_key": "pk_new"}, admin)
    assert writer.await_args.kwargs["key"] == "payments"
    assert writer.await_args.kwargs["value"] == {
        "razorpay_key_secret": "keep-razorpay", "stripe_secret_key": "keep-stripe",
        "stripe_publishable_key": "pk_new",
    }

    writer.reset_mock()
    await settings.update_platform_settings({"smtp_from": "team@example.com"}, admin)
    assert writer.await_count == 1
    assert writer.await_args.kwargs["key"] == "smtp"
    assert writer.await_args.kwargs["value"]["smtp_password"] == "keep-smtp"


@pytest.mark.asyncio
async def test_admin_settings_does_not_return_defaults_after_database_failure(monkeypatch):
    from unittest.mock import AsyncMock

    from sqlalchemy.exc import SQLAlchemyError

    from api.routes.admin import settings

    monkeypatch.setattr(settings.kodewaves_db_client, "get_settings_map", AsyncMock(side_effect=SQLAlchemyError("unavailable")))
    with pytest.raises(HTTPException) as error:
        await settings.get_all_platform_settings(SimpleNamespace(id=1))
    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_client_license_status_requires_client_administrator(monkeypatch):
    from api.routes import installation

    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    with pytest.raises(HTTPException) as denied:
        await installation.installation_license_status(SimpleNamespace(is_superuser=False))
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_client_license_status_reports_owner_grace_and_last_check(monkeypatch):
    from api.routes import installation
    from api.services.installation_license import InstallationLicense
    from api.services.owner_installation_status import OwnerStatusSnapshot

    async def owner_snapshot(_license):
        return OwnerStatusSnapshot(last_owner_check=12345, using_outage_grace=True)

    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "client-1")
    monkeypatch.setattr(installation, "load_license", lambda: InstallationLicense(
        "client-1", "buyer-1", "client", ("example.com",), 99999,
        frozenset({"voice"}), {"max_concurrent_calls": 2},
    ))
    monkeypatch.setattr(installation, "get_installation_binding", lambda: "example.com")
    monkeypatch.setattr(installation, "require_current_owner_status", owner_snapshot)

    result = await installation.installation_license_status(SimpleNamespace(is_superuser=True))
    assert result["valid"] is True
    assert result["owner_status"] == "outage_grace"
    assert result["last_owner_check"] == 12345

    async def owner_revoked(_license):
        raise InstallationLicenseError("Installation license was revoked by the owner")

    monkeypatch.setattr(installation, "require_current_owner_status", owner_revoked)
    revoked = await installation.installation_license_status(SimpleNamespace(is_superuser=True))
    assert revoked["valid"] is False
    assert revoked["installation_id"] == "client-1"
    assert revoked["domains"] == ["example.com"]
    assert "revoked" in revoked["message"]


def test_signed_license_is_canonical_and_domain_and_ip_bound():
    private_key, public_key = _key_material()
    token = issue_license_token(_claims(), private_key)

    license_data = load_license(token, public_key, now=150)
    assert license_data.domains == ("example.com",)
    assert license_data.features == {"voice", "crm"}
    assert license_data.limits == {"max_concurrent_calls": 4}
    assert require_limit(license_data, "max_concurrent_calls") == 4
    validate_request_binding(
        license_data,
        hostname="example.com",
        installation_ip="203.0.113.27",
    )


@pytest.mark.parametrize("installation_ip", ["198.51.100.9", None, "not-an-ip"])
def test_signed_license_rejects_missing_or_out_of_range_installation_ip(installation_ip):
    private_key, public_key = _key_material()
    license_data = load_license(issue_license_token(_claims(), private_key), public_key, now=150)

    with pytest.raises(InstallationLicenseError, match="IP"):
        validate_request_binding(
            license_data,
            hostname="example.com",
            installation_ip=installation_ip,
        )


def test_client_image_trust_key_cannot_be_replaced_by_environment(monkeypatch, tmp_path):
    from api.services import owner_installation_status, owner_trust

    owner_private, owner_public = _key_material()
    forged_private, forged_public = _key_material()
    trust_file = tmp_path / "owner_public_keys.json"
    trust_file.write_text(json.dumps({
        "license": owner_public, "release": owner_public,
        "owner_status_url": "https://owner.example.com/check",
    }), encoding="ascii")
    monkeypatch.setattr(owner_trust, "TRUST_FILE", trust_file)
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", forged_public)
    monkeypatch.setenv("KODEWAVES_OWNER_STATUS_URL", "https://attacker.example/check")

    approved = issue_license_token(_claims(), owner_private)
    forged = issue_license_token(_claims(), forged_private)
    assert load_license(approved, now=150).installation_id == "install-123"
    with pytest.raises(InstallationLicenseError, match="signature"):
        load_license(forged, now=150)
    assert owner_installation_status._status_url() == "https://owner.example.com/check"


def test_client_image_accepts_baked_previous_owner_key_during_rotation(monkeypatch, tmp_path):
    from api.services import owner_trust

    previous_private, previous_public = _key_material()
    _new_private, new_public = _key_material()
    trust_file = tmp_path / "owner_public_keys.json"
    trust_file.write_text(json.dumps({
        "license": new_public,
        "license_previous": previous_public,
        "release": new_public,
        "owner_status_url": "https://owner.example.com/check",
    }), encoding="ascii")
    monkeypatch.setattr(owner_trust, "TRUST_FILE", trust_file)
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    old_token = issue_license_token(_claims(), previous_private)
    assert load_license(old_token, now=150).installation_id == "install-123"
    signed_status = issue_license_token({
        "kind": "installation_status",
        "installation_id": "install-123",
        "license_sha256": hashlib.sha256(old_token.encode("ascii")).hexdigest(),
        "nonce": "nonce-123",
        "revoked": False,
        "issued_at": 150,
        "expires_at": 300,
    }, previous_private)
    assert verify_installation_status(
        signed_status,
        public_key=owner_trust.trusted_license_public_keys(),
        installation_id="install-123", license_token=old_token,
        nonce="nonce-123", now=151,
    ) is False


@pytest.mark.parametrize("suffix", ["==", "!", " "])
def test_client_image_rejects_noncanonical_baked_owner_keys(monkeypatch, tmp_path, suffix):
    from api.services import owner_trust

    _private, valid_public = _key_material()
    trust_file = tmp_path / "owner_public_keys.json"
    trust_file.write_text(json.dumps({
        "license": valid_public + suffix,
        "release": valid_public,
        "owner_status_url": "https://owner.example.com/check",
    }), encoding="ascii")
    monkeypatch.setattr(owner_trust, "TRUST_FILE", trust_file)

    with pytest.raises(owner_trust.OwnerTrustError, match="owner trust keys"):
        owner_trust.trusted_license_public_key()


def test_client_image_rejects_noncanonical_previous_owner_key(monkeypatch, tmp_path):
    from api.services import owner_trust

    _private, valid_public = _key_material()
    trust_file = tmp_path / "owner_public_keys.json"
    trust_file.write_text(json.dumps({
        "license": valid_public,
        "license_previous": valid_public + "==",
        "release": valid_public,
        "owner_status_url": "https://owner.example.com/check",
    }), encoding="ascii")
    monkeypatch.setattr(owner_trust, "TRUST_FILE", trust_file)

    with pytest.raises(owner_trust.OwnerTrustError, match="invalid owner trust keys"):
        owner_trust.trusted_license_public_keys()


def test_expired_or_tampered_license_is_rejected():
    private_key, public_key = _key_material()
    expired = issue_license_token(_claims(exp=199), private_key)
    try:
        load_license(expired, public_key, now=200)
    except InstallationLicenseError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("expired license was accepted")

    pieces = expired.split(".")
    changed_payload = json.loads(base64.urlsafe_b64decode(pieces[0] + "=="))
    changed_payload["customer_id"] = "different-customer"
    altered = base64.urlsafe_b64encode(
        json.dumps(changed_payload, sort_keys=True, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    try:
        load_license(f"{altered}.{pieces[1]}", public_key, now=150)
    except InstallationLicenseError as exc:
        assert "signature" in str(exc)
    else:
        raise AssertionError("tampered license was accepted")


def test_license_rejects_noncanonical_base64_token_and_public_key_encodings():
    private_key, public_key = _key_material()
    token = issue_license_token(_claims(), private_key)
    payload, signature = token.split(".")

    for malformed in (f"{payload}!.{signature}", f"{payload}.{signature}!", f"{payload}.{signature}==="):
        with pytest.raises(InstallationLicenseError, match="signature"):
            load_license(malformed, public_key, now=150)

    with pytest.raises(InstallationLicenseError, match="signature"):
        load_license(token, public_key + "!", now=150)
    with pytest.raises(InstallationLicenseError, match="signature"):
        load_license(token, public_key + "==", now=150)
    with pytest.raises(InstallationLicenseError, match="signature"):
        load_license(f"{payload}.{signature}=", public_key, now=150)


def test_wrong_domain_and_ip_are_rejected():
    private_key, public_key = _key_material()
    license_data = load_license(issue_license_token(_claims(), private_key), public_key, now=150)
    for host, address, expected in (
        ("other.example", "203.0.113.27", "domain"),
        ("example.com", "198.51.100.1", "IP address"),
    ):
        try:
            validate_request_binding(
                license_data,
                hostname=host,
                installation_ip=address,
            )
        except InstallationLicenseError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"unexpectedly accepted {host} / {address}")


@pytest.mark.parametrize("domain", ["example.com:443", "bad_domain.example", "-bad.example", "example..com"])
def test_license_rejects_malformed_domain(domain):
    private_key, public_key = _key_material()
    with pytest.raises(InstallationLicenseError, match="invalid domain"):
        load_license(issue_license_token(_claims(domains=[domain]), private_key), public_key, now=150)


def test_installation_id_and_domain_match_and_server_ip_is_not_trusted(monkeypatch):
    from api.services import installation_license

    private_key, public_key = _key_material()
    license_data = load_license(issue_license_token(_claims(), private_key), public_key, now=150)
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "install-123")
    monkeypatch.setattr(
        installation_license,
        "get_installation_binding",
        lambda: "example.com",
    )
    validate_installation_license(license_data)
    require_feature(license_data, "voice")

    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "another-install")
    try:
        validate_installation_license(license_data)
    except InstallationLicenseError as exc:
        assert "different installation" in str(exc)
    else:
        raise AssertionError("a license copied to a different installation ID was accepted")

    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "install-123")
    monkeypatch.setattr(
        installation_license,
        "get_installation_binding",
        lambda: "example.com",
    )
    # SERVER_IP is installation-controlled and cannot prove the source IP.
    validate_installation_license(license_data)

    try:
        require_feature(license_data, "campaigns")
    except InstallationLicenseError as exc:
        assert "campaigns" in str(exc)
    else:
        raise AssertionError("an unlicensed feature was accepted")


def test_call_admission_reads_signed_features_and_limit(monkeypatch):
    from api.services import installation_license
    from api.services.call_concurrency import service as concurrency_service

    private_key, public_key = _key_material()
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "install-123")
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", issue_license_token(_claims(), private_key))
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public_key)
    monkeypatch.setattr(installation_license, "get_installation_binding", lambda: "example.com")
    monkeypatch.setattr(concurrency_service, "KODEWAVES_EDITION", "client")

    assert concurrency_service._licensed_call_limit("webrtc") == 4
    for source in ("campaign:42", "ari_inbound", "public_agent", "agent_stream:cloudonix"):
        try:
            concurrency_service._licensed_call_limit(source)
        except InstallationLicenseError:
            pass
        else:
            raise AssertionError(f"unlicensed call source was accepted: {source}")

    monkeypatch.setenv(
        "KODEWAVES_LICENSE_TOKEN",
        issue_license_token(_claims(features=["voice", "telephony"], ip_ranges=[]), private_key),
    )
    assert concurrency_service._licensed_call_limit("agent_stream:cloudonix") == 4


def test_client_http_and_websocket_requests_are_gated(monkeypatch):
    from api.services import client_license_middleware as middleware
    from api.services import installation_license

    private_key, public_key = _key_material()
    monkeypatch.setattr(middleware, "KODEWAVES_EDITION", "client")
    owner_access = {"allowed": True, "failure": "Installation license was revoked by the owner"}
    async def owner_status_ok(_license):
        if not owner_access["allowed"]:
            raise InstallationLicenseError(owner_access["failure"])
    monkeypatch.setattr(middleware, "require_current_owner_status", owner_status_ok)
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", issue_license_token(_claims(ip_ranges=[]), private_key))
    monkeypatch.setenv("KODEWAVES_LICENSE_PUBLIC_KEY", public_key)
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "install-123")
    configured_binding = {"hostname": "example.com"}
    monkeypatch.setattr(
        installation_license,
        "get_installation_binding",
        lambda: configured_binding["hostname"],
    )

    async def run(scope):
        called = False
        messages = []

        async def app(_scope, _receive, _send):
            nonlocal called
            called = True

        async def send(message):
            messages.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await middleware.ClientLicenseMiddleware(app)(scope, receive, send)
        return called, messages

    base = {
        "type": "http",
        "path": "/api/v1/agents",
        "headers": [(b"host", b"example.com")],
        "client": ("203.0.113.27", 1234),
    }
    passed, _ = asyncio.run(run(base))
    assert passed

    # Core identity/context and the API-to-UI proxy are license-bound, but do
    # not require a product grant because every enabled workspace needs them.
    core_paths = (
        "/api/v1/user/auth/user",
        "/api/v1/organizations/context",
        "/user/auth/user",
        "/organizations/context",
        "/api/auth/session",
    )
    monkeypatch.setenv(
        "KODEWAVES_LICENSE_TOKEN",
        issue_license_token(_claims(features=[], ip_ranges=[]), private_key),
    )
    for path in core_paths:
        passed, _ = asyncio.run(run(dict(base, path=path)))
        assert passed, f"Core endpoint should work on a valid license: {path}"

    monkeypatch.delenv("KODEWAVES_LICENSE_TOKEN")
    for path in core_paths:
        passed, messages = asyncio.run(run(dict(base, path=path)))
        assert not passed, f"Core endpoint must still require a license: {path}"
        assert messages[0]["status"] == 402
    monkeypatch.setenv(
        "KODEWAVES_LICENSE_TOKEN",
        issue_license_token(_claims(ip_ranges=[]), private_key),
    )

    owner_access["allowed"] = False
    passed, messages = asyncio.run(run(base))
    assert not passed
    assert messages[0]["status"] == 402
    passed, messages = asyncio.run(run(dict(base, type="websocket", path="/api/v1/ws/signaling/21/run")))
    assert not passed
    assert messages[0]["code"] == 4403
    owner_access["allowed"] = True

    owner_access["allowed"] = False
    owner_access["failure"] = "Protected installation files were modified"
    passed, messages = asyncio.run(run(base))
    assert not passed
    assert messages[0]["status"] == 402
    assert json.loads(messages[-1]["body"])["detail"] == "Protected installation files were modified"
    owner_access["allowed"] = True

    # The request authority must be bound even if the operator-controlled
    # PUBLIC_HOST still points at a licensed domain.
    configured_binding["hostname"] = "example.com"
    bad_domain = dict(base, headers=[(b"host", b"attacker.example")])
    passed, messages = asyncio.run(run(bad_domain))
    assert not passed
    assert messages[0]["status"] == 402

    # Ports are valid in Host but are not part of the signed domain claim.
    passed, _ = asyncio.run(run(dict(base, headers=[(b"host", b"example.com:8443")])))
    assert passed
    for headers in (
        [],
        [(b"host", b"example.com"), (b"host", b"example.com")],
        [(b"host", b"example.com:bad")],
        [(b"host", b"example.com:")],
    ):
        passed, messages = asyncio.run(run(dict(base, headers=headers)))
        assert not passed
        assert messages[0]["status"] == 402

    passed, messages = asyncio.run(
        run(dict(base, type="websocket", headers=[(b"host", b"attacker.example")]))
    )
    assert not passed
    assert messages[0]["code"] == 4403

    configured_binding["hostname"] = "example.com"
    unlicensed_feature = dict(base, path="/api/v1/campaign/start")
    passed, messages = asyncio.run(run(unlicensed_feature))
    assert not passed
    assert messages[0]["status"] == 403

    assert middleware.required_feature_for_path("/api/v1/workflow/21") == "voice"
    assert middleware.required_feature_for_path("/api/v1/workflow/21/embed-token") == "widgets"
    assert middleware.required_feature_for_path("/api/v1/ws/public/signaling/session") == "widgets"
    assert middleware.required_feature_for_path("/api/v1/workflow-recordings/21") == "voice"
    assert middleware.required_feature_for_path("/api/v1/tts-cache/item") == "voice"
    assert middleware.required_feature_for_path("/api/v1/public/agent/call") == "telephony"
    assert middleware.required_feature_for_path("/api/v1/user/api-keys") == "voice"
    assert middleware.required_feature_for_path("/api/v1/user/api-keys/17/reactivate") == "voice"
    assert middleware.required_feature_for_path("/api/v1/mcp/tools/list") == "voice"
    assert middleware.required_feature_for_path("/api/v1/organizations/telephony-configs/1") == "telephony"
    assert middleware.required_feature_for_path("/api/v1/organizations/overview/stats") == "voice"
    assert middleware.required_feature_for_path("/api/v1/organizations/preferences") == "voice"
    assert middleware.required_feature_for_path("/api/v1/agent-stream/cloudonix/workflow-id") == "telephony"
    assert middleware.required_feature_for_path("/api/v1/organizations/campaign-defaults") == "campaigns"
    assert middleware.required_feature_for_path("/api/v1/campaign/start") == "campaigns"
    assert middleware.required_feature_for_path("/api/v1/s3/presigned-upload-url") == "campaigns"
    assert middleware.required_feature_for_path("/api/v1/campaigner") is None
    for route in (
        "/api/v1/catalog/available",
        "/api/v1/credentials/",
        "/api/v1/folder/",
        "/api/v1/node-types",
        "/api/v1/prompt-templates",
        "/api/v1/tools/",
        "/api/v1/turn/credentials",
        "/api/v1/organizations/usage/runs",
        "/api/v1/user/onboarding-state",
    ):
        assert middleware.required_feature_for_path(route) == "voice"
    assert middleware.required_feature_for_request(
        "/api/v1/s3/signed-url", b"key=campaigns%2F2%2Fcontacts.csv"
    ) == "campaigns"
    assert middleware.required_feature_for_request(
        "/api/v1/s3/signed-url", b"key=knowledge_base%2F2%2Fmanual.pdf"
    ) == "knowledge_base"
    assert middleware.required_feature_for_request(
        "/api/v1/s3/signed-url", b"key=recordings%2F22.wav"
    ) == "voice"
    for path in ("/api/v1/s3/signed-url", "/api/v1/s3/file-metadata"):
        passed, messages = asyncio.run(run(dict(
            base, path=path,
            query_string=b"key=recordings%2F22.wav&key=campaigns%2F2%2Fcontacts.csv",
        )))
        assert not passed
        assert messages[0]["status"] == 402

    for widget_path in ("/api/v1/workflow/21/embed-token", "/api/v1/ws/public/signaling/session"):
        scope = dict(base, path=widget_path, type="websocket" if "/ws/" in widget_path else "http")
        passed, messages = asyncio.run(run(scope))
        assert not passed
        assert messages[0]["code" if scope["type"] == "websocket" else "status"] == (
            4403 if scope["type"] == "websocket" else 403
        )

    # Inbound telephony agent streams cannot be opened with only a voice grant.
    passed, messages = asyncio.run(
        run(dict(base, path="/api/v1/agent-stream/cloudonix/workflow-id", type="websocket"))
    )
    assert not passed
    assert messages[0]["code"] == 4403

    passed, messages = asyncio.run(run(dict(base, path="/api/v1/s3/presigned-upload-url")))
    assert not passed
    assert messages[0]["status"] == 403

    # Resource routes must deny a product whose grant is absent, including
    # storage URLs whose required grant depends on the object namespace.
    monkeypatch.setenv(
        "KODEWAVES_LICENSE_TOKEN",
        issue_license_token(_claims(features=["crm"], ip_ranges=[]), private_key),
    )
    for scope in (
        dict(base, path="/api/v1/tools/"),
        dict(
            base,
            path="/api/v1/s3/signed-url",
            query_string=b"key=campaigns%2F2%2Fcontacts.csv",
        ),
        dict(
            base,
            path="/api/v1/s3/signed-url",
            query_string=b"key=knowledge_base%2F2%2Fmanual.pdf",
        ),
        dict(
            base,
            path="/api/v1/s3/signed-url",
            query_string=b"key=recordings%2F22.wav",
        ),
    ):
        passed, messages = asyncio.run(run(scope))
        assert not passed
        assert messages[0]["status"] == 403

    websocket = dict(base, type="websocket")
    monkeypatch.delenv("KODEWAVES_LICENSE_TOKEN")
    passed, messages = asyncio.run(run(websocket))
    assert not passed
    assert messages[0]["code"] == 4403


def test_openapi_data_routes_are_feature_mapped_or_explicitly_core():
    """New API endpoints must not silently escape client feature entitlements."""
    from api.app import app
    from api.services.client_license_middleware import (
        is_owner_control_path,
        required_feature_for_request,
    )

    core_paths = {
        # Identity and tenant context are required by every licensed workspace.
        "/user/auth/user",
        "/organizations/context",
    }
    public_control_paths = {
        "/",
        "/health",
        "/health/active-calls",
        "/health/autoscale-metric",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
    unclassified = []
    schema_paths = app.openapi()["paths"]
    assert "/api/{path}" not in schema_paths
    for path in schema_paths:
        normalized = path.removeprefix("/api/v1") or "/"
        if (
            is_owner_control_path(normalized)
            or normalized in public_control_paths
            or normalized.startswith(("/auth/", "/installation/"))
            or normalized in core_paths
        ):
            continue
        if required_feature_for_request(path) is None:
            unclassified.append(path)

    assert not unclassified, f"API routes missing client feature classification: {unclassified}"


def test_status_and_health_paths_remain_available_without_license(monkeypatch):
    from api.services import client_license_middleware as middleware

    monkeypatch.setattr(middleware, "KODEWAVES_EDITION", "client")
    monkeypatch.delenv("KODEWAVES_LICENSE_TOKEN", raising=False)
    monkeypatch.delenv("KODEWAVES_LICENSE_PUBLIC_KEY", raising=False)

    async def run(path):
        called = False

        async def app(_scope, _receive, _send):
            nonlocal called
            called = True

        await middleware.ClientLicenseMiddleware(app)(
            {"type": "http", "path": path, "headers": [], "client": ("127.0.0.1", 1)},
            lambda: None,
            lambda _message: None,
        )
        return called

    assert asyncio.run(run("/api/v1/health"))
    assert asyncio.run(run("/api/v1/installation/license"))


def test_client_middleware_hides_owner_control_routes_even_if_mounted(monkeypatch):
    from api.services import client_license_middleware as middleware

    monkeypatch.setattr(middleware, "KODEWAVES_EDITION", "client")

    async def run(path, scope_type="http"):
        called = False
        messages = []

        async def app(_scope, _receive, _send):
            nonlocal called
            called = True

        async def send(message):
            messages.append(message)

        await middleware.ClientLicenseMiddleware(app)(
            {"type": scope_type, "path": path, "headers": []},
            lambda: None,
            send,
        )
        return called, messages

    for path in (
        "/admin/client-installations",
        "/api/v1/admin/client-installations",
        "/superuser/impersonate",
        "/api/v1/superuser/impersonate",
    ):
        called, messages = asyncio.run(run(path))
        assert not called
        assert messages[0]["status"] == 404

    called, messages = asyncio.run(run("/api/v1/admin/client-installations", "websocket"))
    assert not called
    assert messages[0]["code"] == 4404


def test_only_post_binding_request_bypasses_a_stale_client_license(monkeypatch):
    from api.services import client_license_middleware as middleware

    monkeypatch.setattr(middleware, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        middleware, "load_license",
        lambda: (_ for _ in ()).throw(InstallationLicenseError("license unavailable")),
    )

    async def run(method):
        called = False
        messages = []

        async def app(_scope, _receive, _send):
            nonlocal called
            called = True

        async def send(message):
            messages.append(message)

        await middleware.ClientLicenseMiddleware(app)(
            {
                "type": "http",
                "method": method,
                "path": "/api/v1/installation/binding-requests",
                "headers": [(b"host", b"customer.example")],
                "client": ("198.51.100.2", 1234),
            },
            lambda: None,
            send,
        )
        return called, messages

    called, messages = asyncio.run(run("POST"))
    assert called
    assert messages == []
    called, messages = asyncio.run(run("GET"))
    assert not called
    assert messages[0]["status"] == 402
