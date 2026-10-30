"""Focused contract tests for the internal owner license signer."""

import base64
import hashlib
import time

from fastapi.testclient import TestClient

from api.services.installation_license import issue_license_token, verify_installation_status
from api.services.owner_license_signer import app


def _configure_signer(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    path = tmp_path / "current.key"
    path.write_bytes(base64.urlsafe_b64encode(raw).rstrip(b"="))
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(path))
    monkeypatch.setenv("KODEWAVES_OWNER_LEGACY_LICENSE_SIGNING_KEY_FILES", "")
    monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "t" * 48)
    return raw


def test_signer_requires_api_authentication_and_only_returns_public_keys(monkeypatch, tmp_path):
    _configure_signer(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/v1/public-keys").status_code == 401
        result = client.get(
            "/v1/public-keys", headers={"Authorization": "Bearer " + "t" * 48}
        )
        assert result.status_code == 200
        assert len(result.json()["public_keys"]) == 1
        assert "private" not in result.text.lower()


def test_signer_health_requires_token_and_readable_signing_keys(monkeypatch, tmp_path):
    _configure_signer(monkeypatch, tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "short")
        assert client.get("/health").status_code == 503
        monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNER_TOKEN", "t" * 48)
        monkeypatch.setenv("KODEWAVES_OWNER_LICENSE_SIGNING_KEY_FILE", str(tmp_path / "missing.key"))
        assert client.get("/health").status_code == 503


def test_signer_issues_license_and_binds_status_to_original_license(monkeypatch, tmp_path):
    _configure_signer(monkeypatch, tmp_path)
    now = int(time.time())
    claims = {
        "iat": now - 1, "exp": now + 3600, "edition": "client",
        "installation_id": "client-test", "customer_id": "buyer-test",
        "domains": ["example.com"], "features": [], "limits": {},
    }
    headers = {"Authorization": "Bearer " + "t" * 48}
    with TestClient(app) as client:
        unauthorized = client.post("/v1/sign-license", json={"claims": claims})
        assert unauthorized.status_code == 401
        issued = client.post("/v1/sign-license", json={"claims": claims}, headers=headers)
        assert issued.status_code == 200
        payload = issued.json()
        token = payload["token"]
        assert payload["public_key"]
        assert "private" not in issued.text.lower()

        for invalid_domains in ([], ["*.example.com"], [""]):
            invalid = client.post(
                "/v1/sign-license",
                json={"claims": {**claims, "domains": invalid_domains}},
                headers=headers,
            )
            assert invalid.status_code == 422
        invalid_feature = client.post(
            "/v1/sign-license",
            json={"claims": {**claims, "features": ["owner_admin"]}},
            headers=headers,
        )
        assert invalid_feature.status_code == 422

        nonce = "nonce-test-" + "x" * 32
        status_claims = {
            "kind": "installation_status", "installation_id": "client-test",
            "license_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
            "nonce": nonce, "revoked": False, "binding_valid": True,
            "observed_ip": "203.0.113.1", "issued_at": now,
            "expires_at": now + 300,
        }
        signed = client.post(
            "/v1/sign-status",
            json={"claims": status_claims, "license_token": token},
            headers=headers,
        )
        assert signed.status_code == 200
        assert verify_installation_status(
            signed.json()["signed_status"], public_key=payload["public_key"],
            installation_id="client-test", license_token=token, nonce=nonce,
            now=now + 1,
        ) is False

        changed = {**status_claims, "installation_id": "another-client"}
        rejected = client.post(
            "/v1/sign-status",
            json={"claims": changed, "license_token": token},
            headers=headers,
        )
        assert rejected.status_code == 422
