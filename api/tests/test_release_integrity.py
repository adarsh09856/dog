import asyncio
import base64
import json
import time
from types import SimpleNamespace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services import release_integrity
from api.services.release_integrity import (
    ReleaseIntegrityError,
    protected_files,
    report_startup_integrity_failure,
    verify_configured_release,
    verify_release_before_startup,
    verify_release_manifest,
)


def test_signed_release_rejects_modified_or_added_protected_files(tmp_path):
    root = tmp_path / "client"
    (root / "api").mkdir(parents=True)
    (root / "scripts").mkdir()
    source = root / "api" / "app.py"
    source.write_text("print('approved')\n", encoding="utf-8")
    (root / "api" / "services").mkdir()
    (root / "api" / "services" / "release_integrity.py").write_text("pass\n", encoding="utf-8")
    (root / "api" / "services" / "deployment_edition.py").write_text("IMAGE_EDITION = 'client'\n", encoding="utf-8")
    (root / "api" / "services" / "owner_public_keys.json").write_text('{"license":"test","release":"test"}\n', encoding="utf-8")
    (root / "pipecat" / "src" / "pipecat").mkdir(parents=True)
    (root / "pipecat" / "src" / "pipecat" / "__init__.py").write_text("pass\n", encoding="utf-8")
    (root / "scripts" / "run_web.sh").write_text("exit 0\n", encoding="utf-8")
    (root / "scripts" / "start_services_docker.sh").write_text("exit 0\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "docs.json").write_text("{}\n", encoding="utf-8")

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    payload = {"edition": "client", "files": protected_files(root), "ui_files": {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "signed-manifest.json"
    manifest.write_text(
        json.dumps({
            "payload": payload,
            "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode("ascii"),
        }),
        encoding="utf-8",
    )

    verify_release_manifest(root, manifest, public_key)
    source.write_text("print('modified')\n", encoding="utf-8")
    with pytest.raises(ReleaseIntegrityError, match="differ") as modified:
        verify_release_manifest(root, manifest, public_key)
    assert modified.value.finding() == {
        "reason": "modified_file", "component": "api/app.py",
        "expected_sha256": payload["files"]["api/app.py"],
        "observed_sha256": protected_files(root)["api/app.py"],
    }
    source.write_text("print('approved')\n", encoding="utf-8")
    (root / "api" / "injected.py").write_text("print('extra')\n", encoding="utf-8")
    with pytest.raises(ReleaseIntegrityError, match="differ") as added:
        verify_release_manifest(root, manifest, public_key)
    assert added.value.finding()["reason"] == "added_file"
    assert added.value.finding()["component"] == "api/injected.py"


def test_signed_release_requires_a_valid_ui_inventory(tmp_path):
    root = tmp_path / "client"
    (root / "api" / "services").mkdir(parents=True)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    payload = {"edition": "client", "files": {}, "ui_files": {"server.js": "invalid"}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "invalid-ui-manifest.json"
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode("ascii"),
    }), encoding="utf-8")

    with pytest.raises(ReleaseIntegrityError, match="Invalid client release manifest"):
        verify_release_manifest(root, manifest, public_key)


def test_signed_release_validates_image_and_schema_metadata(tmp_path):
    root, manifest, public = signed_test_tree(tmp_path)
    private = Ed25519PrivateKey.generate()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    payload = {
        "edition": "client", "files": protected_files(root), "ui_files": {},
        "images": {
            "api": {"kind": "registry_digest", "reference": "registry.example/api@sha256:" + "a" * 64},
            "ui": {"kind": "image_id", "reference": "sha256:" + "b" * 64},
        },
        "schema_compatibility": {"head": "new", "upgrade_from": ["old", "new"], "rollback_to": []},
    }

    def write_signed():
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        manifest.write_text(json.dumps({
            "payload": payload,
            "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode(),
        }))

    write_signed()
    assert verify_release_manifest(root, manifest, public)["images"] == payload["images"]
    payload["schema_compatibility"]["rollback_to"] = ["unrelated"]
    write_signed()
    with pytest.raises(ReleaseIntegrityError, match="schema compatibility"):
        verify_release_manifest(root, manifest, public)


def test_configured_release_rejects_runtime_image_digest_mismatch(monkeypatch, tmp_path):
    root, manifest, public = signed_test_tree(tmp_path)
    private = Ed25519PrivateKey.generate()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    payload = {
        "edition": "client", "files": protected_files(root), "ui_files": {},
        "images": {
            "api": {"kind": "registry_digest", "reference": "registry.example/api@sha256:" + "a" * 64},
            "ui": {"kind": "registry_digest", "reference": "registry.example/ui@sha256:" + "b" * 64},
        },
        "schema_compatibility": {"head": "rev1", "upgrade_from": ["rev1"], "rollback_to": []},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode(),
    }))
    monkeypatch.setattr(release_integrity, "trusted_release_public_key", lambda: public)
    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_RELEASE_MANIFEST", str(manifest))
    monkeypatch.setenv("KODEWAVES_API_IMAGE", payload["images"]["api"]["reference"])
    monkeypatch.setenv("KODEWAVES_UI_IMAGE", "registry.example/ui@sha256:" + "c" * 64)
    with pytest.raises(ReleaseIntegrityError, match="UI image does not match"):
        verify_configured_release(root)


def test_migration_compatibility_derives_head_and_ancestors(tmp_path):
    from api.services.release_schema import migration_compatibility

    migrations = tmp_path / "versions"
    migrations.mkdir()
    (migrations / "first.py").write_text("revision = 'first'\ndown_revision = None\n")
    (migrations / "second.py").write_text("revision = 'second'\ndown_revision = 'first'\n")
    assert migration_compatibility(migrations) == {
        "head": "second", "upgrade_from": ["second"], "rollback_to": [],
    }
    assert migration_compatibility(migrations, ["first"])["upgrade_from"] == ["first", "second"]


def test_migration_compatibility_rejects_ambiguous_heads(tmp_path):
    from api.services.release_schema import migration_compatibility

    migrations = tmp_path / "versions"
    migrations.mkdir()
    (migrations / "first.py").write_text("revision = 'first'\ndown_revision = None\n")
    (migrations / "second.py").write_text("revision = 'second'\ndown_revision = None\n")
    with pytest.raises(ValueError, match="one Alembic head"):
        migration_compatibility(migrations)


def test_client_release_gate_fails_without_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", None)
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    monkeypatch.delenv("KODEWAVES_RELEASE_MANIFEST", raising=False)
    monkeypatch.delenv("KODEWAVES_RELEASE_PUBLIC_KEY", raising=False)
    with pytest.raises(ReleaseIntegrityError, match="required"):
        verify_configured_release(tmp_path)


def test_baked_client_edition_cannot_disable_integrity_with_environment(monkeypatch, tmp_path):
    from api.services import release_integrity

    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_EDITION", "saas")
    with pytest.raises(ReleaseIntegrityError, match="does not match") as mismatch:
        verify_configured_release(tmp_path)
    assert mismatch.value.finding()["reason"] == "unknown"


def test_client_release_gate_ignores_replacement_environment_key(monkeypatch, tmp_path):
    from api.services import owner_trust

    root = tmp_path / "client"
    (root / "api" / "services").mkdir(parents=True)
    (root / "pipecat" / "src" / "pipecat").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "docs").mkdir()
    for relative in (
        "api/app.py", "api/services/release_integrity.py",
        "api/services/deployment_edition.py",
        "pipecat/src/pipecat/__init__.py", "scripts/run_web.sh",
        "scripts/start_services_docker.sh", "docs/docs.json",
    ):
        (root / relative).write_text("approved\n", encoding="utf-8")
    owner = Ed25519PrivateKey.generate()
    forger = Ed25519PrivateKey.generate()

    def public_key(private):
        return base64.urlsafe_b64encode(private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )).rstrip(b"=").decode()

    trust_file = root / "api" / "services" / "owner_public_keys.json"
    trust_file.write_text(json.dumps({"license": public_key(owner), "release": public_key(owner)}), encoding="ascii")
    payload = {"edition": "client", "files": protected_files(root), "ui_files": {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(forger.sign(canonical)).rstrip(b"=").decode(),
    }), encoding="utf-8")
    monkeypatch.setattr(owner_trust, "TRUST_FILE", trust_file)
    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", None)
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_RELEASE_MANIFEST", str(manifest))
    monkeypatch.setenv("KODEWAVES_RELEASE_PUBLIC_KEY", public_key(forger))

    with pytest.raises(ReleaseIntegrityError, match="invalid"):
        verify_configured_release(root)


def test_failed_startup_reports_bounded_finding_to_pinned_owner_endpoint(monkeypatch):
    import httpx

    from api.services import release_integrity

    sent = []

    class Response:
        def raise_for_status(self):
            return None

    def post(url, **kwargs):
        sent.append((url, kwargs))
        return Response()

    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_EDITION", "saas")
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", "signed-token")
    monkeypatch.setattr(release_integrity, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(httpx, "post", post)
    report_startup_integrity_failure(ReleaseIntegrityError(
        "modified", reason="modified_file", component="api/app.py",
        expected_sha256="a" * 64, observed_sha256="b" * 64,
    ))
    assert len(sent) == 1
    assert sent[0][0] == "https://owner.example.com/check"
    assert sent[0][1]["headers"] == {"Authorization": "Bearer signed-token"}
    assert sent[0][1]["json"]["integrity_finding"]["component"] == "api/app.py"
    assert sent[0][1]["timeout"] == 5.0


def test_failed_startup_signs_alert_when_installation_key_is_configured(monkeypatch, tmp_path):
    import httpx

    from api.services import release_integrity
    from api.services.installation_identity import verify_owner_check

    private = Ed25519PrivateKey.generate()
    key_path = tmp_path / "client.key"
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    ))
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )).rstrip(b"=").decode("ascii")
    sent = []
    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", "signed-token")
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", "client-1")
    monkeypatch.setenv("KODEWAVES_INSTALLATION_KEY_FILE", str(key_path))
    monkeypatch.setattr(release_integrity, "trusted_owner_status_url", lambda: "https://owner.example.com/check")
    monkeypatch.setattr(httpx, "post", lambda _url, **kwargs: (
        sent.append(kwargs) or SimpleNamespace(raise_for_status=lambda: None)
    ))
    report_startup_integrity_failure(ReleaseIntegrityError("modified", reason="modified_file", component="api/app.py"))
    body = sent[0]["json"]
    verify_owner_check(
        public, body["proof_signature"], installation_id="client-1", license_token="signed-token",
        nonce=body["nonce"], issued_at=body["proof_issued_at"], integrity_ok=False,
        integrity_finding=body["integrity_finding"],
    )


@pytest.mark.asyncio
async def test_startup_integrity_alert_reaches_owner_check_endpoint(monkeypatch, tmp_path):
    """Bridge the real startup reporter to the owner API without network or DB access."""
    import httpx
    from fastapi import FastAPI

    from api.routes.admin import client_installation_check
from api.tests.owner_signer_test_utils import mock_owner_signer
    from api.services import release_integrity
    from api.services.installation_license import issue_license_token, verify_installation_status_claims

    def private_bytes(key):
        return key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )

    def public_string(key):
        return base64.urlsafe_b64encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).rstrip(b"=").decode("ascii")

    owner_key = Ed25519PrivateKey.generate()
    installation_key = Ed25519PrivateKey.generate()
    owner_private = private_bytes(owner_key)
    owner_public = public_string(owner_key)
    installation_public = public_string(installation_key)
    now = int(time.time())
    installation_id = "client-alert-test"
    token = issue_license_token({
        "iat": now - 1,
        "exp": now + 3600,
        "edition": "client",
        "installation_id": installation_id,
        "customer_id": "isolated-test",
        "domains": ["customer.example"],
        "ip_ranges": ["203.0.113.0/24"],
        "features": ["voice"],
        "limits": {"max_concurrent_calls": 1},
    }, owner_private)
    key_path = tmp_path / "installation.key"
    key_path.write_bytes(private_bytes(installation_key))

    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setattr(
        release_integrity,
        "trusted_owner_status_url",
        lambda: "https://owner.example.com/client-installations/check",
    )
    mock_owner_signer(monkeypatch, client_installation_check, (owner_private, owner_public))
    monkeypatch.setattr(
        client_installation_check,
        "get_client_installation_record",
        AsyncMock(return_value={"installation_public_key": installation_public}),
    )
    persisted = {}

    async def record_check(_installation_id, _fingerprint, **kwargs):
        persisted.update(kwargs)
        return {
            "revoked_at": None,
            "integrity_failed_at": datetime.now(UTC).isoformat(),
            "expires_at": now + 3600,
        }

    monkeypatch.setattr(client_installation_check, "record_client_installation_check", record_check)
    monkeypatch.setenv("KODEWAVES_LICENSE_TOKEN", token)
    monkeypatch.setenv("KODEWAVES_INSTALLATION_ID", installation_id)
    monkeypatch.setenv("KODEWAVES_INSTALLATION_KEY_FILE", str(key_path))

    owner_app = FastAPI()
    owner_app.include_router(client_installation_check.router)
    responses = []

    def post_to_local_owner(url, **kwargs):
        async def request_owner():
            transport = httpx.ASGITransport(app=owner_app, client=("203.0.113.7", 1234))
            async with httpx.AsyncClient(
                transport=transport,
                base_url="https://owner.example.com",
            ) as client:
                response = await client.post(
                    url,
                    json=kwargs["json"],
                    headers=kwargs["headers"],
                )
                responses.append(response)
                return response

        # The production reporter is synchronous; run its local ASGI transport
        # in this worker thread so the test's async event loop stays independent.
        return asyncio.run(request_owner())

    monkeypatch.setattr(httpx, "post", post_to_local_owner)
    finding = ReleaseIntegrityError(
        "Protected application file changed",
        reason="modified_file",
        component="api/app.py",
        expected_sha256="a" * 64,
        observed_sha256="b" * 64,
    )
    def fail_release_verification(_root=None):
        raise finding

    monkeypatch.setattr(release_integrity, "verify_configured_release", fail_release_verification)
    with pytest.raises(ReleaseIntegrityError, match="Protected application file changed"):
        await asyncio.to_thread(release_integrity.verify_release_before_startup)

    assert len(responses) == 1
    assert responses[0].status_code == 200, responses[0].text
    assert persisted["integrity_ok"] is False
    assert persisted["integrity_finding"] == finding.finding()
    assert persisted["expected_public_key"] == installation_public
    request_body = json.loads(responses[0].request.content)
    status = verify_installation_status_claims(
        responses[0].json()["signed_status"],
        public_key=owner_public,
        installation_id=installation_id,
        license_token=token,
        nonce=request_body["nonce"],
    )
    assert status["revoked"] is True
    assert status["binding_valid"] is True
    assert status["observed_ip"] == "203.0.113.7"


def test_direct_app_startup_reports_and_rejects_integrity_failure(monkeypatch):
    from api.services import release_integrity

    reported = []

    def fail_verification(_root=None):
        raise ReleaseIntegrityError("tampered")

    monkeypatch.setattr(release_integrity, "verify_configured_release", fail_verification)
    monkeypatch.setattr(release_integrity, "report_startup_integrity_failure", reported.append)
    with pytest.raises(ReleaseIntegrityError, match="tampered"):
        verify_release_before_startup()
    assert len(reported) == 1


def signed_test_tree(tmp_path):
    root = tmp_path / "client"
    for relative in (
        "api/app.py", "api/services/release_integrity.py", "api/services/deployment_edition.py",
        "api/services/owner_public_keys.json", "pipecat/src/pipecat/__init__.py",
        "scripts/run_web.sh", "scripts/start_services_docker.sh", "docs/docs.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("approved\n")
    key = Ed25519PrivateKey.generate()
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    payload = {"edition": "client", "files": protected_files(root), "ui_files": {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"payload": payload, "signature": base64.urlsafe_b64encode(key.sign(canonical)).rstrip(b"=").decode()}))
    return root, manifest, public


@pytest.mark.parametrize("relative", [
    "api/injected.pyc", "api/injected.so", "api/mcp_server/injected.js",
    "api/local_models/injected.onnx", "api/assets/injected.wav",
    "api/workflow/injected.json", "pipecat/src/pipecat/templates/injected.jinja2",
    "api/mcp_server/ts_validator/node_modules/typescript/lib/injected.js",
    "docs/integrity-guide.mdx",
    "api/routes/admin/client_installations.py", "api/routes/superuser.py",
])
def test_signed_release_rejects_added_runtime_files(tmp_path, relative):
    root, manifest, public = signed_test_tree(tmp_path)
    injected = root / relative
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(b"unapproved executable bytes")
    with pytest.raises(ReleaseIntegrityError) as denied:
        verify_release_manifest(root, manifest, public)
    assert denied.value.finding()["reason"] == "added_file"
    assert denied.value.finding()["component"] == relative


@pytest.mark.parametrize("relative", [
    "api/local_models/model.onnx", "api/assets/prompt.json",
    "api/templates/response.jinja2", "pipecat/src/pipecat/audio/voice.wav",
    "api/mcp_server/ts_validator/node_modules/typescript/lib/typescript.js",
    "docs/guides/voice.mdx",
])
def test_signed_release_rejects_modified_runtime_assets(tmp_path, relative):
    root, manifest, public = signed_test_tree(tmp_path)
    asset = root / relative
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"approved asset")
    payload_files = protected_files(root)
    private = Ed25519PrivateKey.generate()
    # Re-sign the fixture inventory to model the approved build containing
    # this runtime asset, then ensure changing it invalidates that inventory.
    payload = {"edition": "client", "files": payload_files, "ui_files": {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode(),
    }))
    asset.write_bytes(b"modified asset")
    with pytest.raises(ReleaseIntegrityError) as denied:
        verify_release_manifest(root, manifest, public)
    assert denied.value.finding()["reason"] == "modified_file"
    assert denied.value.finding()["component"] == relative


@pytest.mark.parametrize("directory", [False, True])
def test_signed_release_rejects_linked_application_code(tmp_path, directory):
    root, manifest, public = signed_test_tree(tmp_path)
    outside = tmp_path / ("external_package" if directory else "external.py")
    if directory:
        outside.mkdir()
        (outside / "__init__.py").write_text("unapproved\n")
    else:
        outside.write_text("unapproved\n")
    linked = root / "api" / ("linked_package" if directory else "linked.py")
    try:
        linked.symlink_to(outside, target_is_directory=directory)
    except OSError as error:
        pytest.skip(f"OS does not permit test symbolic links: {error}")
    with pytest.raises(ReleaseIntegrityError, match="[Ss]ymbolic link"):
        verify_release_manifest(root, manifest, public)


def test_link_rejection_branch_without_os_symlink_privileges(tmp_path, monkeypatch):
    root, manifest, public = signed_test_tree(tmp_path)
    injected = root / "api" / "linked.py"
    injected.write_text("unapproved\n")
    path_type = type(injected)
    original = path_type.is_symlink
    monkeypatch.setattr(path_type, "is_symlink", lambda path: path == injected or original(path))
    with pytest.raises(ReleaseIntegrityError, match="[Ss]ymbolic link") as denied:
        verify_release_manifest(root, manifest, public)
    assert denied.value.finding()["component"] == "api/linked.py"


def test_signed_release_rejects_linked_parent_of_protected_tree(tmp_path):
    import os
    import subprocess

    root, manifest, public = signed_test_tree(tmp_path)
    outside = tmp_path / "external_pipecat"
    (root / "pipecat").rename(outside)
    linked = root / "pipecat"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(linked), str(outside)], check=True, capture_output=True)
    else:
        linked.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReleaseIntegrityError, match="[Ss]ymbolic link") as denied:
        verify_release_manifest(root, manifest, public)
    assert denied.value.finding()["component"] == "pipecat"


def test_runtime_bytecode_cache_does_not_invalidate_signed_source(tmp_path):
    root, manifest, public = signed_test_tree(tmp_path)
    cache = root / "api" / "__pycache__"
    cache.mkdir()
    (cache / "app.cpython-313.pyc").write_bytes(b"runtime-generated cache")
    verify_release_manifest(root, manifest, public)


def test_client_release_requires_runtime_docs_index(tmp_path):
    root, manifest, public = signed_test_tree(tmp_path)
    (root / "docs" / "docs.json").unlink()
    with pytest.raises(ReleaseIntegrityError, match="docs/docs.json"):
        verify_release_manifest(root, manifest, public)
