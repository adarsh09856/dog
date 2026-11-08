import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services import release_integrity
from api.services.release_integrity import (
    ReleaseIntegrityError,
    protected_files,
    verify_configured_release,
    verify_release_manifest,
)


def _client_release(tmp_path, *, model_assets=None):
    root = tmp_path / "client"
    for relative, content in {
        "api/app.py": "pass\n",
        "api/services/release_integrity.py": "pass\n",
        "api/services/deployment_edition.py": "IMAGE_EDITION = 'client'\n",
        "api/services/owner_public_keys.json": '{"release":"test"}\n',
        "pipecat/src/pipecat/__init__.py": "pass\n",
        "scripts/run_web.sh": "exit 0\n",
        "scripts/start_services_docker.sh": "exit 0\n",
        "docs/docs.json": "{}\n",
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    private = Ed25519PrivateKey.generate()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).rstrip(b"=").decode()
    images = {
        "api": {"kind": "registry_digest", "reference": "registry.example/api@sha256:" + "a" * 64},
        "ui": {"kind": "registry_digest", "reference": "registry.example/ui@sha256:" + "b" * 64},
    }
    model_images = {
        name: f"registry.example/{name.replace('_', '-')}@sha256:{letter * 64}"
        for name, letter in (
            ("ollama", "c"), ("indic_stt", "d"),
            ("indus_tts", "e"), ("indic_vits_tts", "f"),
        )
    }
    payload = {
        "edition": "client",
        "files": protected_files(root),
        "ui_files": {},
        "images": images,
        "model_images": model_images,
        "schema_compatibility": {"head": "rev1", "upgrade_from": ["rev1"], "rollback_to": []},
    }
    if model_assets is not None:
        payload["model_assets"] = model_assets
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "client-release.json"
    manifest.write_text(json.dumps({
        "payload": payload,
        "signature": base64.urlsafe_b64encode(private.sign(canonical)).rstrip(b"=").decode(),
    }), encoding="utf-8")
    return root, manifest, public, payload


def _configure_runtime(monkeypatch, manifest, public, payload, *, model_digest):
    monkeypatch.setattr(release_integrity, "trusted_release_public_key", lambda: public)
    monkeypatch.setattr(release_integrity, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_RELEASE_MANIFEST", str(manifest))
    monkeypatch.setenv("KODEWAVES_API_IMAGE", payload["images"]["api"]["reference"])
    monkeypatch.setenv("KODEWAVES_UI_IMAGE", payload["images"]["ui"]["reference"])
    monkeypatch.setenv("COMPOSE_PROFILES", "direct-ingress,self-hosted")
    for name, reference in payload["model_images"].items():
        monkeypatch.setenv(f"KODEWAVES_CLIENT_{name.upper()}_IMAGE", reference)
    monkeypatch.setenv("KODEWAVES_CLIENT_OLLAMA_MODEL", "qwen3.5:2b-q4_K_M")
    monkeypatch.setenv("KODEWAVES_CLIENT_OLLAMA_MODEL_DIGEST", model_digest)


def test_signed_release_rejects_invalid_model_asset_descriptor(tmp_path):
    root, manifest, public, payload = _client_release(
        tmp_path, model_assets={"ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": "mutable-tag"}},
    )

    with pytest.raises(ReleaseIntegrityError, match="model asset metadata"):
        verify_release_manifest(root, manifest, public)


def test_self_hosted_runtime_accepts_the_exact_signed_model_digest(monkeypatch, tmp_path):
    digest = "sha256:" + "a" * 64
    root, manifest, public, payload = _client_release(
        tmp_path, model_assets={"ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": digest}},
    )
    _configure_runtime(monkeypatch, manifest, public, payload, model_digest=digest)

    assert verify_configured_release(root)["model_assets"]["ollama"]["digest"] == digest


def test_self_hosted_runtime_rejects_a_mutable_model_tag_digest(monkeypatch, tmp_path):
    digest = "sha256:" + "a" * 64
    root, manifest, public, payload = _client_release(
        tmp_path, model_assets={"ollama": {"name": "qwen3.5:2b-q4_K_M", "digest": digest}},
    )
    _configure_runtime(monkeypatch, manifest, public, payload, model_digest="sha256:" + "b" * 64)

    with pytest.raises(ReleaseIntegrityError, match="model weights do not match"):
        verify_configured_release(root)


def test_self_hosted_runtime_requires_a_signed_model_asset(monkeypatch, tmp_path):
    root, manifest, public, payload = _client_release(tmp_path)
    _configure_runtime(monkeypatch, manifest, public, payload, model_digest="sha256:" + "a" * 64)

    with pytest.raises(ReleaseIntegrityError, match="not bound to the signed release"):
        verify_configured_release(root)


def test_cloud_only_runtime_does_not_require_local_model_assets(monkeypatch, tmp_path):
    root, manifest, public, payload = _client_release(tmp_path)
    _configure_runtime(monkeypatch, manifest, public, payload, model_digest="")
    monkeypatch.setenv("COMPOSE_PROFILES", "direct-ingress")
    monkeypatch.setenv("KODEWAVES_CLIENT_OLLAMA_MODEL", "")
    monkeypatch.setenv("KODEWAVES_CLIENT_OLLAMA_MODEL_DIGEST", "")

    assert verify_configured_release(root)["edition"] == "client"
