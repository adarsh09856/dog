#!/usr/bin/env python3
"""Run a disposable, signed client upgrade/rollback lifecycle acceptance.

This is intentionally manual CI tooling. It builds prior and candidate images
locally, uses short-lived test keys and synthetic data, and never publishes.
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy/client"))
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import recovery
from ci_verify import _CI_POSTGRES_IMAGE, _CI_REDIS_IMAGE, _temporary_keypair
from verify_images import verify_api, verify_caddyfile, verify_ui

_IMAGE_PATH = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"
_IMAGE_REF = re.compile(
    rf"^(?:[a-z0-9][a-z0-9.-]*(?::[0-9]{{1,5}})?/)?{_IMAGE_PATH}(?:/{_IMAGE_PATH})*@sha256:[0-9a-f]{{64}}$"
)
_LOCAL_MINIO_TAG = re.compile(r"^kw-lifecycle-[0-9a-f]{12}-minio:acceptance$")
_REVISION = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_FLOW_ORDER = (
    "prior_release_validated", "synthetic_data_seeded", "backup_created",
    "candidate_upgraded_and_data_verified", "rollback_release_and_data_verified",
)


def validate_inputs(args: argparse.Namespace) -> None:
    """Reject mutable infrastructure refs and ambiguous source revisions."""
    for label in ("coturn", "caddy"):
        value = getattr(args, f"{label}_image")
        if not _IMAGE_REF.fullmatch(value):
            raise ValueError(f"{label} image must be a full immutable image@sha256 reference")
    if not re.fullmatch(r"[0-9a-f]{40}", args.prior_commit):
        raise ValueError("prior_commit must be a full 40-character Git commit SHA")


def validate_flow_order(completed: list[str]) -> None:
    """Require the acceptance phases to run in the declared safety order."""
    if tuple(completed) != _FLOW_ORDER:
        raise ValueError("Lifecycle phases ran out of order or were skipped")


def _build_lifecycle_minio(image_tag: str) -> str:
    """Build the pinned-version MinIO fixture locally and return its immutable image ID."""
    if not _LOCAL_MINIO_TAG.fullmatch(image_tag):
        raise ValueError("Lifecycle MinIO tag must be scoped to a generated acceptance project")
    dockerfile = ROOT / "deploy/minio/Dockerfile"
    context = ROOT / "deploy/minio"
    if not dockerfile.is_file() or not context.is_dir():
        raise ValueError("Repository MinIO fixture source is missing")
    _run([
        "docker", "build", "--pull", "--tag", image_tag,
        "--file", str(dockerfile), str(context),
    ], timeout=1200)
    return _image_id(image_tag)


def self_test() -> None:
    """Fast, Docker-free regression checks for pins, data assertions, cleanup, and order."""
    args = argparse.Namespace(
        prior_commit="a" * 40,
        coturn_image="registry.example.invalid/coturn@sha256:" + "b" * 64,
        caddy_image="registry.example.invalid/caddy@sha256:" + "c" * 64,
    )
    validate_inputs(args)
    for name in ("coturn_image", "caddy_image"):
        original = getattr(args, name)
        setattr(args, name, original.split("@", 1)[0] + ":latest")
        try:
            validate_inputs(args)
        except ValueError:
            pass
        else:
            raise AssertionError(f"mutable {name} was accepted")
        setattr(args, name, original)
    validate_flow_order(list(_FLOW_ORDER))
    try:
        validate_flow_order([_FLOW_ORDER[0], _FLOW_ORDER[2], _FLOW_ORDER[1], *_FLOW_ORDER[3:]])
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-order lifecycle phases were accepted")
    with tempfile.TemporaryDirectory(prefix="lifecycle-minio-build-test-") as root:
        with patch(__name__ + "._run", return_value="") as run, patch(
            __name__ + "._image_id", return_value="sha256:" + "d" * 64,
        ) as image_id:
            built_id = _build_lifecycle_minio("kw-lifecycle-0123456789ab-minio:acceptance")
        assert built_id == "sha256:" + "d" * 64
        command = run.call_args.args[0]
        assert command[0:3] == ["docker", "build", "--pull"]
        assert command[command.index("--tag") + 1] == "kw-lifecycle-0123456789ab-minio:acceptance"
        assert Path(command[-2]).name == "Dockerfile"
        assert Path(command[-1]).name == "minio"
        image_id.assert_called_once_with("kw-lifecycle-0123456789ab-minio:acceptance")
    try:
        _build_lifecycle_minio("minio:latest")
    except ValueError:
        pass
    else:
        raise AssertionError("unscoped local MinIO tag was accepted")
    with patch(__name__ + "._psql", return_value="1") as psql:
        if not _tenant_workflow_exists(
            Path("compose"), "project", "tenant", "workflow-uuid", "baseline", "case", "baseline",
        ):
            raise AssertionError("organization-linked workflow was not accepted")
        query = psql.call_args.args[2]
        if "JOIN workflows AS w ON w.organization_id = o.id" not in query:
            raise AssertionError("tenant workflow assertion is not organization-scoped")
    with patch(__name__ + "._psql", return_value="0"):
        if _tenant_workflow_exists(
            Path("compose"), "project", "tenant", "workflow-uuid", "baseline", "case", "baseline",
        ):
            raise AssertionError("missing organization-linked workflow was accepted")
    with tempfile.TemporaryDirectory(prefix="lifecycle-cleanup-self-test-") as parent:
        secret_dir = Path(parent) / "secrets"
        secret_dir.mkdir()
        if not _remove_temp_directory(secret_dir) or secret_dir.exists():
            raise AssertionError("temporary secret directory was not removed")
        secret_dir.mkdir()
        with patch(__name__ + ".shutil.rmtree", side_effect=OSError("simulated cleanup denial")):
            if _remove_temp_directory(secret_dir):
                raise AssertionError("failed temporary secret cleanup was accepted")
        if not secret_dir.exists():
            raise AssertionError("cleanup failure test did not leave the simulated secret path")
        shutil.rmtree(secret_dir)


def _run(command: list[str], *, cwd: Path = ROOT, input_text: str | None = None,
         timeout: int = 1200, capture: bool = True) -> str:
    result = subprocess.run(
        command, cwd=cwd, input=input_text, text=True, check=False, timeout=timeout,
        capture_output=capture,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()[-1200:]
        # Do not include command-line args: they may include temp credentials.
        raise RuntimeError(f"Command failed ({Path(command[0]).name}, exit {result.returncode}): {detail}")
    return (result.stdout or "").strip()


def _migration_head(source: Path) -> str:
    revisions: dict[str, tuple[str, ...]] = {}
    for migration in sorted((source / "api/alembic/versions").glob("*.py")):
        tree = ast.parse(migration.read_text(encoding="utf-8"), filename=str(migration))
        values: dict[str, Any] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}
                       for target in node.targets):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                            values[target.id] = ast.literal_eval(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in {"revision", "down_revision"} and node.value is not None:
                    values[node.target.id] = ast.literal_eval(node.value)
        revision, down = values.get("revision"), values.get("down_revision")
        if revision is None and down is None:
            continue
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise ValueError(f"Invalid migration revision in {migration.name}")
        if down is None:
            parents: tuple[str, ...] = ()
        elif isinstance(down, str) and _REVISION.fullmatch(down):
            parents = (down,)
        elif isinstance(down, (tuple, list)) and all(isinstance(item, str) and _REVISION.fullmatch(item) for item in down):
            parents = tuple(down)
        else:
            raise ValueError(f"Invalid migration parent in {migration.name}")
        if revision in revisions:
            raise ValueError(f"Duplicate migration revision {revision}")
        revisions[revision] = parents
    parents = {parent for values in revisions.values() for parent in values}
    if not revisions or parents - set(revisions):
        raise ValueError("Migration graph is empty or references missing parents")
    heads = sorted(set(revisions) - parents)
    if len(heads) != 1:
        raise ValueError(f"Expected one migration head, found {len(heads)}")
    return heads[0]


def _inventory(image: str, component: str, path: Path) -> dict[str, str]:
    if component == "api":
        command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python", image,
                   "-c", "import json; from pathlib import Path; from api.services.release_integrity import protected_files; print(json.dumps(protected_files(Path('/app'))))"]
    else:
        command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "node", image,
                   "/app/verify-client-release.mjs", "--inventory"]
    result = json.loads(_run(command))
    if not isinstance(result, dict) or not result or any(
        not isinstance(name, str) or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest) for name, digest in result.items()
    ):
        raise ValueError(f"Invalid {component} protected inventory")
    path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return result


def _image_id(tag: str) -> str:
    value = _run(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("Docker returned a non-immutable local image ID")
    return value


def _validate_source_checkout(source: Path, expected_commit: str) -> None:
    actual = _run(["git", "rev-parse", "HEAD"], cwd=source)
    if actual != expected_commit:
        raise ValueError("Prior source checkout does not match the requested release commit")


def _build(source: Path, tag_prefix: str, license_public: Path, release_public: Path,
           owner_status_url: str, inventory_dir: Path, release_label: str,
           set_phase: Callable[[str], None]) -> tuple[dict[str, str], dict[str, str]]:
    tags = {"api": f"{tag_prefix}-api:acceptance", "ui": f"{tag_prefix}-ui:acceptance"}
    for component in ("api", "ui"):
        set_phase(f"build_{release_label}_{component}_image")
        command = ["docker", "build", "--build-arg", "KODEWAVES_EDITION=client"]
        if component == "api":
            command.extend([
                "--build-arg", f"KODEWAVES_LICENSE_PUBLIC_KEY={license_public.read_text(encoding='ascii').strip()}",
                "--build-arg", f"KODEWAVES_RELEASE_PUBLIC_KEY={release_public.read_text(encoding='ascii').strip()}",
                "--build-arg", f"KODEWAVES_OWNER_STATUS_URL={owner_status_url}",
            ])
        else:
            command.extend([
                "--build-arg", f"KODEWAVES_RELEASE_PUBLIC_KEY={release_public.read_text(encoding='ascii').strip()}",
                "--build-arg", f"KODEWAVES_OWNER_STATUS_URL={owner_status_url}",
            ])
        command.extend(["-f", str(source / f"{component}/Dockerfile"), "-t", tags[component], str(source)])
        _run(command, timeout=2400, capture=False)
    set_phase(f"verify_{release_label}_api_image")
    verify_api(
        tags["api"],
        allow_legacy_owner_persistence=release_label == "prior",
    )
    set_phase(f"verify_{release_label}_ui_image")
    verify_ui(tags["ui"])
    inventory_dir.mkdir(parents=True, exist_ok=True)
    set_phase(f"inventory_{release_label}_api_image")
    api_inventory = _inventory(tags["api"], "api", inventory_dir / f"{tag_prefix}-api-inventory.json")
    set_phase(f"inventory_{release_label}_ui_image")
    ui_inventory = _inventory(tags["ui"], "ui", inventory_dir / f"{tag_prefix}-ui-inventory.json")
    inventories = {
        "api": api_inventory,
        "ui": ui_inventory,
    }
    set_phase(f"inspect_{release_label}_api_image")
    api_image_id = _image_id(tags["api"])
    set_phase(f"inspect_{release_label}_ui_image")
    ui_image_id = _image_id(tags["ui"])
    image_ids = {"api": api_image_id, "ui": ui_image_id}
    return image_ids, {**tags, **{f"{name}_inventory": str(inventory_dir / f"{tag_prefix}-{name}-inventory.json") for name in tags}}


def _signed_manifest(private_key_file: Path, public_key_file: Path, output: Path,
                     inventories: dict[str, dict[str, str]], images: dict[str, str],
                     schema: dict[str, Any]) -> dict[str, Any]:
    key = Ed25519PrivateKey.from_private_bytes(private_key_file.read_bytes())
    payload = {
        "edition": "client", "files": inventories["api"], "ui_files": inventories["ui"],
        "images": {name: {"kind": "image_id", "reference": images[name]} for name in ("api", "ui")},
        "schema_compatibility": schema,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signed = {"payload": payload, "signature": base64.urlsafe_b64encode(key.sign(canonical)).rstrip(b"=").decode("ascii")}
    output.write_text(json.dumps(signed, indent=2) + "\n", encoding="utf-8")
    trusted = public_key_file.read_text(encoding="ascii").strip()
    recovery._verify_release_manifest(output.read_bytes(), trusted)
    return signed


def _write_env(compose_dir: Path, values: dict[str, str]) -> Path:
    path = compose_dir / ".env"
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def _compose(compose_dir: Path, project: str, args: list[str], timeout: int = 900,
             input_text: str | None = None) -> str:
    env_file = compose_dir / ".env"
    return _run([
        "docker", "compose", "--project-directory", str(compose_dir), "--project-name", project,
        "--env-file", str(env_file), "-f", str(compose_dir / "docker-compose.client.yaml"),
        "-f", str(compose_dir / "docker-compose.recovery.yaml"), *args,
    ], cwd=compose_dir, timeout=timeout, input_text=input_text)


def _assert_compose_refs(compose_dir: Path, project: str, expected: dict[str, str]) -> None:
    rendered = json.loads(_compose(compose_dir, project, ["config", "--format", "json"]))
    services = rendered.get("services", {})
    if any(services.get(name, {}).get("image") != image for name, image in expected.items()):
        raise ValueError("Compose did not resolve the signed local image IDs")


def _psql(compose_dir: Path, project: str, sql: str) -> str:
    return _compose(compose_dir, project, [
        "exec", "-T", "postgres", "psql", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-d", "postgres", "-c", sql,
    ])


def _assert_schema_head(compose_dir: Path, project: str, expected: str, phase: str) -> None:
    actual = _psql(compose_dir, project, "SELECT version_num FROM alembic_version ORDER BY version_num")
    revisions = [item.strip() for item in actual.splitlines() if item.strip()]
    if revisions != [expected]:
        raise ValueError(f"{phase} Alembic head mismatch")


def _assert_running_image(compose_dir: Path, project: str, service: str, expected_id: str) -> None:
    # Confirm the image ID exists locally, then inspect both the configured
    # reference and the resolved image on the running container. The Compose
    # image ref is the immutable local sha256 ID recorded in the signed test
    # manifest, never a mutable or unresolved tag.
    _run(["docker", "image", "inspect", expected_id])
    container = _container_id(compose_dir, project, service)
    observed = _run(["docker", "inspect", "--format", "{{.Config.Image}}|{{.Image}}", container])
    if observed != f"{expected_id}|{expected_id}":
        raise ValueError(f"{service} is not running from its expected local image ID")


def _object(compose_dir: Path, project: str, name: str, payload: bytes | None = None) -> str:
    operation = "put" if payload is not None else "get"
    body = base64.b64encode(payload).decode("ascii") if payload is not None else ""
    script = f"""import base64, io, os
from minio import Minio
c=Minio(os.environ['MINIO_ENDPOINT'], access_key=os.environ['MINIO_ACCESS_KEY'], secret_key=os.environ['MINIO_SECRET_KEY'], secure=False)
b=os.environ['MINIO_BUCKET']
if not c.bucket_exists(b): c.make_bucket(b)
if {operation!r} == 'put':
 d=base64.b64decode({body!r}); c.put_object(b, {name!r}, io.BytesIO(d), len(d)); print('written')
else:
 try:
  r=c.get_object(b, {name!r}); d=r.read(); r.close(); r.release_conn(); print(base64.b64encode(d).decode('ascii'))
 except Exception as e:
  from minio.error import S3Error
  if isinstance(e, S3Error) and e.code in ('NoSuchKey','NoSuchBucket'): print('missing')
  else: raise
"""
    return _compose(compose_dir, project, ["exec", "-T", "api", "python", "-c", script])


def _sql_literal(value: str) -> str:
    """Quote a generated lifecycle value as a PostgreSQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def _tenant_workflow_exists(compose_dir: Path, project: str, tenant_provider_id: str,
                            workflow_uuid: str, workflow_name: str, case_id: str,
                            milestone: str) -> bool:
    """Check a workflow through its real organization tenant relationship."""
    query = (
        "SELECT count(*) FROM organizations AS o "
        "JOIN workflows AS w ON w.organization_id = o.id "
        f"WHERE o.provider_id = {_sql_literal(tenant_provider_id)} "
        f"AND w.workflow_uuid = {_sql_literal(workflow_uuid)} "
        f"AND w.name = {_sql_literal(workflow_name)} "
        f"AND w.workflow_definition->>'acceptance_case' = {_sql_literal(case_id)} "
        f"AND w.workflow_definition->>'milestone' = {_sql_literal(milestone)}"
    )
    return _psql(compose_dir, project, query) == "1"


def _remove_temp_directory(path: Path) -> bool:
    """Remove the directory holding temporary signing material, and verify it is gone."""
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return not path.exists()


def _record_failure_diagnostics(result: dict[str, Any], phase: str,
                                completed_phases: list[str], exc: Exception) -> None:
    """Record safe failure metadata without preserving command output or secrets."""
    result["status"] = "failed"
    result["failed_phase"] = phase
    result["failure_type"] = type(exc).__name__
    detail = str(exc).replace("\r", " ").replace("\n", " ")
    detail = re.sub(
        r"(?i)\b(password|token|secret|credential|private[_ -]?key)\b([=:]\s*)[^\s,;]+",
        r"\1\2<redacted>", detail,
    )
    detail = re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9])", "<redacted>", detail)
    detail = re.sub(r"(?<!\w)/(?:tmp|home|run|app)/[^\s,;]+", "<path>", detail)
    if detail:
        result["failure_detail"] = detail[:240]
    result["completed_phases"] = list(completed_phases)
    result["last_successful_phase"] = completed_phases[-1] if completed_phases else None


def _format_failure_message(report_path: str | Path | None, exc: Exception) -> str:
    """Return an actionable but secret-free CI failure line."""
    phase = "unknown"
    try:
        if report_path is not None:
            result = json.loads(Path(report_path).read_text(encoding="utf-8"))
            reported_phase = result.get("failed_phase")
            if isinstance(reported_phase, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reported_phase):
                phase = reported_phase
    except (OSError, ValueError, TypeError):
        pass
    return f"Lifecycle acceptance failed: phase={phase}, error_type={type(exc).__name__}"


def run(args: argparse.Namespace) -> dict[str, Any]:
    preflight_phase = "validate_inputs"
    try:
        validate_inputs(args)
        preflight_phase = "validate_candidate_checkout"
        head = _run(["git", "rev-parse", "HEAD"])
        if args.candidate_commit and head != args.candidate_commit:
            raise ValueError("Checked-out candidate commit does not match requested candidate commit")
        preflight_phase = "validate_prior_checkout"
        _validate_source_checkout(args.prior_source, args.prior_commit)
        preflight_phase = "validate_commit_ancestry"
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", args.prior_commit, head],
            cwd=ROOT, check=False,
        )
        if ancestor.returncode:
            raise ValueError("The prior release commit must be an ancestor of the checked-out candidate")
        preflight_phase = "validate_migration_compatibility"
        prior_head = _migration_head(args.prior_source)
        candidate_head = _migration_head(ROOT)
        if prior_head == candidate_head:
            raise ValueError("Prior and candidate releases must have distinct Alembic heads")
        if prior_head not in _ancestor_revisions(ROOT):
            raise ValueError("Candidate migration history does not descend from the selected prior schema")
    except Exception as exc:
        # Preflight runs before the disposable workspace exists. Still emit a
        # sanitized report so CI uploads the precise phase for early failures.
        result = {
            "status": "failed",
            "candidate_commit": getattr(args, "candidate_commit", None),
            "prior_commit": getattr(args, "prior_commit", None),
        }
        _record_failure_diagnostics(result, preflight_phase, [], exc)
        report_path = Path(args.report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise

    project = "kw-lifecycle-" + uuid.uuid4().hex[:12]
    case_id = "synthetic-" + uuid.uuid4().hex
    tenant_provider_id = f"lifecycle-{case_id}"
    tenant_workflow_uuid = str(uuid.uuid4())
    baseline_workflow_name = f"Lifecycle acceptance {case_id}"
    candidate_workflow_name = f"Lifecycle candidate {case_id}"
    object_base = f"acceptance/{case_id}/baseline.txt"
    object_candidate = f"acceptance/{case_id}/candidate.txt"
    result: dict[str, Any] = {
        "status": "failed", "candidate_commit": head, "prior_commit": args.prior_commit,
        "prior_schema_head": prior_head, "candidate_schema_head": candidate_head,
        "production_release": False, "data_is_synthetic": True,
        "rollback_authorization": "ephemeral signed acceptance fixture; not a production release claim",
    }
    temp_root = Path(tempfile.mkdtemp(prefix="kodewaves-lifecycle-"))
    completed_phases: list[str] = []
    compose_dir = temp_root / "client"
    images_to_remove: set[str] = set()
    original_volume_names: list[str] = []
    cleanup_errors: list[str] = []
    active_phase = "prepare_disposable_compose"
    report_path = Path(args.report).resolve()
    try:
        if report_path == temp_root or temp_root in report_path.parents:
            raise ValueError("Lifecycle report must be outside the temporary secrets directory")
        compose_dir.mkdir()
        client_compose = compose_dir / "docker-compose.client.yaml"
        shutil.copy2(ROOT / "deploy/client/docker-compose.client.yaml", client_compose)
        # Keep synthetic app credentials and data on an egress-isolated Docker
        # bridge for the entire upgrade/backup/rollback lifecycle.
        compose_text = client_compose.read_text(encoding="utf-8")
        network_anchor = "networks:\n  internal:\n    driver: bridge\n"
        if network_anchor not in compose_text:
            raise ValueError("Client Compose internal network definition changed; refusing an unisolated run")
        client_compose.write_text(
            compose_text.replace(network_anchor, network_anchor + "    internal: true\n", 1),
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "deploy/client/docker-compose.recovery.yaml", compose_dir)
        shutil.copy2(ROOT / "deploy/client/Caddyfile", compose_dir)
        minio_tag = project + "-minio:acceptance"
        images_to_remove.add(minio_tag)
        active_phase = "build_local_minio_fixture"
        minio_image_id = _build_lifecycle_minio(minio_tag)
        result["dependency_image_ids_sha256"] = {
            "postgres": hashlib.sha256(_CI_POSTGRES_IMAGE.encode()).hexdigest(),
            "redis": hashlib.sha256(_CI_REDIS_IMAGE.encode()).hexdigest(),
            "minio": hashlib.sha256(minio_image_id.encode()).hexdigest(),
        }
        license_private, license_public = _temporary_keypair(temp_root, "lifecycle-license")
        release_private, release_public = _temporary_keypair(temp_root, "lifecycle-release")
        verify_caddyfile(args.caddy_image, str(compose_dir / "Caddyfile"))

        # Build the immutable prior and candidate artifacts from two separate source trees.
        owner_status_url = "https://owner.invalid/api/v1/admin/client-installations/check"
        prior_tag_prefix = project + "-prior"
        candidate_tag_prefix = project + "-candidate"
        images_to_remove.update({f"{prior_tag_prefix}-api:acceptance", f"{prior_tag_prefix}-ui:acceptance"})
        images_to_remove.update({f"{candidate_tag_prefix}-api:acceptance", f"{candidate_tag_prefix}-ui:acceptance"})
        active_phase = "build_and_verify_release_images"

        def set_release_phase(phase: str) -> None:
            nonlocal active_phase
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", phase):
                raise ValueError("Invalid lifecycle release phase")
            active_phase = phase

        prior_ids, prior_artifacts = _build(
            args.prior_source, prior_tag_prefix, license_public, release_public,
            owner_status_url, temp_root / "prior-inventory", "prior", set_release_phase,
        )
        candidate_ids, candidate_artifacts = _build(
            ROOT, candidate_tag_prefix, license_public, release_public,
            owner_status_url, temp_root / "candidate-inventory", "candidate", set_release_phase,
        )
        images_to_remove.update(prior_artifacts[name] for name in ("api", "ui"))
        images_to_remove.update(candidate_artifacts[name] for name in ("api", "ui"))
        if prior_ids == candidate_ids:
            raise ValueError("Prior and candidate resolved to identical app image IDs")

        inventory_prior = {name: json.loads(Path(prior_artifacts[f"{name}_inventory"]).read_text()) for name in ("api", "ui")}
        inventory_candidate = {name: json.loads(Path(candidate_artifacts[f"{name}_inventory"]).read_text()) for name in ("api", "ui")}
        prior_manifest = compose_dir / "client-release-prior.json"
        candidate_manifest = compose_dir / "client-release-candidate.json"
        _signed_manifest(release_private, release_public, prior_manifest, inventory_prior, prior_ids,
                         {"head": prior_head, "upgrade_from": [prior_head], "rollback_to": []})
        candidate_schema = {
            "head": candidate_head,
            "upgrade_from": sorted({prior_head, candidate_head}),
            # This fixture is signed with the per-run key and authorizes only the
            # exact rollback scenario exercised by this disposable workflow.
            "rollback_to": [prior_head],
        }
        _signed_manifest(release_private, release_public, candidate_manifest, inventory_candidate, candidate_ids, candidate_schema)
        result["prior_manifest_sha256"] = hashlib.sha256(prior_manifest.read_bytes()).hexdigest()
        result["candidate_manifest_sha256"] = hashlib.sha256(candidate_manifest.read_bytes()).hexdigest()
        result["prior_image_ids_sha256"] = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in prior_ids.items()}
        result["candidate_image_ids_sha256"] = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in candidate_ids.items()}
        completed_phases.append("prior_release_validated")
        result["completed_phases"] = list(completed_phases)

        # Runtime-only license data uses a disposable key and a reserved synthetic domain.
        from api.services.installation_license import issue_license_token
        import time
        now = int(time.time())
        license_token = issue_license_token({
            "iat": now, "exp": now + 7200, "installation_id": case_id,
            "customer_id": "synthetic-lifecycle", "edition": "client",
            "domains": ["lifecycle.customer.example.invalid"], "ip_ranges": [],
            "features": ["voice"],
            "limits": {"max_concurrent_calls": 1, "max_seats": 1, "max_workspaces": 1},
        }, license_private.read_bytes())
        identity_id = case_id
        api_port, ui_port, minio_port = secrets.SystemRandom().sample(range(22000, 59000), 3)
        values = {
            "CLIENT_API_IMAGE": prior_ids["api"], "CLIENT_UI_IMAGE": prior_ids["ui"],
            "CLIENT_POSTGRES_IMAGE": _CI_POSTGRES_IMAGE, "CLIENT_REDIS_IMAGE": _CI_REDIS_IMAGE,
            "CLIENT_MINIO_IMAGE": minio_image_id, "CLIENT_COTURN_IMAGE": args.coturn_image,
            "CLIENT_CADDY_IMAGE": args.caddy_image, "COMPOSE_PROFILES": "",
            "COMPOSE_PROJECT_NAME": project, "KODEWAVES_INSTALLATION_ID": identity_id,
            "KODEWAVES_LICENSE_TOKEN": license_token, "KODEWAVES_OWNER_STATUS_POLL_SECONDS": "3600",
            "PUBLIC_HOST": "lifecycle.customer.example.invalid", "TURN_HOST": "127.0.0.1",
            "POSTGRES_PASSWORD": secrets.token_urlsafe(40), "REDIS_PASSWORD": secrets.token_urlsafe(40),
            "MINIO_ROOT_USER": "lifecycle-storage", "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(40),
            "OSS_JWT_SECRET": secrets.token_urlsafe(40),
            "MASTER_CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode(),
            "TELEPHONY_WS_TOKEN_SECRET": secrets.token_urlsafe(40), "TURN_SECRET": secrets.token_urlsafe(40),
            "CLIENT_RELEASE_MANIFEST_FILE": "./client-release-prior.json",
            "API_PORT": str(api_port), "UI_PORT": str(ui_port), "MINIO_PORT": str(minio_port),
        }
        env_file = _write_env(compose_dir, values)
        project_model = json.loads(_compose(compose_dir, project, ["config", "--format", "json"]))
        if any(project_model.get("services", {}).get(name, {}).get("image") != prior_ids[name] for name in ("api", "ui")):
            raise ValueError("Compose cannot resolve the prior signed image IDs")
        original_volume_names = [item["name"] for item in project_model["volumes"].values() if isinstance(item, dict) and item.get("name")]
        active_phase = "start_prior_release"
        _compose(compose_dir, project, ["up", "--detach", "--wait", "--wait-timeout", "360", "api", "ui"], timeout=480)
        _assert_running_image(compose_dir, project, "api", prior_ids["api"])
        _assert_running_image(compose_dir, project, "ui", prior_ids["ui"])
        _assert_running_image(compose_dir, project, "minio", minio_image_id)
        _assert_schema_head(compose_dir, project, prior_head, "Prior startup")
        result["prior_alembic_version"] = prior_head
        result["prior_api_health"] = "passed"
        _run(["docker", "exec", _container_id(compose_dir, project, "api"), "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)"])

        active_phase = "seed_synthetic_organization_record"
        organization_id = _psql(
            compose_dir, project,
            f"INSERT INTO organizations (provider_id) VALUES ({_sql_literal(tenant_provider_id)}) RETURNING id",
        )
        if not re.fullmatch(r"[0-9]+", organization_id):
            raise ValueError("Could not seed the synthetic tenant organization")
        workflow_payload = json.dumps({"acceptance_case": case_id, "milestone": "baseline"}, separators=(",", ":"))
        active_phase = "seed_synthetic_workflow_record"
        workflow_id = _psql(
            compose_dir, project,
            "INSERT INTO workflows "
            "(workflow_uuid, organization_id, name, workflow_definition, "
            "template_context_variables, call_disposition_codes, workflow_configurations) VALUES "
            f"({_sql_literal(tenant_workflow_uuid)}, {organization_id}, {_sql_literal(baseline_workflow_name)}, "
            f"{_sql_literal(workflow_payload)}::json, '{{}}'::json, '{{}}'::json, '{{}}'::json) RETURNING id",
        )
        if not re.fullmatch(r"[0-9]+", workflow_id):
            raise ValueError("Could not seed the synthetic tenant workflow")
        baseline_object = f"synthetic baseline {case_id}".encode()
        active_phase = "seed_synthetic_media_object"
        _object(compose_dir, project, object_base, baseline_object)
        result["synthetic_organization_id"] = int(organization_id)
        result["synthetic_workflow_id"] = int(workflow_id)
        result["seeded_synthetic_tenant_workflow"] = True
        completed_phases.append("synthetic_data_seeded")
        result["completed_phases"] = list(completed_phases)

        active_phase = "create_signed_backup"
        archive = temp_root / "prior-release-backup.tar.gz"
        _run([sys.executable, str(ROOT / "deploy/client/recovery.py"), "backup-docker",
              "--compose-dir", str(compose_dir), "--env-file", str(env_file),
              "--release-public-key", str(release_public), "--output", str(archive), "--confirm-maintenance"], timeout=900)
        result["signed_prior_release_backup"] = "passed"
        completed_phases.append("backup_created")

        values["CLIENT_API_IMAGE"] = candidate_ids["api"]
        values["CLIENT_UI_IMAGE"] = candidate_ids["ui"]
        values["CLIENT_RELEASE_MANIFEST_FILE"] = "./client-release-candidate.json"
        _write_env(compose_dir, values)
        _assert_compose_refs(compose_dir, project, {"api": candidate_ids["api"], "ui": candidate_ids["ui"]})
        active_phase = "upgrade_candidate"
        _compose(compose_dir, project, ["up", "--detach", "--wait", "--wait-timeout", "480", "api", "ui"], timeout=600)
        if _run(["docker", "inspect", "--format", "{{.Image}}", _container_id(compose_dir, project, "api")]) != candidate_ids["api"]:
            raise ValueError("Candidate API image did not start")
        _assert_running_image(compose_dir, project, "api", candidate_ids["api"])
        _assert_running_image(compose_dir, project, "ui", candidate_ids["ui"])
        _assert_schema_head(compose_dir, project, candidate_head, "Candidate migration")
        result["candidate_alembic_version"] = candidate_head
        if not _tenant_workflow_exists(
            compose_dir, project, tenant_provider_id, tenant_workflow_uuid,
            baseline_workflow_name, case_id, "baseline",
        ):
            raise ValueError("Synthetic tenant workflow was not preserved by upgrade")
        if base64.b64decode(_object(compose_dir, project, object_base)) != baseline_object:
            raise ValueError("Synthetic baseline MinIO object was not preserved by upgrade")
        candidate_payload = json.dumps({"acceptance_case": case_id, "milestone": "candidate"}, separators=(",", ":"))
        changed_workflow = _psql(
            compose_dir, project,
            "UPDATE workflows SET name = " + _sql_literal(candidate_workflow_name)
            + ", workflow_definition = " + _sql_literal(candidate_payload) + "::json "
            + "WHERE workflow_uuid = " + _sql_literal(tenant_workflow_uuid)
            + " AND organization_id = " + organization_id + " RETURNING id",
        )
        if not re.fullmatch(r"[0-9]+", changed_workflow):
            raise ValueError("Could not simulate candidate tenant workflow data")
        candidate_object = f"synthetic candidate {case_id}".encode()
        _object(compose_dir, project, object_candidate, candidate_object)
        result["candidate_upgrade_and_migration"] = "passed"
        result["candidate_data_checks"] = "passed"
        completed_phases.append("candidate_upgraded_and_data_verified")

        active_phase = "rollback_candidate_and_verify_data"
        rollback_result = _run([sys.executable, str(ROOT / "deploy/client/recovery.py"), "restore", str(archive),
                                "--docker-volumes", "--allow-release-rollback", "--compose-dir", str(compose_dir),
                                "--env-file", str(env_file), "--release-public-key", str(release_public),
                                "--confirm-maintenance"], timeout=1200)
        parsed_restore = json.loads(rollback_result)
        if parsed_restore.get("status") != "restored_to_new_volumes" or parsed_restore.get("release_rollback") is not True:
            raise ValueError("Recovery command did not confirm an authorized release rollback")
        _assert_compose_refs(compose_dir, project, {"api": prior_ids["api"], "ui": prior_ids["ui"]})
        if _run(["docker", "inspect", "--format", "{{.Image}}", _container_id(compose_dir, project, "api")]) != prior_ids["api"]:
            raise ValueError("Prior API image was not restored")
        if _run(["docker", "inspect", "--format", "{{.Image}}", _container_id(compose_dir, project, "ui")]) != prior_ids["ui"]:
            raise ValueError("Prior UI image was not restored")
        _assert_running_image(compose_dir, project, "api", prior_ids["api"])
        _assert_running_image(compose_dir, project, "ui", prior_ids["ui"])
        _assert_schema_head(compose_dir, project, prior_head, "Rollback migration")
        result["rollback_alembic_version"] = prior_head
        if not _tenant_workflow_exists(
            compose_dir, project, tenant_provider_id, tenant_workflow_uuid,
            baseline_workflow_name, case_id, "baseline",
        ) or _tenant_workflow_exists(
            compose_dir, project, tenant_provider_id, tenant_workflow_uuid,
            candidate_workflow_name, case_id, "candidate",
        ):
            raise ValueError("Rollback did not restore the tenant workflow data")
        if base64.b64decode(_object(compose_dir, project, object_base)) != baseline_object:
            raise ValueError("Rollback did not restore prior MinIO data selection")
        if _object_exists(compose_dir, project, object_candidate):
            raise ValueError("Rollback retained candidate-only MinIO data")
        _run(["docker", "exec", _container_id(compose_dir, project, "api"), "python", "-c",
              "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)"])
        result["authorized_release_and_volume_rollback"] = "passed"
        result["rollback_api_health"] = "passed"
        result["rollback_data_selection"] = "passed"
        completed_phases.append("rollback_release_and_data_verified")
        validate_flow_order(completed_phases)
        result["completed_phases"] = list(completed_phases)
        result["last_successful_phase"] = completed_phases[-1]
        result["status"] = "passed"
        return result
    except Exception as exc:
        _record_failure_diagnostics(result, active_phase, completed_phases, exc)
        raise
    finally:
        # A unique project name scopes Compose-created resources. Remove its
        # active recovery mapping first, then only the known initial volume set.
        recovery_volumes: list[str] = []
        state_path = compose_dir / ".client-recovery-state/state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                values = state.get("new_volumes", {})
                if isinstance(values, dict):
                    recovery_volumes.extend(value for value in values.values() if isinstance(value, str))
            except (OSError, ValueError, TypeError):
                cleanup_errors.append("recovery_state_unreadable")
        try:
            _compose(compose_dir, project, ["down", "--volumes", "--remove-orphans", "--timeout", "20"], timeout=120)
        except Exception as exc:  # keep attempting owned-resource cleanup
            cleanup_errors.append(type(exc).__name__)
        # Compose down normally handles these. Exact names were generated from
        # this unique project and recovery state, so retry only those volumes.
        for volume in sorted(set(original_volume_names + recovery_volumes)):
            try:
                removed = subprocess.run(["docker", "volume", "rm", volume], cwd=compose_dir, check=False, capture_output=True, text=True, timeout=30)
                if removed.returncode and "no such volume" not in (removed.stderr or "").casefold():
                    cleanup_errors.append("volume_cleanup_failed")
            except Exception:
                cleanup_errors.append("volume_cleanup_error")
        for image in images_to_remove:
            try:
                removed = subprocess.run(["docker", "image", "rm", "--force", image], cwd=ROOT, check=False, capture_output=True, text=True, timeout=60)
                if removed.returncode and "no such image" not in (removed.stderr or "").casefold():
                    cleanup_errors.append("image_cleanup_failed")
            except Exception:
                cleanup_errors.append("image_cleanup_error")
        try:
            containers = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
                cwd=ROOT, check=False, capture_output=True, text=True, timeout=30,
            )
            if containers.returncode:
                cleanup_errors.append("container_enumeration_failed")
            elif containers.stdout.strip():
                removed = subprocess.run(["docker", "rm", "--force", *containers.stdout.split()], cwd=ROOT,
                                         check=False, capture_output=True, text=True, timeout=60)
                if removed.returncode:
                    cleanup_errors.append("container_cleanup_failed")
        except Exception:
            cleanup_errors.append("container_cleanup_error")
        try:
            network = subprocess.run(["docker", "network", "rm", f"{project}_internal"], cwd=ROOT,
                                     check=False, capture_output=True, text=True, timeout=30)
            if network.returncode and "no such network" not in (network.stderr or "").casefold():
                cleanup_errors.append("network_cleanup_failed")
        except Exception:
            cleanup_errors.append("network_cleanup_error")
        if not _remove_temp_directory(temp_root):
            cleanup_errors.append("temporary_secrets_directory_cleanup_failed")
        # Write the report only after checking that temporary private keys,
        # license data, backup and .env have actually been removed.
        result.setdefault("completed_phases", list(completed_phases))
        result.setdefault("last_successful_phase", completed_phases[-1] if completed_phases else None)
        result["cleanup"] = "passed" if not cleanup_errors else "failed"
        if cleanup_errors:
            result["status"] = "failed"
            result["cleanup_error_types"] = sorted(set(cleanup_errors))
            result.setdefault("failed_phase", "cleanup")
            result.setdefault("failure_type", "CleanupError")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _ancestor_revisions(source: Path) -> set[str]:
    revisions: dict[str, tuple[str, ...]] = {}
    for migration in sorted((source / "api/alembic/versions").glob("*.py")):
        values: dict[str, Any] = {}
        for node in ast.parse(migration.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        values[target.id] = ast.literal_eval(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in {"revision", "down_revision"}:
                values[node.target.id] = ast.literal_eval(node.value)
        revision, down = values.get("revision"), values.get("down_revision")
        if isinstance(revision, str):
            revisions[revision] = (down,) if isinstance(down, str) else tuple(down or ())
    found: set[str] = set()
    def visit(revision: str) -> None:
        if revision in found:
            return
        found.add(revision)
        for parent in revisions.get(revision, ()):
            visit(parent)
    visit(_migration_head(source))
    return found


def _container_id(compose_dir: Path, project: str, service: str) -> str:
    return _compose(compose_dir, project, ["ps", "--quiet", service]).splitlines()[-1]


def _object_exists(compose_dir: Path, project: str, name: str) -> bool:
    return _object(compose_dir, project, name) != "missing"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run fast Docker-free input and flow-order checks")
    parser.add_argument("--prior-commit")
    parser.add_argument("--prior-source", type=Path)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--coturn-image")
    parser.add_argument("--caddy-image")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            print("Lifecycle helper checks passed")
            return 0
        required = ("prior_commit", "prior_source", "candidate_commit", "coturn_image", "caddy_image", "report")
        missing = [name for name in required if getattr(args, name) is None]
        if missing:
            parser.error("required unless --self-test: " + ", ".join("--" + name.replace("_", "-") for name in missing))
        result = run(args)
        print(json.dumps({"status": result["status"], "report": str(Path(args.report).resolve())}))
        return 0 if result["status"] == "passed" else 1
    except Exception as exc:
        # The evidence file is written by run()'s finally path once execution
        # has started. Keep the console failure generic to avoid secret leaks.
        # Exception text can contain synthetic credentials, URLs, SQL values,
        # or service output. Keep CI logs free of those values by emitting only
        # the exception class; the evidence artifact is already redacted too.
        print(_format_failure_message(args.report, exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
