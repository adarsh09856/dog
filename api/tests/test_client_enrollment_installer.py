"""Exercise enrollment without Docker, network access or real credentials."""

import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services import installation_enrollment_cli as image_helper
from api.services.installation_identity import verify_enrollment, verify_owner_check
from api.services.installation_license import issue_license_token

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/client"))
import enroll_identity  # noqa: E402


@pytest.mark.parametrize("lost_response", [False, True])
def test_enrollment_and_existing_key_verification_without_sending_private_key(tmp_path, monkeypatch, lost_response):
    owner_key = Ed25519PrivateKey.generate()
    owner_private = owner_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    owner_public = base64.urlsafe_b64encode(owner_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    now = int(time.time())
    token = issue_license_token({
        "iat": now - 1, "exp": now + 3600, "edition": "client", "installation_id": "client-1",
        "customer_id": "buyer-1", "domains": ["customer.example"], "features": [], "limits": {},
    }, owner_private)
    status_url = "https://owner.example.test/api/v1/admin/client-installations/check"
    monkeypatch.setattr(image_helper, "trusted_license_public_keys", lambda: (owner_public,))
    monkeypatch.setattr(image_helper, "trusted_owner_status_url", lambda: status_url)
    monkeypatch.setattr(enroll_identity, "_image_helper", lambda _image, request: image_helper.execute(request))
    identity_path = tmp_path / "client.key"
    if os.name == "nt":
        group = 10003
    else:
        group = os.getgid() or 10003
    env = tmp_path / ".env"
    env.write_text(
        "CLIENT_API_IMAGE=registry.example.com/client/api@sha256:" + "a" * 64 + "\n"
        f"KODEWAVES_LICENSE_TOKEN={token}\nKODEWAVES_INSTALLATION_ID=client-1\n"
        f"PUBLIC_HOST=customer.example\nCLIENT_IDENTITY_KEY_FILE={identity_path}\nCLIENT_IDENTITY_GID={group}\n",
        encoding="utf-8",
    )
    enrollment_secret = "e" * 43
    state = {"public_key": None, "nonces": set()}

    def owner_request(url, bearer, payload):
        assert bearer == token
        assert "private_key" not in payload
        assert identity_path.read_bytes().hex() not in json.dumps(payload)
        if url.endswith("/enroll"):
            assert payload["enrollment_token"] == enrollment_secret
            verify_enrollment(
                payload["public_key"], payload["signature"], installation_id="client-1",
                license_token=token, enrollment_token=enrollment_secret,
                nonce=payload["nonce"], issued_at=payload["issued_at"],
            )
            state["public_key"] = payload["public_key"]
            if lost_response:
                raise enroll_identity.EnrollmentError("simulated lost response")
            return {"enrolled": True}
        assert url == status_url and state["public_key"]
        assert payload["nonce"] not in state["nonces"]
        state["nonces"].add(payload["nonce"])
        verify_owner_check(
            state["public_key"], payload["proof_signature"], installation_id="client-1", license_token=token,
            nonce=payload["nonce"], issued_at=payload["proof_issued_at"], integrity_ok=True,
            integrity_finding=None,
        )
        timestamp = int(time.time())
        return {"signed_status": issue_license_token({
            "kind": "installation_status", "installation_id": "client-1",
            "license_sha256": hashlib.sha256(token.encode("ascii")).hexdigest(),
            "nonce": payload["nonce"], "revoked": False, "binding_valid": True,
            "issued_at": timestamp, "expires_at": timestamp + 300,
        }, owner_private)}

    monkeypatch.setattr(enroll_identity, "_post_json", owner_request)
    enroll_identity.enroll(env, enrollment_secret)
    original = identity_path.read_bytes()
    assert len(original) == 32
    enroll_identity.enroll(env, None)
    assert identity_path.read_bytes() == original


def test_verify_only_never_creates_a_replacement_key(tmp_path):
    with pytest.raises(enroll_identity.EnrollmentError, match="missing"):
        enroll_identity._private_key(tmp_path / "missing.key", 10003, allow_create=False)
    assert not (tmp_path / "missing.key").exists()


def test_helper_uses_network_isolation_and_stdin_for_secrets(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(command=command, options=kwargs)
        return type("Result", (), {"returncode": 0, "stdout": '{"verified":true}'})()

    monkeypatch.setattr(enroll_identity.subprocess, "run", fake_run)
    secret = "test-private-seed"
    assert enroll_identity._image_helper("registry.example.com/a/b@sha256:" + "a" * 64, {"private_key": secret}) == {"verified": True}
    assert "--network=none" in captured["command"] and "--pull=never" in captured["command"]
    assert secret not in " ".join(captured["command"])
    assert json.loads(captured["options"]["input"])["private_key"] == secret


def test_owner_endpoint_must_be_pinned_https_check_url():
    with pytest.raises(enroll_identity.EnrollmentError):
        enroll_identity._enrollment_url("https://attacker.example/check?redirect=1")
    assert enroll_identity._enrollment_url(
        "https://owner.example/api/v1/admin/client-installations/check"
    ) == "https://owner.example/api/v1/admin/client-installations/enroll"
