"""Installation proof format must agree across API and UI runtimes."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services.installation_identity import (
    InstallationIdentityError,
    owner_check_message,
    owner_check_payload,
    sign_binding_request,
    sign_enrollment,
    sign_owner_check,
    verify_enrollment,
    verify_owner_check,
    verify_binding_request,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def identity():
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    fields = {
        "installation_id": "customer-install-1", "license_token": "license.payload-signature",
        "nonce": "n" * 43, "issued_at": 1_800_000_000,
        "integrity_ok": False,
        "integrity_finding": {"reason": "modified_file", "component": "ui/server.js"},
    }
    return private, public, fields


def test_proof_binds_license_identity_nonce_and_integrity_finding(identity):
    private, public, fields = identity
    signature = sign_owner_check(private, **fields)
    verify_owner_check(public, signature, now=fields["issued_at"], **fields)
    for change in (
        {"license_token": "another-license"}, {"installation_id": "other-install"},
        {"nonce": "x" * 43}, {"integrity_finding": {"reason": "modified_file", "component": "ui/other.js"}},
    ):
        with pytest.raises(InstallationIdentityError):
            verify_owner_check(public, signature, now=fields["issued_at"], **{**fields, **change})


def test_proof_rejects_invalid_encoding_stale_time_and_inconsistent_integrity(identity):
    private, public, fields = identity
    signature = sign_owner_check(private, **fields)
    with pytest.raises(InstallationIdentityError):
        verify_owner_check(public, signature + "=", now=fields["issued_at"], **fields)
    with pytest.raises(InstallationIdentityError):
        verify_owner_check(public, signature, now=fields["issued_at"] + 91, **fields)
    with pytest.raises(InstallationIdentityError):
        owner_check_message(**{**fields, "integrity_ok": True})


def test_configured_private_key_signs_and_missing_key_never_falls_back(identity, tmp_path):
    private, public, fields = identity
    key_path = tmp_path / "installation.key"
    key_path.write_bytes(private)
    payload = owner_check_payload(
        installation_id=fields["installation_id"], license_token=fields["license_token"],
        nonce=fields["nonce"], integrity_ok=fields["integrity_ok"],
        integrity_finding=fields["integrity_finding"], private_key_path=str(key_path),
        issued_at=fields["issued_at"],
    )
    verify_owner_check(public, payload["proof_signature"], now=fields["issued_at"], **fields)
    key_path.unlink()
    with pytest.raises(InstallationIdentityError):
        owner_check_payload(
            installation_id=fields["installation_id"], license_token=fields["license_token"],
            nonce=fields["nonce"], integrity_ok=True, integrity_finding=None,
            private_key_path=str(key_path),
        )


def test_enrollment_binds_one_time_token_license_and_key(identity):
    private, public, fields = identity
    enrollment = {
        "installation_id": fields["installation_id"], "license_token": fields["license_token"],
        "enrollment_token": "e" * 43, "public_key": public,
        "nonce": fields["nonce"], "issued_at": fields["issued_at"],
    }
    signature = sign_enrollment(private, **enrollment)
    verify_enrollment(signature=signature, now=fields["issued_at"], **enrollment)
    for changes in ({"enrollment_token": "x" * 43}, {"license_token": "different-license"}):
        with pytest.raises(InstallationIdentityError):
            verify_enrollment(signature=signature, now=fields["issued_at"], **{**enrollment, **changes})
    with pytest.raises(InstallationIdentityError):
        verify_enrollment(signature=signature, now=fields["issued_at"] + 91, **enrollment)


def test_binding_request_proof_binds_domains_ips_reason_and_freshness(identity):
    private, public, base = identity
    fields = {
        "installation_id": base["installation_id"],
        "license_token": base["license_token"],
        "nonce": base["nonce"],
        "issued_at": base["issued_at"],
        "domains": ["app.customer.example", "customer.example"],
        "ip_ranges": ["203.0.113.10/32"],
        "reason": "Move to the new host",
    }
    signature = sign_binding_request(private, **fields)
    verify_binding_request(public, signature, now=fields["issued_at"], **fields)
    for change in (
        {"domains": ["other.example"]},
        {"ip_ranges": ["203.0.113.11/32"]},
        {"reason": "different request"},
        {"license_token": "different-license"},
    ):
        with pytest.raises(InstallationIdentityError):
            verify_binding_request(public, signature, now=fields["issued_at"], **{**fields, **change})
    with pytest.raises(InstallationIdentityError):
        verify_binding_request(public, signature, now=fields["issued_at"] + 301, **fields)
    with pytest.raises(InstallationIdentityError):
        sign_binding_request(private, **{**fields, "domains": ["Customer.example"]})


@pytest.mark.parametrize("finding", [None, {"reason": "modified_file", "component": "ui/server.js"}])
def test_node_and_python_sign_identical_owner_check_bytes(identity, finding):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for cross-runtime signature verification")
    private, public, fields = identity
    fields = {**fields, "integrity_finding": finding, "integrity_ok": finding is None}
    script = r'''
import { signOwnerCheck } from "./ui/scripts/verify-client-release.mjs";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const data = JSON.parse(input);
process.stdout.write(signOwnerCheck(Buffer.from(data.private, "base64"), data.fields));
'''
    result = subprocess.run(
        [node, "--input-type=module", "-e", script], cwd=ROOT,
        input=json.dumps({"private": base64.b64encode(private).decode("ascii"), "fields": fields}),
        capture_output=True, text=True, check=True, timeout=15,
    )
    assert result.stdout == sign_owner_check(private, **fields)
    verify_owner_check(public, result.stdout, now=fields["issued_at"], **fields)
