from __future__ import annotations

import json
from pathlib import Path

from deploy.client import lifecycle_acceptance


def test_tenant_workflow_check_requires_org_scoped_app_record(monkeypatch):
    calls = []

    def fake_psql(compose_dir, project, sql):
        calls.append(sql)
        return "1"

    monkeypatch.setattr(lifecycle_acceptance, "_psql", fake_psql)

    assert lifecycle_acceptance._tenant_workflow_exists(
        Path("."), "project", "tenant-123", "workflow-123", "Before upgrade",
        "case-123", "baseline",
    )
    assert "JOIN workflows AS w ON w.organization_id = o.id" in calls[0]
    assert "organizations" in calls[0] and "workflow_definition" in calls[0]


def test_temp_directory_cleanup_reports_residual_secrets(monkeypatch, tmp_path):
    target = tmp_path / "ephemeral-release-secrets"
    target.mkdir()
    (target / ".env").write_text("synthetic-secret")

    def refuse_removal(path):
        raise PermissionError("cannot remove")

    monkeypatch.setattr(lifecycle_acceptance.shutil, "rmtree", refuse_removal)

    assert lifecycle_acceptance._remove_temp_directory(target) is False
    assert target.exists()


def test_prior_checkout_must_match_requested_commit(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle_acceptance, "_run", lambda *args, **kwargs: "b" * 40)

    try:
        lifecycle_acceptance._validate_source_checkout(tmp_path, "a" * 40)
    except ValueError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("mismatched prior source checkout was accepted")


def test_lifecycle_minio_is_built_from_repository_and_pinned_by_local_id(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return ""

    tag = "kw-lifecycle-0123456789ab-minio:acceptance"
    image_id = "sha256:" + "a" * 64
    monkeypatch.setattr(lifecycle_acceptance, "_run", fake_run)
    monkeypatch.setattr(lifecycle_acceptance, "_image_id", lambda value: image_id if value == tag else None)

    assert lifecycle_acceptance._build_lifecycle_minio(tag) == image_id
    command, kwargs = calls[0]
    assert command[:4] == ["docker", "build", "--pull", "--tag"]
    assert command[4] == tag
    assert Path(command[6]).name == "Dockerfile"
    assert Path(command[7]).name == "minio"
    assert kwargs["timeout"] == 1200


def test_lifecycle_minio_rejects_unscoped_tag():
    try:
        lifecycle_acceptance._build_lifecycle_minio("minio:latest")
    except ValueError as error:
        assert "generated acceptance project" in str(error)
    else:
        raise AssertionError("unscoped MinIO image tag was accepted")


def test_failure_diagnostics_keep_phase_and_type_without_exception_text():
    result = {"status": "started"}
    secret = "synthetic-password-must-not-be-recorded"
    lifecycle_acceptance._record_failure_diagnostics(
        result,
        "upgrade_candidate",
        ["prior_release_validated", "synthetic_data_seeded", "backup_created"],
        RuntimeError(secret),
    )

    assert result["status"] == "failed"
    assert result["failed_phase"] == "upgrade_candidate"
    assert result["failure_type"] == "RuntimeError"
    assert result["last_successful_phase"] == "backup_created"
    assert result["completed_phases"] == [
        "prior_release_validated", "synthetic_data_seeded", "backup_created",
    ]
    assert secret not in str(result)


def test_ci_failure_line_reports_phase_without_secret_details(tmp_path):
    secret = "synthetic-password-must-not-be-printed"
    report = tmp_path / "lifecycle-report.json"
    report.write_text(json.dumps({"failed_phase": "upgrade_candidate"}), encoding="utf-8")

    message = lifecycle_acceptance._format_failure_message(report, RuntimeError(secret))

    assert message == "Lifecycle acceptance failed: phase=upgrade_candidate, error_type=RuntimeError"
    assert secret not in message
