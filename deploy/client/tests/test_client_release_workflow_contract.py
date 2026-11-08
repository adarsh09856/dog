from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SILO_IMAGE = "docker.io/pgsty/silo@sha256:7bb2aff6b89efe1cb1303c10fc21d579447434ed06649ac9ec05a5e2dbf30ad7"
SILO_SOURCE = "silo-source-RELEASE.2026-10-26T00-00-00Z.tar.gz"


def test_production_release_lifecycle_and_installer_use_the_pinned_storage_release():
    workflow = (ROOT / ".github/workflows/client-production-release.yml").read_text(encoding="utf-8")

    assert SILO_IMAGE in workflow
    assert "--minio-image \"$MINIO_IMAGE\"" in workflow
    assert "owner-tools/fetch_client_silo_source.py" in workflow
    assert f"--output \"$work_dir/{SILO_SOURCE}\"" in workflow
    assert f"--silo-source-archive \"$work_dir/{SILO_SOURCE}\"" in workflow


def test_disposable_lifecycle_workflow_passes_the_pinned_storage_image():
    workflow = (ROOT / ".github/workflows/client-release-lifecycle.yml").read_text(encoding="utf-8")

    assert f"MINIO_IMAGE: {SILO_IMAGE}" in workflow
    assert "--minio-image \"$MINIO_IMAGE\"" in workflow


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
