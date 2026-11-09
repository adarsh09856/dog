"""The host updater uses the approved API image helper for signing and trust."""

from __future__ import annotations

import base64
import hashlib
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services import installation_enrollment_cli as helper
from api.services import client_update_protocol
from api.services.client_update_protocol import canonical_json, release_signature_payload, verify_update_report
from api.services.installation_identity import verify_owner_check
from api.services.installation_license import issue_license_token
from api.services.release_integrity import ReleaseIntegrityError


def _key_text(key: Ed25519PrivateKey) -> str:
    return base64.urlsafe_b64encode(key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )).rstrip(b"=").decode("ascii")


def _public_text(key: Ed25519PrivateKey) -> str:
    return base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode("ascii")


def _license(owner_key: Ed25519PrivateKey) -> str:
    now = int(time.time())
    return issue_license_token({
        "iat": now - 1,
        "exp": now + 3600,
        "edition": "client",
        "installation_id": "client-1",
        "customer_id": "buyer-1",
        "domains": ["customer.example"],
        "features": [],
        "limits": {},
    }, owner_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))


def _trust(monkeypatch, key: Ed25519PrivateKey) -> None:
    monkeypatch.setattr(helper, "trusted_license_public_keys", lambda: (_public_text(key),))
    monkeypatch.setattr(helper, "trusted_owner_status_url", lambda: "https://owner.example/api/v1/admin/client-installations/check")


def test_prepare_update_check_signs_current_version_without_returning_key(monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    identity_key = Ed25519PrivateKey.generate()
    token = _license(owner_key)
    _trust(monkeypatch, owner_key)
    monkeypatch.setattr("api.services.release_integrity.verify_configured_release", lambda: None)
    response = helper.execute({
        "action": "prepare_update_check",
        "license_token": token,
        "installation_id": "client-1",
        "public_host": "customer.example",
        "private_key": _key_text(identity_key),
        "current_version": "1.2.3",
    })
    verify_owner_check(
        _public_text(identity_key), response["signature"],
        installation_id="client-1", license_token=token,
        nonce=response["nonce"], issued_at=response["issued_at"],
        integrity_ok=True, integrity_finding=None, current_version="1.2.3",
    )
    assert response["current_version"] == "1.2.3"
    assert response["integrity_ok"] is True
    assert response["integrity_finding"] is None
    assert response["owner_status_url"].endswith("/client-installations/check")
    assert "private_key" not in response
    assert token not in str(response)


def test_prepare_update_check_signs_integrity_failure_from_installed_manifest(monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    identity_key = Ed25519PrivateKey.generate()
    token = _license(owner_key)
    _trust(monkeypatch, owner_key)
    monkeypatch.setenv("KODEWAVES_EDITION", "client")

    def modified_release():
        raise ReleaseIntegrityError(
            "Client release file changed", reason="modified_file", component="api/app.py",
            expected_sha256="a" * 64, observed_sha256="b" * 64,
        )

    monkeypatch.setattr("api.services.release_integrity.verify_configured_release", modified_release)
    response = helper.execute({
        "action": "prepare_update_check",
        "license_token": token,
        "installation_id": "client-1",
        "public_host": "customer.example",
        "private_key": _key_text(identity_key),
        "current_version": "1.2.3",
    })

    assert response["integrity_ok"] is False
    assert response["integrity_finding"] == {
        "reason": "modified_file",
        "component": "api/app.py",
        "expected_sha256": "a" * 64,
        "observed_sha256": "b" * 64,
    }
    verify_owner_check(
        _public_text(identity_key), response["signature"],
        installation_id="client-1", license_token=token,
        nonce=response["nonce"], issued_at=response["issued_at"],
        integrity_ok=False, integrity_finding=response["integrity_finding"],
        current_version="1.2.3",
    )


def test_verify_status_returns_only_owner_verified_claims(monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    release_key = Ed25519PrivateKey.generate()
    token = _license(owner_key)
    _trust(monkeypatch, owner_key)
    monkeypatch.setattr(client_update_protocol, "trusted_release_public_key", lambda: _public_text(release_key))
    nonce = "n" * 43
    now = int(time.time())
    envelope = {
        "release_id": "release-1",
        "version": "1.3.0",
        "archive_url": "https://releases.example/customer.tar.gz",
        "archive_sha256": "a" * 64,
        "min_current_version": "1.2.0",
        "notes": "update",
    }
    signature = release_key.sign(canonical_json(release_signature_payload(**envelope)))
    envelope["archive_signature"] = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    status = {
        "kind": "installation_status",
        "installation_id": "client-1",
        "license_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
        "nonce": nonce,
        "revoked": False,
        "binding_valid": True,
        "issued_at": now,
        "expires_at": now + 240,
        "update": {
            **envelope,
            "rollout_id": "13dbb634-9dc2-4a59-a3d8-44ff5c03a1c2",
            "target_status": "applying",
            "rollout_state": "active",
        },
    }
    signed = issue_license_token(status, owner_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ))
    verified = helper.execute({
        "action": "verify_status",
        "license_token": token,
        "installation_id": "client-1",
        "public_host": "customer.example",
        "nonce": nonce,
        "signed_status": signed,
    })
    assert verified["verified"] is True
    assert verified["status"]["update"] == status["update"]


def test_prepare_update_report_signs_domain_separated_claims(monkeypatch):
    owner_key = Ed25519PrivateKey.generate()
    identity_key = Ed25519PrivateKey.generate()
    token = _license(owner_key)
    _trust(monkeypatch, owner_key)
    now = int(time.time())
    fields = {
        "rollout_id": "13dbb634-9dc2-4a59-a3d8-44ff5c03a1c2",
        "release_id": "release-1",
        "version": "1.3.0",
        "nonce": "r" * 43,
        "issued_at": now,
        "status": "downloading",
        "detail": "",
    }
    response = helper.execute({
        "action": "prepare_update_report",
        "license_token": token,
        "installation_id": "client-1",
        "public_host": "customer.example",
        "private_key": _key_text(identity_key),
        **fields,
    })
    verify_update_report(
        _public_text(identity_key), response["proof_signature"],
        installation_id="client-1", license_token=token, **fields,
    )
    assert set(response) == {"proof_signature"}
    assert "private_key" not in str(response)
    assert token not in str(response)

    rollback_fields = {
        **fields,
        "status": "rolled_back",
        "installed_version": "1.2.0",
    }
    rollback_response = helper.execute({
        "action": "prepare_update_report",
        "license_token": token,
        "installation_id": "client-1",
        "public_host": "customer.example",
        "private_key": _key_text(identity_key),
        **rollback_fields,
    })
    verify_update_report(
        _public_text(identity_key), rollback_response["proof_signature"],
        installation_id="client-1", license_token=token, **rollback_fields,
    )
