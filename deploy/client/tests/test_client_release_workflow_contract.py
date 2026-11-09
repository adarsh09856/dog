from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "deploy/client"))
from validate_install import IMAGE_KEYS, MODEL_IMAGE_KEYS, validate_release_image_inventory

SILO_IMAGE = "docker.io/pgsty/silo@sha256:7bb2aff6b89efe1cb1303c10fc21d579447434ed06649ac9ec05a5e2dbf30ad7"
SILO_SOURCE = "silo-source-RELEASE.2026-10-26T00-00-00Z.tar.gz"


def test_production_release_lifecycle_and_installer_use_the_pinned_storage_release():
    workflow = (ROOT / ".github/workflows/client-production-release.yml").read_text(encoding="utf-8")

    assert SILO_IMAGE in workflow
    assert "--minio-image \"$MINIO_IMAGE\"" in workflow
    assert "owner-tools/fetch_client_silo_source.py" in workflow
    assert f"--output \"$work_dir/{SILO_SOURCE}\"" in workflow
    assert f"--silo-source-archive \"$work_dir/{SILO_SOURCE}\"" in workflow


def test_signed_update_metadata_is_attached_to_a_draft_stable_release():
    workflow_path = ROOT / ".github/workflows/client-production-release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert workflow["permissions"]["contents"] == "read"
    assert workflow["jobs"]["release"]["permissions"]["contents"] == "write"
    assert "release_version:" in workflow_text
    assert "min_current_version:" in workflow_text
    assert "Validate release version and ensure the draft tag is unused" in workflow_text
    assert "Release tag already exists" in workflow_text
    assert "owner-tools/sign_client_update_release.py" in workflow_text
    assert 'releases/download/$RELEASE_TAG/kodewaves-client-installer.tar.gz' in workflow_text
    assert 'gh release create --repo "$GITHUB_REPOSITORY" "$RELEASE_TAG"' in workflow_text
    assert "            --draft \\" in workflow_text
    for asset in (
        "kodewaves-client-installer.tar.gz",
        "kodewaves-client-installer.tar.gz.sig",
        "kodewaves-client-update.json",
        "client-release-manifest.json",
        "release-public.key",
    ):
        assert asset in workflow_text
    assert "The release remains a draft until an owner explicitly publishes it." in workflow_text


def test_disposable_lifecycle_workflow_passes_the_pinned_storage_image():
    workflow = (ROOT / ".github/workflows/client-release-lifecycle.yml").read_text(encoding="utf-8")

    assert f"MINIO_IMAGE: {SILO_IMAGE}" in workflow
    assert "--minio-image \"$MINIO_IMAGE\"" in workflow


def test_production_release_can_sign_the_complete_self_hosted_model_profile():
    workflow_path = ROOT / ".github/workflows/client-production-release.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    workflow_dispatch = workflow.get("on", workflow.get(True))["workflow_dispatch"]
    inputs = workflow_dispatch["inputs"]

    for name in (
        "ollama_image",
        "indic_stt_image",
        "indus_tts_image",
        "indic_vits_tts_image",
        "ollama_model_name",
        "ollama_model_digest",
    ):
        assert inputs[name]["required"] is False

    assert "--model-images-json" in workflow_text
    assert "--model-assets-json" in workflow_text
    assert "Verify self-hosted image digests exist in registries" in workflow_text
    assert "docker buildx imagetools inspect" in workflow_text
    assert "CLIENT_OLLAMA_IMAGE" in workflow_text
    assert "CLIENT_INDIC_STT_IMAGE" in workflow_text
    assert "CLIENT_INDUS_TTS_IMAGE" in workflow_text
    assert "CLIENT_INDIC_VITS_TTS_IMAGE" in workflow_text
    assert "CLIENT_OLLAMA_MODEL" in workflow_text
    assert "CLIENT_OLLAMA_MODEL_DIGEST" in workflow_text
    assert "all four" in workflow_text
    assert "validate_release_image_inventory(images)" in workflow_text


def test_release_image_inventory_separates_container_pins_from_model_metadata():
    digest = "a" * 64
    images = {name: f"registry.example/{name.lower()}@sha256:{digest}" for name in IMAGE_KEYS}
    images.update({name: f"registry.example/{name.lower()}@sha256:{digest}" for name in MODEL_IMAGE_KEYS})
    images["CLIENT_OLLAMA_MODEL"] = "qwen2.5:3b"
    images["CLIENT_OLLAMA_MODEL_DIGEST"] = "sha256:" + digest

    assert validate_release_image_inventory(images) == IMAGE_KEYS | MODEL_IMAGE_KEYS

    bad_asset = {**images, "CLIENT_OLLAMA_MODEL_DIGEST": "not-an-asset-digest"}
    with pytest.raises(ValueError, match="model asset"):
        validate_release_image_inventory(bad_asset)


def test_release_image_inventory_accepts_cloud_profile_and_rejects_partial_model_images():
    digest = "b" * 64
    cloud_images = {name: f"registry.example/{name.lower()}@sha256:{digest}" for name in IMAGE_KEYS}
    assert validate_release_image_inventory(cloud_images) == IMAGE_KEYS

    partial = {**cloud_images, "CLIENT_OLLAMA_IMAGE": f"registry.example/ollama@sha256:{digest}"}
    with pytest.raises(ValueError, match="model image"):
        validate_release_image_inventory(partial)


def test_client_compose_and_helm_chart_use_silo_healthcheck_and_digest():
    compose = (ROOT / "deploy/client/docker-compose.client.yaml").read_text(encoding="utf-8")
    hostinger = (ROOT / "deploy/hostinger/docker-compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "deploy/minio/Dockerfile").read_text(encoding="utf-8")
    chart_values = (ROOT / "deploy/helm/kodewaves/values.yaml").read_text(encoding="utf-8")
    chart_template = (ROOT / "deploy/helm/kodewaves/templates/internal-minio.yaml").read_text(encoding="utf-8")

    assert "/usr/bin/silo, healthcheck, ready" in compose
    assert '"/usr/bin/silo", "healthcheck", "ready"' in hostinger
    assert hostinger.count("      start_period: 2m") == 1
    assert SILO_IMAGE in dockerfile
    assert "repository: pgsty/silo" in chart_values
    assert "digest: sha256:" + SILO_IMAGE.rsplit("sha256:", 1)[1] in chart_values
    assert "{{ if .Values.minio.image.digest }}" in chart_template
    assert '"%s/%s@%s"' in chart_template
