#!/usr/bin/env python3
"""Create, validate and stage offline client recovery sets.

Archive format (tar.gz): recovery.json, SHA256SUMS, volumes/postgres.tar,
volumes/minio.tar, config/.env, config/client-release-manifest.json, and an
optional config/installation.key. `create` only packages already-exported cold
volume tar files after explicit operator attestation. `restore` extracts into a
new offline directory; it never writes Docker volumes or modifies an install.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_install import parse_env

REQUIRED_FILES = {
    "recovery.json",
    "SHA256SUMS",
    "volumes/postgres.tar",
    "volumes/minio.tar",
    "config/.env",
    "config/client-release-manifest.json",
    "config/release-public-key.txt",
}
OPTIONAL_FILES = {"config/installation.key"}
MAX_FILE_SIZE = 512 * 1024 * 1024 * 1024
MAX_METADATA_SIZE = 1024 * 1024
MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
HASH_CHUNK_SIZE = 1024 * 1024
MAX_DOCKER_TIMEOUT = 3600
RECOVERY_OVERRIDE = "docker-compose.recovery.yaml"
RECOVERY_STATE_DIR = ".client-recovery-state"
RECOVERY_LOCK_FILE = ".client-recovery-operation.lock"


@contextmanager
def _recovery_operation_lock(compose_dir: Path):
    """Serialize backup/restore/rollback across processes without stale locks."""
    compose_dir = compose_dir.resolve(strict=True)
    lock_path = compose_dir / RECOVERY_LOCK_FILE
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name or "\\" in name or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != name
    ):
        raise ValueError(f"Unsafe recovery archive path: {name!r}")


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo, limit: int) -> bytes:
    if not member.isfile() or member.issym() or member.islnk():
        raise ValueError(f"Recovery archive entry must be a regular file: {member.name}")
    if member.size < 0 or member.size > limit:
        raise ValueError(f"Recovery archive entry has an invalid size: {member.name}")
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"Unable to read recovery archive entry: {member.name}")
    content = stream.read(limit + 1)
    if len(content) != member.size:
        raise ValueError(f"Recovery archive entry size mismatch: {member.name}")
    return content


def _hash_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    """Hash a potentially large volume archive without loading it into memory."""
    if not member.isfile() or member.size < 0 or member.size > MAX_FILE_SIZE:
        raise ValueError(f"Recovery volume snapshot has an invalid size: {member.name}")
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"Unable to read recovery archive entry: {member.name}")
    digest = hashlib.sha256()
    total = 0
    while chunk := stream.read(HASH_CHUNK_SIZE):
        total += len(chunk)
        if total > member.size:
            raise ValueError(f"Recovery archive entry size mismatch: {member.name}")
        digest.update(chunk)
    if total != member.size:
        raise ValueError(f"Recovery archive entry size mismatch: {member.name}")
    return digest.hexdigest()


def _validate_nested_tar(stream, outer_name: str) -> None:
    """Reject unsafe filesystem entries before a restore tool may unpack a volume."""
    try:
        nested = tarfile.open(fileobj=stream, mode="r|*")
    except (tarfile.TarError, OSError) as exc:
        raise ValueError(f"Invalid nested volume tar: {outer_name}") from exc
    with nested:
        count = 0
        total_size = 0
        seen: set[str] = set()
        for member in nested:
            count += 1
            if count > MAX_ARCHIVE_MEMBERS * 100:
                raise ValueError(f"Nested volume archive has too many entries: {outer_name}")
            name = member.name
            normalized = name[2:] if name.startswith("./") else name
            if normalized in {"", "."}:
                if member.isdir():
                    continue
                raise ValueError(f"Invalid nested volume entry: {name!r}")
            _validate_member_name(normalized)
            if normalized in seen:
                raise ValueError(f"Duplicate nested volume entry: {name!r}")
            seen.add(normalized)
            if member.size < 0 or member.size > MAX_FILE_SIZE:
                raise ValueError(f"Nested volume entry has an invalid size: {name!r}")
            total_size += member.size
            if total_size > MAX_ARCHIVE_SIZE:
                raise ValueError(f"Nested volume archive exceeds the size limit: {outer_name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Nested volume archive links/devices are unsupported: {name!r}")


def _apply_archive_owner_mode(path: Path, member: tarfile.TarInfo) -> None:
    if os.name == "nt":
        path.chmod(member.mode & 0o777)
        return
    if os.geteuid() == 0:
        os.chown(path, member.uid, member.gid)
    elif member.uid != os.getuid() or member.gid not in {*os.getgroups(), os.getgid()}:
        raise ValueError(
            "Staged volume ownership requires root privileges; rerun restore with an operator account allowed to preserve UID/GID"
        )
    path.chmod(member.mode & 0o777)


def _extract_nested_volume(stream, target_root: Path, outer_name: str) -> None:
    directories: list[tuple[Path, tarfile.TarInfo]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(fileobj=stream, mode="r|*") as nested:
            for member in nested:
                name = member.name
                normalized = name[2:] if name.startswith("./") else name
                if normalized in {"", "."} and member.isdir():
                    directories.append((target_root, member))
                    continue
                _validate_member_name(normalized)
                if normalized in seen:
                    raise ValueError(f"Duplicate nested volume entry: {name!r}")
                seen.add(normalized)
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"Nested volume archive links/devices are unsupported: {name!r}")
                target = target_root.joinpath(*PurePosixPath(normalized).parts)
                if not target.resolve(strict=False).is_relative_to(target_root.resolve()):
                    raise ValueError(f"Unsafe nested volume path: {name!r}")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    directories.append((target, member))
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = nested.extractfile(member)
                if source is None:
                    raise ValueError(f"Unable to read nested volume file: {name}")
                with target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, length=HASH_CHUNK_SIZE)
                _apply_archive_owner_mode(target, member)
        for directory, member in reversed(directories):
            _apply_archive_owner_mode(directory, member)
    except (OSError, tarfile.TarError) as exc:
        raise ValueError(f"Unable to stage nested {outer_name} data") from exc


def _nested_expanded_size(stream, outer_name: str) -> int:
    total = 0
    try:
        with tarfile.open(fileobj=stream, mode="r|*") as nested:
            count = 0
            for member in nested:
                count += 1
                if count > MAX_ARCHIVE_MEMBERS * 100:
                    raise ValueError(f"Nested {outer_name} archive has too many entries")
                name = member.name
                normalized = name[2:] if name.startswith("./") else name
                if normalized in {"", "."} and member.isdir():
                    continue
                _validate_member_name(normalized)
                if not (member.isfile() or member.isdir()):
                    raise ValueError(f"Nested {outer_name} links/devices are unsupported")
                if member.size < 0 or member.size > MAX_FILE_SIZE:
                    raise ValueError(f"Nested {outer_name} entry has invalid size")
                total += member.size
                if total > MAX_ARCHIVE_SIZE:
                    raise ValueError(f"Nested {outer_name} exceeds the expanded size limit")
    except (OSError, tarfile.TarError) as exc:
        raise ValueError(f"Invalid nested {outer_name} tar archive") from exc
    return total


def _env_value(content: bytes, key: str) -> str | None:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("Archived .env must be UTF-8") from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _check_regular_file(path: Path, description: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ValueError(f"{description} is unavailable") from exc
    if not stat.S_ISREG(mode):
        raise ValueError(f"{description} must be a regular file, not a symlink")


def _check_nested_tar_file(path: Path, description: str) -> None:
    _check_regular_file(path, description)
    if path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError(f"{description} exceeds the supported size limit")
    try:
        with tarfile.open(path, mode="r:*") as nested:
            count = 0
            total_size = 0
            seen: set[str] = set()
            for member in nested:
                count += 1
                if count > MAX_ARCHIVE_MEMBERS * 100:
                    raise ValueError(f"{description} contains too many entries")
                name = member.name
                normalized = name[2:] if name.startswith("./") else name
                if normalized in {"", "."} and member.isdir():
                    continue
                _validate_member_name(normalized)
                if normalized in seen:
                    raise ValueError(f"{description} contains duplicate paths")
                seen.add(normalized)
                if member.size < 0 or member.size > MAX_FILE_SIZE:
                    raise ValueError(f"{description} contains an invalid member size")
                total_size += member.size
                if total_size > MAX_ARCHIVE_SIZE:
                    raise ValueError(f"{description} exceeds the uncompressed size limit")
                if not (member.isfile() or member.isdir()):
                    raise ValueError(
                        f"{description} contains links/devices; Postgres tablespace links require owner-assisted backup"
                    )
    except (OSError, tarfile.TarError) as exc:
        raise ValueError(f"{description} is not a valid tar archive") from exc


def create_archive(
    *, postgres_tar: Path, minio_tar: Path, env_file: Path, manifest: Path,
    release_public_key: Path, output: Path, identity_key: Path | None,
    writers_stopped: bool,
) -> dict[str, object]:
    """Package pre-exported offline snapshots; no Docker or live-volume writes."""
    if not writers_stopped:
        raise ValueError("Refusing snapshot: confirm the maintenance window and stopped writers")
    sources = {
        "volumes/postgres.tar": postgres_tar,
        "volumes/minio.tar": minio_tar,
        "config/.env": env_file,
        "config/client-release-manifest.json": manifest,
        "config/release-public-key.txt": release_public_key,
    }
    if identity_key is not None:
        sources["config/installation.key"] = identity_key
    resolved_inputs: dict[str, Path] = {}
    for archive_name, source in sources.items():
        _check_regular_file(source, archive_name)
        resolved_inputs[archive_name] = source.resolve(strict=True)
    if output.exists():
        raise ValueError("Recovery archive already exists; refusing to overwrite")
    output_resolved = output.resolve(strict=False)
    if output_resolved in resolved_inputs.values():
        raise ValueError("Recovery archive output cannot replace an input file")
    _check_nested_tar_file(resolved_inputs["volumes/postgres.tar"], "Postgres snapshot")
    _check_nested_tar_file(resolved_inputs["volumes/minio.tar"], "MinIO snapshot")

    env_bytes = resolved_inputs["config/.env"].read_bytes()
    installation_id = _env_value(env_bytes, "KODEWAVES_INSTALLATION_ID")
    if not isinstance(installation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", installation_id):
        raise ValueError("Archived .env must include a valid KODEWAVES_INSTALLATION_ID")
    key_path = _env_value(env_bytes, "CLIENT_IDENTITY_KEY_FILE")
    configured_gid = _env_value(env_bytes, "CLIENT_IDENTITY_GID")
    if bool(key_path) != bool(identity_key):
        raise ValueError("Identity key input must match CLIENT_IDENTITY_KEY_FILE in the archived .env")
    identity_gid = None
    identity_uid = None
    identity_mode = None
    if identity_key is not None:
        try:
            identity_gid = int(configured_gid or "")
        except ValueError as exc:
            raise ValueError("Archived .env must include a numeric CLIENT_IDENTITY_GID") from exc
        identity_stat = identity_key.stat()
        identity_uid = getattr(identity_stat, "st_uid", 0)
        if identity_key.stat().st_size != 32:
            raise ValueError("Installation identity key must contain exactly 32 bytes")
        if os.name != "nt" and (
            identity_stat.st_gid != identity_gid or identity_stat.st_mode & 0o777 != 0o640
        ):
            raise ValueError("Identity key must have the configured group and 0640 permissions")
        identity_mode = 0o640

    manifest_bytes = resolved_inputs["config/client-release-manifest.json"].read_bytes()
    try:
        manifest_json = json.loads(manifest_bytes)
        payload = manifest_json["payload"]
        manifest_images = payload["images"]
        env_api = _env_value(env_bytes, "CLIENT_API_IMAGE")
        env_ui = _env_value(env_bytes, "CLIENT_UI_IMAGE")
        if (
            payload.get("edition") != "client"
            or manifest_images["api"].get("reference") != env_api
            or manifest_images["ui"].get("reference") != env_ui
        ):
            raise ValueError("Archived .env images do not match the signed release manifest")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Archived release manifest does not identify the configured API/UI images") from exc

    license_token = _env_value(env_bytes, "KODEWAVES_LICENSE_TOKEN") or ""
    metadata = {
        "format": "kodewaves-client-recovery-v1",
        "snapshot_mode": "cold",
        "writers_stopped": True,
        "redis_included": False,
        "installation_id": installation_id,
        "license_sha256": hashlib.sha256(license_token.encode()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "api_image": env_api,
        "ui_image": env_ui,
        "identity_gid": identity_gid,
        "identity_uid": identity_uid,
        "identity_mode": identity_mode,
    }
    contents: dict[str, bytes] = {
        "recovery.json": (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode(),
    }
    for name, source in resolved_inputs.items():
        if name.startswith("volumes/"):
            continue
        contents[name] = source.read_bytes()
    checksum_lines = []
    for name, content in sorted(contents.items()):
        checksum = hashlib.sha256(content).hexdigest()
        checksum_lines.append(f"{checksum}  {name}\n")
    for name in ("volumes/minio.tar", "volumes/postgres.tar"):
        checksum_lines.append(f"{_sha256_file(resolved_inputs[name])}  {name}\n")
    contents["SHA256SUMS"] = "".join(sorted(checksum_lines)).encode("ascii")

    output.parent.mkdir(parents=True, exist_ok=True)
    created_output = False
    try:
        with output.open("xb") as raw:
            created_output = True
            if os.name != "nt":
                os.chmod(output, 0o600)
            with tarfile.open(fileobj=raw, mode="w:gz", compresslevel=1, format=tarfile.PAX_FORMAT) as archive:
                for name, content in sorted(contents.items()):
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    member.mode = 0o640 if name == "config/installation.key" else 0o600 if name == "config/.env" else 0o644
                    if name == "config/installation.key":
                        member.gid = identity_gid
                        member.uid = identity_uid
                    archive.addfile(member, io.BytesIO(content))
                for name in ("volumes/minio.tar", "volumes/postgres.tar"):
                    source_path = resolved_inputs[name]
                    member = tarfile.TarInfo(name)
                    member.size = source_path.stat().st_size
                    member.mode = 0o600
                    with source_path.open("rb") as source:
                        archive.addfile(member, source)
        return {"status": "created", "archive": str(output), **metadata}
    except Exception:
        if created_output:
            output.unlink(missing_ok=True)
        raise


def _run(command: list[str], *, cwd: Path, timeout: int = 120) -> str:
    configured: set[str] = set()
    if command[:2] == ["docker", "compose"] and "--env-file" in command:
        env_index = command.index("--env-file")
        if env_index + 1 < len(command):
            configured = set(parse_env(Path(command[env_index + 1])))
    command_env = {
        key: value for key, value in os.environ.items()
        if key not in configured and key not in {
            "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "COMPOSE_FILE",
            "COMPOSE_ENV_FILES", "COMPOSE_PATH_SEPARATOR",
        }
    }
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False, env=command_env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Recovery command could not complete: {command[0]} {command[1]}") from exc
    if result.returncode:
        raise RuntimeError(
            f"Recovery command failed: {Path(command[0]).name} {command[1]} (exit {result.returncode})"
        )
    return result.stdout.strip()


def _compose_context(compose_dir: Path, env_file: Path) -> tuple[list[str], dict[str, object], dict[str, str]]:
    compose_dir = compose_dir.resolve(strict=True)
    env_file = env_file.resolve(strict=True)
    env = parse_env(env_file)
    compose_files = ["docker-compose.client.yaml"]
    if env.get("CLIENT_IDENTITY_KEY_FILE"):
        compose_files.append("docker-compose.identity.yaml")
    compose_files.append(RECOVERY_OVERRIDE)
    from compose_client import _project_name

    project_name = _project_name(compose_dir, env)
    for name in compose_files:
        path = compose_dir / name
        if not path.is_file():
            raise ValueError(f"Compose file is missing: {name}")
    command = [
        "docker", "compose", "--project-directory", str(compose_dir),
        "--project-name", project_name, "--env-file", str(env_file),
    ]
    for name in compose_files:
        command.extend(("-f", str(compose_dir / name)))
    rendered = json.loads(_run([*command, "config", "--format", "json"], cwd=compose_dir))
    return command, rendered, env


def _running_services(compose_command: list[str], compose_dir: Path, services: set[str]) -> list[str]:
    output = _run(
        [*compose_command, "ps", "--services", "--status", "running"],
        cwd=compose_dir,
    )
    running = sorted(set(output.splitlines()) & services)
    return running


def _compose_volume_names(compose_model: dict[str, object]) -> dict[str, str]:
    volumes = compose_model.get("volumes")
    if not isinstance(volumes, dict):
        raise ValueError("Compose configuration does not declare named volumes")
    resolved = {}
    for logical_name in ("postgres_data", "minio_data", "redis_data"):
        item = volumes.get(logical_name)
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise ValueError(f"Compose did not resolve the {logical_name} volume name")
        resolved[logical_name] = item["name"]
    return resolved


def _atomic_write(path: Path, content: bytes, *, mode: int | None = None) -> None:
    existing = path.stat() if path.exists() else None
    if mode is None:
        mode = stat.S_IMODE(existing.st_mode) if existing else 0o600
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
            if os.name != "nt":
                os.fchmod(destination.fileno(), mode)
                if existing is not None and os.geteuid() == 0:
                    os.fchown(destination.fileno(), existing.st_uid, existing.st_gid)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _update_env_value(content: bytes, key: str, value: str) -> bytes:
    text = content.decode("utf-8")
    lines = text.splitlines(keepends=True)
    replaced = False
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" in line and line.split("=", 1)[0].strip() == key:
            ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
            lines[index] = f"{key}={value}{ending}"
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    return "".join(lines).encode("utf-8")


def _recovery_override(volume_names: dict[str, str]) -> bytes:
    selected = {
        logical: {"external": True, "name": name}
        for logical, name in volume_names.items()
    }
    return (json.dumps({"volumes": selected}, sort_keys=True, indent=2) + "\n").encode()


def _get_volume_image(env: dict[str, str]) -> str:
    image = env.get("CLIENT_POSTGRES_IMAGE", "")
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", image):
        raise ValueError("CLIENT_POSTGRES_IMAGE must be an approved immutable digest for safe volume operations")
    return image


def _docker_volume_exists(name: str, compose_dir: Path) -> bool:
    result = subprocess.run(
        ["docker", "volume", "inspect", name], cwd=compose_dir,
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode == 0:
        return True
    if "no such volume" in (result.stderr or "").lower():
        return False
    raise RuntimeError("Docker volume availability could not be checked safely")


def _assert_no_running_volume_consumers(names: list[str], compose_dir: Path) -> None:
    for name in names:
        output = _run(
            ["docker", "ps", "--quiet", "--filter", f"volume={name}"],
            cwd=compose_dir,
        )
        if output:
            raise ValueError(
                f"Refusing a cold snapshot: one or more running containers still mount volume {name}"
            )


def _create_volume(name: str, compose_dir: Path, recovery_id: str) -> None:
    if _docker_volume_exists(name, compose_dir):
        raise ValueError(f"Recovery volume already exists; refusing to reuse: {name}")
    _run(
        ["docker", "volume", "create", "--label", f"com.kodewaves.recovery={recovery_id}", name],
        cwd=compose_dir,
    )


def _remove_owned_recovery_volumes(names: list[str], compose_dir: Path, recovery_id: str) -> list[str]:
    """Remove only volumes whose recovery label proves this run created them."""
    removed: list[str] = []
    for name in names:
        result = subprocess.run(
            ["docker", "volume", "inspect", name], cwd=compose_dir,
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode:
            if "no such volume" in (result.stderr or "").lower():
                continue
            raise RuntimeError(f"Could not verify recovery volume ownership: {name}")
        try:
            inspected = json.loads(result.stdout)
            labels = inspected[0].get("Labels") or {}
        except (ValueError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError(f"Could not verify recovery volume ownership: {name}") from exc
        if labels.get("com.kodewaves.recovery") != recovery_id:
            raise RuntimeError(f"Refusing to remove a volume without this recovery label: {name}")
        _run(["docker", "volume", "rm", name], cwd=compose_dir)
        removed.append(name)
    return removed


def _volume_tar_command(
    *, image: str, volume_name: str, host_directory: Path, archive_name: str,
    compose_dir: Path, extract: bool,
) -> None:
    source_path = host_directory / archive_name
    if extract:
        cmd = (
            "set -eu; command -v tar >/dev/null; "
            f"tar --numeric-owner -C /target -xf /snapshot/{archive_name}"
        )
        mounts = [
            "type=volume,src=" + volume_name + ",dst=/target",
            "type=bind,src=" + str(host_directory.resolve()) + ",dst=/snapshot,readonly",
        ]
    else:
        cmd = (
            "set -eu; command -v tar >/dev/null; "
            f"tar --numeric-owner -C /source -cf /snapshot/{archive_name} ."
        )
        mounts = [
            "type=volume,src=" + volume_name + ",dst=/source,readonly",
            "type=bind,src=" + str(host_directory.resolve()) + ",dst=/snapshot",
        ]
    command = [
        "docker", "run", "--rm", "--pull=never", "--network=none", "--user=0:0",
        "--entrypoint", "/bin/sh",
    ]
    for mount in mounts:
        command.extend(("--mount", mount))
    command.extend((image, "-ec", cmd))
    _run(command, cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)


def _restart_services(compose_command: list[str], compose_dir: Path, services: list[str]) -> None:
    if services:
        _run([*compose_command, "start", *services], cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)


def _create_docker_backup_locked(
    *, compose_dir: Path, env_file: Path, output: Path,
    release_public_key: Path, confirm_maintenance: bool,
) -> dict[str, object]:
    """Stop Compose writers, cold-export both data volumes, then restart prior services."""
    if not confirm_maintenance:
        raise ValueError("Docker backup requires --confirm-maintenance because client services will stop")
    compose_dir = compose_dir.resolve(strict=True)
    command, model, env = _compose_context(compose_dir, env_file)
    required_services = {"postgres", "minio", "api", "ui", "redis"}
    if not required_services <= set(model.get("services", {})):
        raise ValueError("Compose project is missing required client services for backup")
    volume_names = _compose_volume_names(model)
    for volume in (volume_names["postgres_data"], volume_names["minio_data"]):
        if not _docker_volume_exists(volume, compose_dir):
            raise ValueError(f"Required data volume does not exist; refusing to snapshot an empty replacement: {volume}")
    running = _running_services(command, compose_dir, set(model["services"]))
    if output.exists():
        raise ValueError("Recovery archive already exists; refusing to overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    restart_error: Exception | None = None
    backup_result: dict[str, object] | None = None
    try:
        if running:
            _run([*command, "stop"], cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)
        _assert_no_running_volume_consumers(
            [volume_names["postgres_data"], volume_names["minio_data"]], compose_dir,
        )
        image = _get_volume_image(env)
        with tempfile.TemporaryDirectory(prefix="kodewaves-client-backup-", dir=output.parent) as temp_name:
            temp_dir = Path(temp_name)
            _assert_no_running_volume_consumers(
                [volume_names["postgres_data"], volume_names["minio_data"]], compose_dir,
            )
            _volume_tar_command(
                image=image, volume_name=volume_names["postgres_data"], host_directory=temp_dir,
                archive_name="postgres.tar", compose_dir=compose_dir, extract=False,
            )
            _assert_no_running_volume_consumers(
                [volume_names["postgres_data"], volume_names["minio_data"]], compose_dir,
            )
            _volume_tar_command(
                image=image, volume_name=volume_names["minio_data"], host_directory=temp_dir,
                archive_name="minio.tar", compose_dir=compose_dir, extract=False,
            )
            current_env = parse_env(env_file)
            manifest_path = Path(current_env["CLIENT_RELEASE_MANIFEST_FILE"])
            if not manifest_path.is_absolute():
                manifest_path = compose_dir / manifest_path
            identity_path = Path(current_env["CLIENT_IDENTITY_KEY_FILE"]) if current_env.get("CLIENT_IDENTITY_KEY_FILE") else None
            backup_result = create_archive(
                postgres_tar=temp_dir / "postgres.tar", minio_tar=temp_dir / "minio.tar",
                env_file=env_file, manifest=manifest_path,
                release_public_key=release_public_key, identity_key=identity_path,
                output=output, writers_stopped=True,
            )
    finally:
        try:
            _restart_services(command, compose_dir, running)
        except Exception as exc:
            restart_error = exc
    if restart_error is not None:
        raise RuntimeError(
            "Backup archive may have been created, but the previously running services could not be restarted; "
            "use docker compose start after resolving the Docker error"
        ) from restart_error
    if backup_result is None:
        raise RuntimeError("Docker backup did not produce an archive")
    return {**backup_result, "services_restarted": running}


def create_docker_backup(
    *, compose_dir: Path, env_file: Path, output: Path,
    release_public_key: Path, confirm_maintenance: bool,
) -> dict[str, object]:
    with _recovery_operation_lock(compose_dir):
        return _create_docker_backup_locked(
            compose_dir=compose_dir, env_file=env_file, output=output,
            release_public_key=release_public_key, confirm_maintenance=confirm_maintenance,
        )


def _write_private(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        path.chmod(mode)


def _staged_config_matches_installation(staged: Path, env_file: Path, compose_dir: Path) -> dict[str, str]:
    archived_env_path = staged / "config/.env"
    archived_env = parse_env(archived_env_path)
    current_env = parse_env(env_file)
    if {
        key: value for key, value in archived_env.items() if key != "COMPOSE_FILE"
    } != {
        key: value for key, value in current_env.items() if key != "COMPOSE_FILE"
    }:
        raise ValueError("Active .env differs from the recovery set; refusing to change installation credentials")
    manifest_ref = current_env.get("CLIENT_RELEASE_MANIFEST_FILE", "")
    manifest_path = Path(manifest_ref)
    if not manifest_path.is_absolute():
        manifest_path = compose_dir / manifest_path
    _check_regular_file(manifest_path, "active release manifest")
    if manifest_path.read_bytes() != (staged / "config/client-release-manifest.json").read_bytes():
        raise ValueError("Active release manifest differs from the recovery set")
    if current_env.get("CLIENT_IDENTITY_KEY_FILE"):
        key_path = Path(current_env["CLIENT_IDENTITY_KEY_FILE"])
        _check_regular_file(key_path, "active installation identity key")
        if key_path.read_bytes() != (staged / "config/installation.key").read_bytes():
            raise ValueError("Active installation identity key differs from the recovery set")
    return current_env


def _persisted_recovery_state(compose_dir: Path) -> Path:
    return compose_dir / RECOVERY_STATE_DIR


def _switch_compose_up(
    compose_dir: Path, env_file: Path, services: list[str], *, timeout: int = 360,
) -> None:
    if not services:
        return
    command, _model, _env = _compose_context(compose_dir, env_file)
    _run(
        [*command, "up", "--detach", "--wait", "--wait-timeout", str(timeout), *services],
        cwd=compose_dir, timeout=timeout + 60,
    )


def _restore_to_docker_volumes_locked(
    *, archive_path: Path, compose_dir: Path, env_file: Path,
    confirm_maintenance: bool,
) -> dict[str, object]:
    """Restore into new labeled volumes, atomically switch Compose, retain rollback volumes."""
    if not confirm_maintenance:
        raise ValueError("Docker restore requires --confirm-maintenance because client services will stop")
    compose_dir = compose_dir.resolve(strict=True)
    env_file = env_file.resolve(strict=True)
    state_dir = _persisted_recovery_state(compose_dir)
    if state_dir.exists():
        raise ValueError("A prior recovery is still active; run rollback-docker before another restore")
    command, model, env = _compose_context(compose_dir, env_file)
    stage_parent = compose_dir / ".client-recovery-stage"
    stage_parent.mkdir(mode=0o700, exist_ok=True)
    stage_dir = stage_parent / f"restore-{uuid.uuid4().hex}"
    summary = restore_to_directory(archive_path, stage_dir)
    try:
        current_env = _staged_config_matches_installation(stage_dir, env_file, compose_dir)
        original_volumes = _compose_volume_names(model)
        services = set(model.get("services", {}))
        running = _running_services(command, compose_dir, services)
        image = _get_volume_image(env)
        metadata = json.loads((stage_dir / "recovery.json").read_text(encoding="utf-8"))
        recovery_id = uuid.uuid4().hex[:12]
        project = str(model.get("name") or compose_dir.name.lower())
        new_volumes = {
            "postgres_data": f"{project}_postgres_recovery_{recovery_id}",
            "minio_data": f"{project}_minio_recovery_{recovery_id}",
            "redis_data": f"{project}_redis_recovery_{recovery_id}",
        }
        override_path = compose_dir / RECOVERY_OVERRIDE
        original_override_exists = override_path.exists()
        original_override = override_path.read_bytes() if original_override_exists else b""
        state_dir.mkdir(mode=0o700)
        try:
            _write_private(state_dir / "previous-recovery-override", original_override)
        except Exception:
            shutil.rmtree(state_dir, ignore_errors=True)
            raise
        state = {
            "format": "kodewaves-client-recovery-state-v1",
            "restore_id": recovery_id,
            "installation_id": metadata["installation_id"],
            "original_volumes": original_volumes,
            "new_volumes": new_volumes,
            "running_services": running,
            "original_override_exists": original_override_exists,
            "original_override_sha256": hashlib.sha256(original_override).hexdigest(),
            "created_volumes": [],
            "status": "preparing",
        }
        try:
            _write_private(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
        except Exception:
            shutil.rmtree(state_dir, ignore_errors=True)
            raise
        try:
            for name in new_volumes.values():
                state["created_volumes"].append(name)
                _atomic_write(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
                _create_volume(name, compose_dir, recovery_id)
            _volume_tar_command(
                image=image, volume_name=new_volumes["postgres_data"],
                host_directory=stage_dir / "volumes", archive_name="postgres.tar",
                compose_dir=compose_dir, extract=True,
            )
            _volume_tar_command(
                image=image, volume_name=new_volumes["minio_data"],
                host_directory=stage_dir / "volumes", archive_name="minio.tar",
                compose_dir=compose_dir, extract=True,
            )
            if running:
                _run([*command, "stop"], cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)
            _atomic_write(override_path, _recovery_override(new_volumes), mode=0o600)
            state["status"] = "switching"
            _atomic_write(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
            _switch_compose_up(compose_dir, env_file, running)
        except Exception as restore_error:
            # A failed stop may have stopped only part of the project. Restore
            # the exact previous mapping first, then restart only its services.
            if running:
                current_command, _current_model, _ = _compose_context(compose_dir, env_file)
                try:
                    _run([*current_command, "stop"], cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)
                except Exception:
                    pass
            if original_override_exists:
                _atomic_write(override_path, original_override, mode=0o600)
            else:
                override_path.unlink(missing_ok=True)
            try:
                _switch_compose_up(compose_dir, env_file, running)
            except Exception as rollback_error:
                state["status"] = "automatic_rollback_failed"
                _atomic_write(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
                raise RuntimeError(
                    "Restore failed and automatic rollback could not restart the original volumes; "
                    "the original volume set and recovery state are preserved"
                ) from rollback_error
            state["status"] = "automatic_rollback_succeeded"
            try:
                _remove_owned_recovery_volumes(state["created_volumes"], compose_dir, recovery_id)
            except Exception as cleanup_error:
                state["status"] = "automatic_rollback_succeeded_volumes_retained"
                state["cleanup_error"] = str(cleanup_error)
            _atomic_write(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
            failed_state_dir = compose_dir / f".client-recovery-failed-{recovery_id}"
            state_dir.rename(failed_state_dir)
            raise RuntimeError("Restore failed; original volume selection was automatically restored") from restore_error
        state["status"] = "active"
        _atomic_write(state_dir / "state.json", (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
        return {
            **summary,
            "status": "restored_to_new_volumes",
            "installation_id": metadata["installation_id"],
            "new_volumes": new_volumes,
            "original_volumes_preserved": True,
            "rollback_command": "python3 recovery.py rollback-docker",
            "docker_volumes_modified": True,
        }
    finally:
        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)
        try:
            if stage_parent.exists() and not any(stage_parent.iterdir()):
                stage_parent.rmdir()
        except OSError:
            pass


def restore_to_docker_volumes(
    *, archive_path: Path, compose_dir: Path, env_file: Path,
    confirm_maintenance: bool,
) -> dict[str, object]:
    with _recovery_operation_lock(compose_dir):
        return _restore_to_docker_volumes_locked(
            archive_path=archive_path, compose_dir=compose_dir, env_file=env_file,
            confirm_maintenance=confirm_maintenance,
        )


def _rollback_docker_restore_locked(*, compose_dir: Path, env_file: Path, confirm_maintenance: bool) -> dict[str, object]:
    """Switch Compose back to the original volumes without deleting either set."""
    if not confirm_maintenance:
        raise ValueError("Docker rollback requires --confirm-maintenance because client services will stop")
    compose_dir = compose_dir.resolve(strict=True)
    env_file = env_file.resolve(strict=True)
    state_dir = _persisted_recovery_state(compose_dir)
    if not state_dir.is_dir():
        raise ValueError("No active Docker recovery state exists")
    state_path = state_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("format") != "kodewaves-client-recovery-state-v1" or state.get("status") != "active":
        raise ValueError("Recovery state is not in an active rollback-ready state")
    current_override = compose_dir / RECOVERY_OVERRIDE
    current_bytes = current_override.read_bytes()
    if json.loads(current_bytes).get("volumes") != {
        logical: {"external": True, "name": value}
        for logical, value in state["new_volumes"].items()
    }:
        raise ValueError("Recovery Compose override changed after restore; refusing automatic rollback")
    original_override = (state_dir / "previous-recovery-override").read_bytes()
    if hashlib.sha256(original_override).hexdigest() != state.get("original_override_sha256"):
        raise ValueError("Saved original Compose override is damaged")
    command, model, _env = _compose_context(compose_dir, env_file)
    running = _running_services(command, compose_dir, set(model.get("services", {})))
    original_running = list(state.get("running_services", []))
    try:
        if running:
            _run([*command, "stop"], cwd=compose_dir, timeout=MAX_DOCKER_TIMEOUT)
        if state.get("original_override_exists"):
            _atomic_write(current_override, original_override, mode=0o600)
        else:
            current_override.unlink(missing_ok=True)
        _switch_compose_up(compose_dir, env_file, original_running)
    except Exception as rollback_error:
        _atomic_write(current_override, current_bytes, mode=0o600)
        try:
            _switch_compose_up(compose_dir, env_file, running)
        except Exception as restart_error:
            raise RuntimeError(
                "Rollback failed and the restored-volume services could not restart; both volume sets are retained"
            ) from restart_error
        raise RuntimeError("Rollback failed; the restored-volume selection was reinstated") from rollback_error
    rolled_back_dir = compose_dir / f".client-recovery-rolled-back-{state['restore_id']}"
    state["status"] = "rolled_back"
    _atomic_write(state_path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
    state_dir.rename(rolled_back_dir)
    return {
        "status": "rolled_back",
        "original_volumes_selected": state["original_volumes"],
        "restored_volumes_preserved": state["new_volumes"],
        "rollback_state": str(rolled_back_dir),
    }


def rollback_docker_restore(*, compose_dir: Path, env_file: Path, confirm_maintenance: bool) -> dict[str, object]:
    with _recovery_operation_lock(compose_dir):
        return _rollback_docker_restore_locked(
            compose_dir=compose_dir, env_file=env_file, confirm_maintenance=confirm_maintenance,
        )


def _validate_archive_handle(archive: tarfile.TarFile) -> tuple[dict[str, object], dict[str, str]]:
    """Validate one already-open archive and return summary and verified checksums."""
    files: dict[str, tarfile.TarInfo] = {}
    total_size = 0
    for member in archive:
        if len(files) >= MAX_ARCHIVE_MEMBERS:
            raise ValueError("Recovery archive has too many entries")
        _validate_member_name(member.name)
        if member.name in files:
            raise ValueError(f"Duplicate recovery archive entry: {member.name}")
        if not member.isfile():
            raise ValueError(f"Recovery archive may contain regular files only: {member.name}")
        if member.size < 0 or member.size > MAX_FILE_SIZE:
            raise ValueError(f"Recovery archive entry has an invalid size: {member.name}")
        total_size += member.size
        if total_size > MAX_ARCHIVE_SIZE:
            raise ValueError("Recovery archive exceeds the supported uncompressed size limit")
        files[member.name] = member

    names = set(files)
    if not REQUIRED_FILES <= names or names - REQUIRED_FILES - OPTIONAL_FILES:
        missing = sorted(REQUIRED_FILES - names)
        unexpected = sorted(names - REQUIRED_FILES - OPTIONAL_FILES)
        raise ValueError(f"Invalid recovery archive contents; missing={missing}, unexpected={unexpected}")

    metadata = json.loads(_read_member(archive, files["recovery.json"], MAX_METADATA_SIZE))
    if (
        not isinstance(metadata, dict)
        or metadata.get("format") != "kodewaves-client-recovery-v1"
        or metadata.get("snapshot_mode") != "cold"
        or metadata.get("writers_stopped") is not True
        or metadata.get("redis_included") is not False
    ):
        raise ValueError("Recovery metadata must declare v1 cold snapshot, stopped writers, and no Redis state")
    installation_id = metadata.get("installation_id")
    if not isinstance(installation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", installation_id):
        raise ValueError("Recovery metadata must include a valid installation_id")
    env_bytes = _read_member(archive, files["config/.env"], MAX_METADATA_SIZE)
    if _env_value(env_bytes, "KODEWAVES_INSTALLATION_ID") != installation_id:
        raise ValueError("Recovery installation_id does not match the archived .env")
    license_token = _env_value(env_bytes, "KODEWAVES_LICENSE_TOKEN") or ""
    if metadata.get("license_sha256") != hashlib.sha256(license_token.encode()).hexdigest():
        raise ValueError("Recovery license fingerprint does not match the archived .env")
    manifest_bytes = _read_member(archive, files["config/client-release-manifest.json"], MAX_METADATA_SIZE)
    if metadata.get("manifest_sha256") != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError("Recovery manifest fingerprint does not match the archived manifest")
    try:
        manifest_payload = json.loads(manifest_bytes)["payload"]
        if (
            manifest_payload.get("edition") != "client"
            or metadata.get("api_image") != _env_value(env_bytes, "CLIENT_API_IMAGE")
            or metadata.get("ui_image") != _env_value(env_bytes, "CLIENT_UI_IMAGE")
            or manifest_payload["images"]["api"].get("reference") != metadata.get("api_image")
            or manifest_payload["images"]["ui"].get("reference") != metadata.get("ui_image")
        ):
            raise ValueError("Recovery image references do not match the archived config and manifest")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Archived client release manifest is invalid or incomplete") from exc
    key_configured = bool(_env_value(env_bytes, "CLIENT_IDENTITY_KEY_FILE"))
    if key_configured != ("config/installation.key" in files):
        raise ValueError("Recovery identity key presence does not match the archived .env")
    identity_gid = _env_value(env_bytes, "CLIENT_IDENTITY_GID")
    if key_configured:
        key_member = files["config/installation.key"]
        try:
            configured_gid = int(identity_gid or "")
        except ValueError as exc:
            raise ValueError("Archived .env must include a numeric identity GID") from exc
        if (
            not 1 <= configured_gid <= 2**31 - 1
            or metadata.get("identity_gid") != configured_gid
            or metadata.get("identity_mode") != 0o640
            or key_member.gid != configured_gid
            or metadata.get("identity_uid") != key_member.uid
            or key_member.mode & 0o777 != 0o640
        ):
            raise ValueError("Identity key group and 0640 permissions must match archived metadata and .env")

    checksum_text = _read_member(archive, files["SHA256SUMS"], MAX_METADATA_SIZE).decode("ascii")
    expected: dict[str, str] = {}
    for line in checksum_text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("SHA256SUMS contains an invalid line")
        digest, name = match.groups()
        _validate_member_name(name)
        if name in expected:
            raise ValueError(f"Duplicate checksum entry: {name}")
        expected[name] = digest
    checksummed_names = names - {"SHA256SUMS"}
    if set(expected) != checksummed_names:
        raise ValueError("SHA256SUMS must cover every archive file except itself")
    for name, digest in expected.items():
        member = files[name]
        if name in {"volumes/postgres.tar", "volumes/minio.tar"}:
            if _hash_member(archive, member) != digest:
                raise ValueError(f"Checksum mismatch: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Unable to read recovery archive entry: {name}")
            _validate_nested_tar(stream, name)
            continue
        limit = MAX_METADATA_SIZE
        content = _read_member(archive, member, limit)
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {name}")

    if "config/installation.key" in files:
        key_member = files["config/installation.key"]
        key = _read_member(archive, key_member, 32)
        if len(key) != 32:
            raise ValueError("Installation identity key must contain exactly 32 bytes")
    summary = {
        "status": "validated",
        "installation_id": installation_id,
        "contains_identity_key": "config/installation.key" in files,
        "snapshot_mode": "cold",
        "restore_performed": False,
    }
    return summary, expected


def validate_archive(path: Path) -> dict[str, object]:
    """Validate exact archive layout, cold-snapshot declaration, and all hashes."""
    try:
        archive_bytes = path.stat().st_size
        if archive_bytes < 1 or archive_bytes > MAX_ARCHIVE_SIZE:
            raise ValueError("Recovery archive exceeds the supported compressed size limit")
        with tarfile.open(path, mode="r:gz") as archive:
            summary, _ = _validate_archive_handle(archive)
            return summary
    except (OSError, tarfile.TarError) as exc:
        raise ValueError("Recovery archive must be a readable gzip-compressed tar file") from exc


def restore_to_directory(archive_path: Path, destination: Path) -> dict[str, object]:
    """Stage a validated recovery set to a new directory; never touch live volumes."""
    if destination.exists():
        raise ValueError("Restore destination already exists; refusing to overwrite")
    parent = destination.parent.resolve(strict=True)
    if destination.resolve(strict=False).parent != parent:
        raise ValueError("Restore destination must be directly inside an existing parent directory")
    with archive_path.open("rb") as archive_file:
        archive_bytes = os.fstat(archive_file.fileno()).st_size
        if archive_bytes < 1 or archive_bytes > MAX_ARCHIVE_SIZE:
            raise ValueError("Recovery archive exceeds the supported compressed size limit")
        with tarfile.open(fileobj=archive_file, mode="r:gz") as archive:
            summary, expected = _validate_archive_handle(archive)
            volume_members = {
                member.name: member
                for member in archive.getmembers()
                if member.name in {"volumes/postgres.tar", "volumes/minio.tar"}
            }
            expanded_size = 0
            for name, member in volume_members.items():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f"Unable to inspect nested volume snapshot: {name}")
                expanded_size += _nested_expanded_size(stream, name)
            required_space = sum(member.size for member in volume_members.values()) + expanded_size
            if shutil.disk_usage(parent).free < required_space + max(16 * 1024 * 1024, required_space // 50):
                raise ValueError("Insufficient free space for offline staged restore")
        archive_file.seek(0)
        destination.mkdir(mode=0o700)
        try:
            seen: set[str] = set()
            with tarfile.open(fileobj=archive_file, mode="r:gz") as archive:
                for member in archive:
                    name = member.name
                    _validate_member_name(name)
                    if name in seen or name not in set(expected) | {"SHA256SUMS"}:
                        raise ValueError(f"Unexpected or duplicate recovery entry: {name}")
                    seen.add(name)
                    if not member.isfile() or member.size < 0 or member.size > MAX_FILE_SIZE:
                        raise ValueError(f"Recovery entry is not a bounded regular file: {name}")
                    target = destination.joinpath(*PurePosixPath(name).parts)
                    if not target.resolve(strict=False).is_relative_to(destination.resolve()):
                        raise ValueError(f"Unsafe recovery archive path: {name!r}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError(f"Unable to read recovery entry: {name}")
                    digest = hashlib.sha256()
                    total = 0
                    with target.open("xb") as output:
                        while chunk := source.read(HASH_CHUNK_SIZE):
                            total += len(chunk)
                            if total > member.size:
                                raise ValueError(f"Recovery entry size changed during staging: {name}")
                            digest.update(chunk)
                            output.write(chunk)
                    if total != member.size:
                        raise ValueError(f"Recovery entry size changed during staging: {name}")
                    if name in expected and digest.hexdigest() != expected[name]:
                        raise ValueError(f"Recovery entry changed after validation: {name}")
                    if name == "config/.env":
                        target.chmod(0o600)
                    elif name == "config/installation.key":
                        target.chmod(0o640)
                        if os.name != "nt":
                            os.chown(target, member.uid, member.gid)
                    elif name.endswith(".tar"):
                        target.chmod(0o600)
                        data_directory = target.parent / ("postgres-data" if name.endswith("postgres.tar") else "minio-data")
                        data_directory.mkdir(mode=0o700)
                        with target.open("rb") as nested_stream:
                            _extract_nested_volume(nested_stream, data_directory, name)
                    else:
                        target.chmod(0o644)
            if seen != set(expected) | {"SHA256SUMS"}:
                raise ValueError("Recovery archive changed its entry list after validation")
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    return {**summary, "status": "staged", "destination": str(destination), "docker_volumes_modified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate", help="validate an existing recovery archive")
    validate_parser.add_argument("archive", type=Path)
    create_parser = commands.add_parser("create", help="package already-cold, pre-exported volume archives")
    create_parser.add_argument("--postgres-tar", required=True, type=Path)
    create_parser.add_argument("--minio-tar", required=True, type=Path)
    create_parser.add_argument("--env-file", required=True, type=Path)
    create_parser.add_argument("--manifest", required=True, type=Path)
    create_parser.add_argument("--release-public-key", required=True, type=Path)
    create_parser.add_argument("--identity-key", type=Path)
    create_parser.add_argument("--output", required=True, type=Path)
    create_parser.add_argument(
        "--confirm-stopped-writers", action="store_true",
        help="attest API/UI and all database/object writers were stopped before exporting both volumes",
    )
    restore_parser = commands.add_parser("restore", help="stage a validated archive into a new offline directory")
    restore_parser.add_argument("archive", type=Path)
    restore_mode = restore_parser.add_mutually_exclusive_group(required=True)
    restore_mode.add_argument("--destination", type=Path, help="stage files in a new offline directory")
    restore_mode.add_argument("--docker-volumes", action="store_true", help="restore to new Compose volumes and retain old volumes for rollback")
    restore_parser.add_argument("--compose-dir", type=Path, default=Path(__file__).resolve().parent)
    restore_parser.add_argument("--env-file", type=Path)
    restore_parser.add_argument("--confirm-maintenance", action="store_true")
    docker_backup_parser = commands.add_parser("backup-docker", help="stop client services and create a cold backup of Postgres and MinIO volumes")
    docker_backup_parser.add_argument("--compose-dir", type=Path, default=Path(__file__).resolve().parent)
    docker_backup_parser.add_argument("--env-file", type=Path)
    docker_backup_parser.add_argument("--release-public-key", type=Path)
    docker_backup_parser.add_argument("--output", required=True, type=Path)
    docker_backup_parser.add_argument("--confirm-maintenance", action="store_true")
    rollback_parser = commands.add_parser("rollback-docker", help="switch to preserved original volumes after a Docker restore")
    rollback_parser.add_argument("--compose-dir", type=Path, default=Path(__file__).resolve().parent)
    rollback_parser.add_argument("--env-file", type=Path)
    rollback_parser.add_argument("--confirm-maintenance", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            result = validate_archive(args.archive)
        elif args.command == "create":
            result = create_archive(
                postgres_tar=args.postgres_tar, minio_tar=args.minio_tar,
                env_file=args.env_file, manifest=args.manifest,
                release_public_key=args.release_public_key, output=args.output,
                identity_key=args.identity_key, writers_stopped=args.confirm_stopped_writers,
            )
        elif args.command == "restore" and args.destination is not None:
            result = restore_to_directory(args.archive, args.destination)
        elif args.command == "restore":
            env_file = args.env_file or args.compose_dir / ".env"
            result = restore_to_docker_volumes(
                archive_path=args.archive, compose_dir=args.compose_dir, env_file=env_file,
                confirm_maintenance=args.confirm_maintenance,
            )
        elif args.command == "backup-docker":
            env_file = args.env_file or args.compose_dir / ".env"
            release_public_key = args.release_public_key or args.compose_dir / "release-public-key.txt"
            result = create_docker_backup(
                compose_dir=args.compose_dir, env_file=env_file, output=args.output,
                release_public_key=release_public_key, confirm_maintenance=args.confirm_maintenance,
            )
        else:
            env_file = args.env_file or args.compose_dir / ".env"
            result = rollback_docker_restore(
                compose_dir=args.compose_dir, env_file=env_file,
                confirm_maintenance=args.confirm_maintenance,
            )
    except (ValueError, OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Recovery archive rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
