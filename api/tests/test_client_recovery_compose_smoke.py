"""Opt-in disposable Compose exercise for client volume recovery.

This uses real Docker volumes but only in a UUID-named synthetic project. The
API/UI names are sleeping stand-ins; this is not full client installation,
upgrade, telephony, owner, or production disaster-recovery acceptance.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = ROOT / "deploy/client"
sys.path.insert(0, str(CLIENT_DIR))
import recovery  # noqa: E402

OPT_IN = "KODEWAVES_RUN_DISPOSABLE_COMPOSE_RECOVERY"
IMAGE_ENV = {
    "postgres": "KW_RECOVERY_SMOKE_POSTGRES_IMAGE",
    "minio": "KW_RECOVERY_SMOKE_MINIO_IMAGE",
    "s3_client": "KW_RECOVERY_SMOKE_S3_CLIENT_IMAGE",
}
MAX_MEMORY = "256m"
MAX_CPU = "0.25"
MAX_PIDS = "64"


def _run(command: list[str], *, cwd: Path, timeout: int = 180) -> str:
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Disposable recovery smoke command failed ({result.returncode}): {command[:8]}"
        )
    return result.stdout.strip()


def _compose_command(directory: Path, project: str, env_file: Path) -> list[str]:
    return [
        "docker", "compose", "--project-directory", str(directory),
        "--project-name", project, "--env-file", str(env_file),
        "-f", str(directory / "docker-compose.client.yaml"),
        "-f", str(directory / "docker-compose.identity.yaml"),
        "-f", str(directory / "docker-compose.recovery.yaml"),
    ]


def _write_project(directory: Path, project: str, images: dict[str, str]) -> tuple[Path, Path, Path, Path, Path]:
    env_file = directory / ".env"
    manifest = directory / "client-release-manifest.json"
    public_key = directory / "release-public-key.txt"
    archive = directory / "recovery-smoke.tar.gz"
    postgres_image = images["postgres"]
    minio_image = images["minio"]
    api_ref = "registry.invalid/recovery-smoke/api@sha256:" + "a" * 64
    ui_ref = "registry.invalid/recovery-smoke/ui@sha256:" + "b" * 64
    compose = f"""services:
  postgres:
    image: ${{CLIENT_POSTGRES_IMAGE:?}}
    pull_policy: never
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:?}}
      POSTGRES_DB: postgres
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: [CMD-SHELL, pg_isready -U postgres]
      interval: 2s
      timeout: 2s
      retries: 40
    mem_limit: {MAX_MEMORY}
    cpus: {MAX_CPU}
    pids_limit: {MAX_PIDS}
    networks: [private]
  minio:
    image: ${{CLIENT_MINIO_IMAGE:?}}
    pull_policy: never
    command: [server, /data, --console-address, ":9001"]
    environment:
      MINIO_ROOT_USER: recovery-smoke-user
      MINIO_ROOT_PASSWORD: {"m" * 40}
    volumes: [minio_data:/data]
    mem_limit: {MAX_MEMORY}
    cpus: {MAX_CPU}
    pids_limit: {MAX_PIDS}
    networks: [private]
  redis:
    image: ${{CLIENT_POSTGRES_IMAGE:?}}
    pull_policy: never
    entrypoint: [/bin/sh, -c]
    command: [sleep 3600]
    volumes: [redis_data:/data]
    mem_limit: 64m
    cpus: 0.1
    pids_limit: 32
    networks: [private]
  api:
    image: ${{CLIENT_POSTGRES_IMAGE:?}}
    pull_policy: never
    entrypoint: [/bin/sh, -c]
    command: [sleep 3600]
    mem_limit: 64m
    cpus: 0.1
    pids_limit: 32
    networks: [private]
  ui:
    image: ${{CLIENT_POSTGRES_IMAGE:?}}
    pull_policy: never
    entrypoint: [/bin/sh, -c]
    command: [sleep 3600]
    mem_limit: 64m
    cpus: 0.1
    pids_limit: 32
    networks: [private]
volumes:
  postgres_data:
  minio_data:
  redis_data:
networks:
  private:
    internal: true
"""
    (directory / "docker-compose.client.yaml").write_text(compose, encoding="utf-8")
    # Empty overlay for normal, un-restored startup. recovery.py replaces it
    # temporarily with external references to uniquely named test volumes.
    (directory / "docker-compose.identity.yaml").write_text("services: {}\n", encoding="utf-8")
    (directory / recovery.RECOVERY_OVERRIDE).write_text("{}\n", encoding="utf-8")
    values = {
        "COMPOSE_PROJECT_NAME": project,
        "COMPOSE_PROFILES": "",
        "CLIENT_API_IMAGE": api_ref,
        "CLIENT_UI_IMAGE": ui_ref,
        "CLIENT_POSTGRES_IMAGE": postgres_image,
        "CLIENT_MINIO_IMAGE": minio_image,
        "CLIENT_REDIS_IMAGE": postgres_image,
        "CLIENT_COTURN_IMAGE": postgres_image,
        "CLIENT_CADDY_IMAGE": postgres_image,
        "CLIENT_RELEASE_MANIFEST_FILE": "./client-release-manifest.json",
        "KODEWAVES_INSTALLATION_ID": "recovery-smoke-" + uuid.uuid4().hex[:12],
        "KODEWAVES_LICENSE_TOKEN": "disposable-smoke-license.signature",
        "CLIENT_IDENTITY_KEY_FILE": "",
        "CLIENT_IDENTITY_GID": "",
        "POSTGRES_PASSWORD": "p" * 40,
        "MINIO_ROOT_USER": "recovery-smoke-user",
        "MINIO_ROOT_PASSWORD": "m" * 40,
    }
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    env_file.chmod(0o600)
    manifest.write_text(json.dumps({"payload": {
        "edition": "client",
        "images": {"api": {"reference": api_ref}, "ui": {"reference": ui_ref}},
    }}), encoding="utf-8")
    public_key.write_text("disposable recovery smoke public key\n", encoding="ascii")
    return env_file, manifest, public_key, archive, directory / recovery.RECOVERY_OVERRIDE


def _pg_value(directory: Path, project: str, env_file: Path) -> str:
    command = _compose_command(directory, project, env_file)
    return _run([
        *command, "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "postgres",
        "-At", "-c", "SELECT value FROM recovery_smoke WHERE id = 'only-row'",
    ], cwd=directory)


def _pg_seed(directory: Path, project: str, env_file: Path, value: str) -> None:
    command = _compose_command(directory, project, env_file)
    _run([
        *command, "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "postgres",
        "-v", "ON_ERROR_STOP=1", "-c",
        "CREATE TABLE IF NOT EXISTS recovery_smoke (id text PRIMARY KEY, value text NOT NULL); "
        f"INSERT INTO recovery_smoke VALUES ('only-row', '{value}') "
        "ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value",
    ], cwd=directory)


def _minio_value(directory: Path, project: str, image: str, value: str, *, write: bool) -> str:
    code = [
        "import io, time",
        "from minio import Minio",
        "client = Minio('minio:9000', access_key='recovery-smoke-user', "
        f"secret_key={'m' * 40!r}, secure=False)",
        "bucket = 'recovery-smoke'",
        f"payload = {value!r}",
        "for attempt in range(45):",
        "    try:",
        "        if not client.bucket_exists(bucket):",
        "            client.make_bucket(bucket)",
    ]
    if write:
        code.append("        client.put_object(bucket, 'object.bin', io.BytesIO(payload.encode()), len(payload))")
    code.extend([
        "        response = client.get_object(bucket, 'object.bin')",
        "        actual = response.read().decode()",
        "        response.close()",
        "        response.release_conn()",
        "        if actual != payload:",
        "            raise AssertionError('MinIO object content mismatch')",
        "        print(actual)",
        "        break",
        "    except Exception:",
        "        if attempt == 44:",
        "            raise",
        "        time.sleep(1)",
    ])
    return _run([
        "docker", "run", "--rm", "--pull=never", "--network", f"{project}_private",
        "--memory=256m", "--cpus=0.25", "--pids-limit=64", "--entrypoint", "python",
        image, "-c", "\n".join(code),
    ], cwd=directory, timeout=90)


def _cleanup_owned_volumes(directory: Path) -> None:
    states = [directory / recovery.RECOVERY_STATE_DIR / "state.json", *directory.glob(".client-recovery-*/state.json")]
    for state_path in states:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            recovery._remove_owned_recovery_volumes(
                list(set(state.get("created_volumes", [])) | set(state.get("new_volumes", {}).values())),
                directory,
                state["restore_id"],
            )
        except FileNotFoundError:
            continue


@pytest.mark.skipif(
    os.getenv(OPT_IN) != "1",
    reason=f"set {OPT_IN}=1 to run Docker-backed recovery against disposable resources",
)
def test_disposable_compose_cold_backup_restore_and_rollback(tmp_path: Path) -> None:
    images = {name: os.getenv(env_name, "").strip() for name, env_name in IMAGE_ENV.items()}
    missing = [env_name for name, env_name in IMAGE_ENV.items() if not images[name]]
    if missing:
        pytest.fail("Explicit smoke opt-in requires locally available image values: " + ", ".join(missing))
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", images["postgres"]):
        pytest.fail(f"{IMAGE_ENV['postgres']} must be an immutable digest reference")

    project = "kw-recovery-smoke-" + uuid.uuid4().hex[:12]
    directory = tmp_path / project
    directory.mkdir(mode=0o700)
    env_file, manifest, public_key, archive, _override = _write_project(directory, project, images)
    project_claimed = False
    try:
        for image in images.values():
            _run(["docker", "image", "inspect", image], cwd=directory)
        # Verify the S3 client is already available locally before starting any service.
        _run([
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--memory=128m", "--cpus=0.1", "--pids-limit=32", "--entrypoint", "python",
            images["s3_client"], "-c", "import minio",
        ], cwd=directory, timeout=60)

        compose = _compose_command(directory, project, env_file)
        model = json.loads(_run([*compose, "config", "--format", "json"], cwd=directory))
        assert model["name"] == project
        assert model["networks"]["private"]["internal"] is True
        assert set(model["volumes"]) == {"postgres_data", "minio_data", "redis_data"}
        assert all(not service.get("ports") for service in model["services"].values())
        assert all(not volume.get("external") for volume in model["volumes"].values())
        assert all(service.get("pull_policy") == "never" for service in model["services"].values())
        assert all(not service.get("build") for service in model["services"].values())
        assert all(
            mount.get("type") == "volume" and mount.get("source") in model["volumes"]
            for service in model["services"].values()
            for mount in service.get("volumes", [])
        )
        for service in model["services"].values():
            assert int(service["mem_limit"]) <= 256 * 1024 * 1024
            assert float(service["cpus"]) <= 0.25
        assert max(int(model["services"][name]["pids_limit"]) for name in ("postgres", "minio")) <= 64
        configured_volumes = recovery._compose_volume_names(model)
        assert all(name.startswith(project + "_") for name in configured_volumes.values())

        existing = _run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], cwd=directory)
        existing_volumes = _run(["docker", "volume", "ls", "-q", "--filter", f"name={project}_"], cwd=directory)
        existing_networks = _run(["docker", "network", "ls", "-q", "--filter", f"name={project}_"], cwd=directory)
        if existing or existing_volumes or existing_networks:
            pytest.fail("UUID test project unexpectedly collides with existing Docker resources")
        # From here, all project-scoped resources can only belong to this run.
        # A collision failure above must never call Compose down on another project.
        project_claimed = True
        _run([*compose, "up", "--detach", "--wait", "--wait-timeout", "90", "--pull", "never"], cwd=directory, timeout=150)
        original_volumes = recovery._compose_volume_names(
            json.loads(_run([*compose, "config", "--format", "json"], cwd=directory))
        )

        _pg_seed(directory, project, env_file, "before-backup")
        assert _pg_value(directory, project, env_file) == "before-backup"
        assert _minio_value(directory, project, images["s3_client"], "before-backup", write=True) == "before-backup"

        backup = recovery.create_docker_backup(
            compose_dir=directory, env_file=env_file, output=archive,
            release_public_key=public_key, confirm_maintenance=True,
        )
        assert backup["status"] == "created"
        assert set(backup["services_restarted"]) == {"api", "ui", "postgres", "minio", "redis"}
        _pg_seed(directory, project, env_file, "after-backup")
        assert _minio_value(directory, project, images["s3_client"], "after-backup", write=True) == "after-backup"

        restored = recovery.restore_to_docker_volumes(
            archive_path=archive, compose_dir=directory, env_file=env_file,
            release_public_key=public_key,
            confirm_maintenance=True,
        )
        assert restored["status"] == "restored_to_new_volumes"
        assert all(name.startswith(project + "_") for name in restored["new_volumes"].values())
        selected = recovery._compose_volume_names(
            json.loads(_run([*compose, "config", "--format", "json"], cwd=directory))
        )
        assert selected["postgres_data"] == restored["new_volumes"]["postgres_data"]
        assert _pg_value(directory, project, env_file) == "before-backup"
        assert _minio_value(directory, project, images["s3_client"], "before-backup", write=False) == "before-backup"

        rolled_back = recovery.rollback_docker_restore(
            compose_dir=directory, env_file=env_file, confirm_maintenance=True,
        )
        assert rolled_back["status"] == "rolled_back"
        selected = recovery._compose_volume_names(
            json.loads(_run([*compose, "config", "--format", "json"], cwd=directory))
        )
        assert selected["postgres_data"] == original_volumes["postgres_data"]
        assert _pg_value(directory, project, env_file) == "after-backup"
        assert _minio_value(directory, project, images["s3_client"], "after-backup", write=False) == "after-backup"
    finally:
        if project_claimed:
            compose = _compose_command(directory, project, env_file)
            down = subprocess.run(
                [*compose, "down", "--volumes", "--remove-orphans", "--timeout", "10"],
                cwd=directory, capture_output=True, text=True, timeout=60, check=False,
            )
            _cleanup_owned_volumes(directory)
            assert down.returncode == 0, "Disposable Compose cleanup failed; inspect only this generated test project"
            assert not _run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"], cwd=directory)
            assert not _run(["docker", "volume", "ls", "-q", "--filter", f"name={project}_"], cwd=directory)
            assert not _run(["docker", "network", "ls", "-q", "--filter", f"name={project}_"], cwd=directory)

