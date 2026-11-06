#!/usr/bin/env python3
"""Poll signed owner rollouts and safely update the client application and host tools.

Host control files are replaced only after the signed archive and new
application stack pass verification. Database and MinIO snapshots,
schema-aware rollback, and the shared Compose/recovery lock are handled by the
bundled recovery tooling.
It never accepts shell commands or image references from an unsigned source.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compose_client
import enroll_identity
import recovery
from recovery_lock import recovery_operation_lock
from validate_install import MODEL_IMAGE_KEYS, parse_env, validate as validate_install, validate_model_images

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_FILES = 32
DOWNLOAD_TIMEOUT = 90
COMPOSE_TIMEOUT = 900
APP_IMAGES = ("api", "ui")
HOST_TOOL_FILES = (
    "docker-compose.client.yaml", "docker-compose.identity.yaml",
    "docker-compose.recovery.yaml", "Caddyfile", "validate_install.py",
    "enroll_identity.py", "recovery.py", "compose_client.py",
    "recovery_lock.py", "verify_installer.py", "update_agent.py",
)
MODEL_HOST_FILES = ("docker-compose.models.yaml", "warm_local_models.py")
SYSTEMD_UNIT_FILES = ("kodewaves-client-update.service", "kodewaves-client-update.timer")
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")
HOST_JOURNAL_NAME = ".host-update-transaction.json"
_DIGEST_IMAGE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}\Z")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_PACKAGE_FILES = {
    "README.md", "docker-compose.client.yaml", "docker-compose.identity.yaml",
    "docker-compose.recovery.yaml", "Caddyfile", "validate_install.py",
    "enroll_identity.py", "recovery.py", "compose_client.py", "recovery_lock.py",
    "verify_installer.py", "update_agent.py", "kodewaves-client-update.service",
    "kodewaves-client-update.timer", ".env.example", "client-release-manifest.json",
    "release-public-key.txt", "SHA256SUMS",
}


class UpdateError(RuntimeError):
    """A signed update cannot be applied safely."""


class ManualUnitMigrationRequired(UpdateError):
    """The currently active systemd sandbox predates host-tool updates."""

    MESSAGE = (
        "One-time manual migration required: install the updated Kodewaves updater service unit, "
        "then run systemctl daemon-reload before retrying"
    )


def _version(value: str) -> tuple[int, int, int]:
    match = _VERSION.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise UpdateError("Client version is not canonical X.Y.Z")
    result = tuple(int(part) for part in match.groups())
    if any(part > 2**31 - 1 for part in result):
        raise UpdateError("Client version component is too large")
    return result


def _status_endpoint(check_url: str) -> str:
    parsed = urlsplit(check_url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment
        or not parsed.path.endswith("/client-installations/check")
    ):
        raise UpdateError("Approved owner status URL is invalid")
    return urlunsplit((parsed.scheme, parsed.netloc,
                       parsed.path[:-len("check")] + "update-status", "", ""))


def _read_identity_key(path: Path, gid: int) -> bytes:
    try:
        return enroll_identity._private_key(path, gid, allow_create=False)
    except (OSError, enroll_identity.EnrollmentError) as exc:
        raise UpdateError("Enrolled installation identity key is unavailable") from exc


def _helper_request(image: str, request: dict) -> dict:
    try:
        return enroll_identity._image_helper(image, request)
    except enroll_identity.EnrollmentError as exc:
        raise UpdateError("Approved API image identity helper failed") from exc


def _owner_post(url: str, token: str, payload: dict) -> dict:
    try:
        return enroll_identity._post_json(url, token, payload)
    except enroll_identity.EnrollmentError as exc:
        raise UpdateError("Owner update request failed") from exc


def _prepare_check(env: dict[str, str], current_version: str) -> dict:
    key_path = Path(env["CLIENT_IDENTITY_KEY_FILE"])
    key = _read_identity_key(key_path, int(env["CLIENT_IDENTITY_GID"]))
    return _helper_request(env["CLIENT_API_IMAGE"], {
        "action": "prepare_update_check",
        "license_token": env["KODEWAVES_LICENSE_TOKEN"],
        "installation_id": env["KODEWAVES_INSTALLATION_ID"],
        "public_host": env["PUBLIC_HOST"],
        "private_key": base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii"),
        "current_version": current_version,
    })


def _owner_status(env: dict[str, str], current_version: str) -> tuple[dict, str]:
    prepared = _prepare_check(env, current_version)
    check_url = prepared.get("owner_status_url")
    if not isinstance(check_url, str):
        raise UpdateError("Approved owner status URL is missing")
    _status_endpoint(check_url)
    request_payload = {
        "nonce": prepared["nonce"],
        "integrity_ok": True,
        "integrity_finding": None,
        "proof_issued_at": prepared["issued_at"],
        "proof_signature": prepared["signature"],
        "current_version": current_version,
    }
    response = _owner_post(check_url, env["KODEWAVES_LICENSE_TOKEN"], request_payload)
    verified = _helper_request(env["CLIENT_API_IMAGE"], {
        "action": "verify_status",
        "license_token": env["KODEWAVES_LICENSE_TOKEN"],
        "installation_id": env["KODEWAVES_INSTALLATION_ID"],
        "public_host": env["PUBLIC_HOST"],
        "nonce": prepared["nonce"],
        "signed_status": response.get("signed_status"),
    })
    status = verified.get("status") if verified.get("verified") is True else None
    if not isinstance(status, dict):
        raise UpdateError("Owner status did not contain verified claims")
    return status, _status_endpoint(check_url)


def _report(env: dict[str, str], status_url: str, update: dict, state: str, detail: str = "") -> None:
    nonce = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    issued_at = int(time.time())
    fields = {
        "rollout_id": update["rollout_id"], "release_id": update["release_id"],
        "version": update["version"], "nonce": nonce, "issued_at": issued_at,
        "status": state, "detail": detail[:1000],
    }
    if state == "rolled_back":
        fields["installed_version"] = _current_version(env["CLIENT_API_IMAGE"])
    key = _read_identity_key(Path(env["CLIENT_IDENTITY_KEY_FILE"]), int(env["CLIENT_IDENTITY_GID"]))
    proof = _helper_request(env["CLIENT_API_IMAGE"], {
        "action": "prepare_update_report",
        "license_token": env["KODEWAVES_LICENSE_TOKEN"],
        "installation_id": env["KODEWAVES_INSTALLATION_ID"],
        "public_host": env["PUBLIC_HOST"],
        "private_key": base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii"),
        **fields,
    })
    _owner_post(status_url, env["KODEWAVES_LICENSE_TOKEN"], {
        **fields, "proof_signature": proof["proof_signature"],
    })


def _download(url: str, destination: Path) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise UpdateError("Release archive URL must be HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "KodewavesClientUpdate/1"})
    try:
        with urllib.request.build_opener(enroll_identity._NoRedirect()).open(
            request, timeout=DOWNLOAD_TIMEOUT,
        ) as response, destination.open("xb") as output:
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > MAX_ARCHIVE_BYTES):
                raise UpdateError("Release archive exceeds the supported size")
            digest = hashlib.sha256()
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise UpdateError("Release archive exceeds the supported size")
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
            if declared is not None and total != int(declared):
                raise UpdateError("Release archive download was incomplete")
            return digest.hexdigest()
    except UpdateError:
        destination.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError("Release archive download failed") from exc


def _extract_verified_archive(archive_path: Path, destination: Path) -> dict[str, object]:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names: set[str] = set()
            total = 0
            contents: dict[str, bytes] = {}
            if len(members) > MAX_ARCHIVE_FILES:
                raise UpdateError("Release archive has too many files")
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute() or len(path.parts) != 1 or path.name in {"", ".", ".."}
                    or not member.isfile() or member.name in names
                    or member.size < 0 or member.size > MAX_EXTRACTED_BYTES
                ):
                    raise UpdateError("Release archive contains an unsafe entry")
                names.add(member.name)
                total += member.size
                if total > MAX_EXTRACTED_BYTES:
                    raise UpdateError("Release archive expands beyond the supported size")
                stream = archive.extractfile(member)
                if stream is None:
                    raise UpdateError("Release archive contains an unreadable entry")
                data = stream.read(MAX_EXTRACTED_BYTES + 1)
                if len(data) != member.size:
                    raise UpdateError("Release archive entry size is invalid")
                contents[member.name] = data
            if names not in (_PACKAGE_FILES, _PACKAGE_FILES | set(MODEL_HOST_FILES)):
                raise UpdateError("Release archive file inventory is incomplete or unexpected")
        checksums: dict[str, str] = {}
        for line in contents["SHA256SUMS"].decode("ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
            if not match or match.group(2) in checksums:
                raise UpdateError("Release archive checksum inventory is invalid")
            checksums[match.group(2)] = match.group(1)
        if set(checksums) != names - {"SHA256SUMS"}:
            raise UpdateError("Release archive checksum inventory is incomplete")
        for name, data in contents.items():
            if name != "SHA256SUMS" and hashlib.sha256(data).hexdigest() != checksums[name]:
                raise UpdateError("Release archive checksum mismatch")
        for name, data in contents.items():
            path = destination / name
            with path.open("xb") as output:
                output.write(data)
            path.chmod(0o600 if name == ".env.example" else 0o644)
        return json.loads(contents["client-release-manifest.json"])
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _manifest_images(manifest: dict[str, object]) -> tuple[dict[str, str], dict[str, object]]:
    payload = manifest.get("payload") if isinstance(manifest, dict) else None
    if (
        not isinstance(payload, dict) or payload.get("edition") != "client"
        or not isinstance(payload.get("images"), dict)
    ):
        raise UpdateError("Signed release manifest does not declare application images")
    images = payload["images"]
    if set(images) != set(APP_IMAGES):
        raise UpdateError("Signed release manifest must contain exactly API and UI images")
    references: dict[str, str] = {}
    for name in APP_IMAGES:
        item = images[name]
        reference = item.get("reference") if isinstance(item, dict) else None
        if not isinstance(item, dict) or item.get("kind") != "registry_digest" or not isinstance(reference, str) or not _DIGEST_IMAGE.fullmatch(reference):
            raise UpdateError("Release application image is not pinned to an approved digest")
        references[name] = reference
    schema = payload.get("schema_compatibility")
    if not isinstance(schema, dict) or not isinstance(schema.get("head"), str) or not isinstance(schema.get("rollback_to"), list):
        raise UpdateError("Release manifest has no schema rollback metadata")
    return references, schema


def _verify_manifest_signature(manifest: dict[str, object], public_key_file: Path) -> dict[str, object]:
    from build_and_verify import read_public_key

    try:
        payload = recovery._verify_release_manifest(
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            read_public_key(public_key_file),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UpdateError("Release manifest signature is invalid") from exc
    return payload


def _current_version(image: str) -> str:
    result = subprocess.run(
        ["docker", "run", "--rm", "--pull=never", "--network=none", "--entrypoint", "python",
         image, "-c", "from api.constants import APP_VERSION; print(APP_VERSION)"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if result.returncode != 0:
        raise UpdateError("Installed API image version could not be read")
    value = (result.stdout or "").strip()
    _version(value)
    return value


def _compose(directory: Path, arguments: list[str], timeout: int = COMPOSE_TIMEOUT) -> None:
    command = compose_client.build_command(directory, arguments)
    env = compose_client.controlled_environment(directory)
    try:
        subprocess.run(command, cwd=directory, env=env, timeout=timeout, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("Docker Compose update command failed") from exc


def _atomic_env(directory: Path, values: dict[str, str]) -> bytes:
    env_file = directory / ".env"
    before = env_file.read_bytes()
    replacement = before
    for key in ("CLIENT_API_IMAGE", "CLIENT_UI_IMAGE", "CLIENT_RELEASE_MANIFEST_FILE"):
        if key not in values:
            raise UpdateError("Update release settings are incomplete")
        matches = sum(
            1 for line in before.decode("utf-8").splitlines()
            if re.match(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=", line)
        )
        if matches != 1:
            raise UpdateError(f"Client .env must define {key} exactly once")
        replacement = recovery._update_env_value(replacement, key, values[key])
    recovery._atomic_write(env_file, replacement, mode=0o600)
    return before


def _restore_env(directory: Path, original: bytes) -> None:
    recovery._atomic_write(directory / ".env", original, mode=0o600)


def _fsync_directory(path: Path) -> None:
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _atomic_replace_bytes(path: Path, contents: bytes, mode: int, uid: int, gid: int) -> None:
    """Replace a regular file atomically without following a target symlink."""
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir() or parent.resolve(strict=True) != parent:
        raise UpdateError("Host update target directory is unsafe")
    if path.is_symlink():
        raise UpdateError("Host update target is a symlink")
    if path.exists() and not path.is_file():
        raise UpdateError("Host update target is not a regular file")
    temp_fd = -1
    temp_path: Path | None = None
    try:
        temp_fd, raw_temp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
        temp_path = Path(raw_temp_path)
        with os.fdopen(temp_fd, "wb") as output:
            temp_fd = -1
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        if os.name == "posix":
            os.chmod(temp_path, mode)
            os.chown(temp_path, uid, gid)
        os.replace(temp_path, path)
        temp_path = None
        _fsync_directory(parent)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError("Host update file could not be replaced atomically") from exc
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _host_targets(directory: Path, systemd_dir: Path) -> dict[str, Path]:
    return {
        **{name: directory / name for name in (*HOST_TOOL_FILES, *MODEL_HOST_FILES)},
        **{name: systemd_dir / name for name in SYSTEMD_UNIT_FILES},
    }


def _probe_systemd_unit_write(systemd_dir: Path) -> None:
    """Fail clearly when an old systemd sandbox still blocks unit updates."""
    if systemd_dir.is_symlink() or not systemd_dir.is_dir() or systemd_dir.resolve(strict=True) != systemd_dir:
        raise UpdateError("Systemd unit directory is missing or unsafe")
    try:
        fd, probe = tempfile.mkstemp(prefix=".kodewaves-update-probe.", dir=systemd_dir)
        os.close(fd)
        Path(probe).unlink()
    except OSError as exc:
        raise ManualUnitMigrationRequired(ManualUnitMigrationRequired.MESSAGE) from exc


def _journal_path(work_dir: Path) -> Path:
    path = work_dir / HOST_JOURNAL_NAME
    if path.is_symlink():
        raise UpdateError("Host update rollback journal is unsafe")
    return path


def _write_host_journal(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _atomic_replace_bytes(path, encoded, 0o600, os.getuid() if hasattr(os, "getuid") else 0,
                          os.getgid() if hasattr(os, "getgid") else 0)


def _rollback_host_journal(work_dir: Path, systemd_dir: Path) -> None:
    journal_path = _journal_path(work_dir)
    if not journal_path.exists():
        return
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UpdateError("Host update rollback journal cannot be read") from exc
    if not isinstance(journal, dict) or journal.get("state") not in {"prepared", "committed"}:
        raise UpdateError("Host update rollback journal is malformed")
    if journal["state"] == "committed":
        journal_path.unlink()
        _fsync_directory(work_dir)
        return
    entries = journal.get("files")
    targets = _host_targets(work_dir.parent.parent, systemd_dir)
    if not isinstance(entries, dict) or set(entries) - set(targets):
        raise UpdateError("Host update rollback journal contains unapproved paths")
    units_changed = False
    for name, entry in entries.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("existed"), bool):
            raise UpdateError("Host update rollback journal is malformed")
        target = targets[name]
        if name in SYSTEMD_UNIT_FILES:
            units_changed = True
        if entry["existed"]:
            try:
                contents = base64.b64decode(entry["contents"], validate=True)
                mode, uid, gid = (entry[key] for key in ("mode", "uid", "gid"))
                if any(not isinstance(value, int) or value < 0 for value in (mode, uid, gid)):
                    raise ValueError("invalid metadata")
            except (KeyError, TypeError, ValueError) as exc:
                raise UpdateError("Host update rollback journal is malformed") from exc
            _atomic_replace_bytes(target, contents, mode, uid, gid)
        elif target.exists():
            if target.is_symlink() or not target.is_file():
                raise UpdateError("Host update rollback target is unsafe")
            target.unlink()
            _fsync_directory(target.parent)
    if units_changed:
        _systemd_daemon_reload()
    journal_path.unlink()
    _fsync_directory(work_dir)


def _systemd_daemon_reload() -> None:
    try:
        subprocess.run(["systemctl", "daemon-reload"], timeout=30, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("systemd could not reload the updated Kodewaves units") from exc


def _download_verified_host_release(update: dict, work_dir: Path, public_key_file: Path):
    archive_path = work_dir / "release.tar.gz"
    extracted = work_dir / "unpacked"
    if archive_path.is_symlink() or extracted.is_symlink():
        raise UpdateError("Client update staging path is unsafe")
    archive_path.unlink(missing_ok=True)
    if extracted.exists():
        shutil.rmtree(extracted)
    digest = _download(update["archive_url"], archive_path)
    if digest != update["archive_sha256"]:
        raise UpdateError("Downloaded release does not match the owner-signed SHA-256")
    manifest = _extract_verified_archive(archive_path, extracted)
    payload = _verify_manifest_signature(manifest, public_key_file)
    return archive_path, extracted, payload


def _model_update_values(env: dict[str, str], extracted: Path) -> dict[str, str]:
    if "self-hosted" not in {item.strip() for item in env.get("COMPOSE_PROFILES", "").split(",")}:
        return {}
    if not all((extracted / name).is_file() for name in MODEL_HOST_FILES):
        raise UpdateError("Self-hosted installation requires a signed local-inference package")
    packaged = parse_env(extracted / ".env.example")
    values = {key: packaged.get(key, "") for key in MODEL_IMAGE_KEYS}
    try:
        validate_model_images(values)
    except ValueError as exc:
        raise UpdateError("Signed local-inference image pins are incomplete or invalid") from exc
    return values


def _apply_host_maintenance(
    directory: Path, extracted: Path, work_dir: Path, *, systemd_dir: Path = SYSTEMD_UNIT_DIR,
) -> None:
    """Install the verified, fixed host allowlist as a recoverable transaction."""
    _probe_systemd_unit_write(systemd_dir)
    targets = _host_targets(directory, systemd_dir)
    journal_path = _journal_path(work_dir)
    if journal_path.exists():
        raise UpdateError("A prior host update transaction needs recovery before retry")
    entries: dict[str, dict] = {}
    sources: dict[str, bytes] = {}
    units_changed = False
    model_files = MODEL_HOST_FILES if all((extracted / name).is_file() for name in MODEL_HOST_FILES) else ()
    for name in (*HOST_TOOL_FILES, *model_files, *SYSTEMD_UNIT_FILES):
        source = extracted / name
        if source.is_symlink() or not source.is_file() or source.resolve(strict=True).parent != extracted.resolve(strict=True):
            raise UpdateError("Verified archive host file is missing or unsafe")
        target = targets[name]
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise UpdateError("Host update target is missing or unsafe")
        if name in SYSTEMD_UNIT_FILES:
            units_changed = True
        sources[name] = source.read_bytes()
        if target.exists():
            stat = target.stat(follow_symlinks=False)
            entries[name] = {
                "existed": True,
                "contents": base64.b64encode(target.read_bytes()).decode("ascii"),
                "mode": stat.st_mode & 0o7777,
                "uid": stat.st_uid,
                "gid": stat.st_gid,
            }
        else:
            if name not in (*SYSTEMD_UNIT_FILES, *MODEL_HOST_FILES):
                raise UpdateError("A required installed host control file is missing")
            entries[name] = {"existed": False}
    _write_host_journal(journal_path, {"state": "prepared", "files": entries})
    try:
        for name, contents in sources.items():
            target = targets[name]
            if target.exists():
                stat = target.stat(follow_symlinks=False)
                mode, uid, gid = stat.st_mode & 0o7777, stat.st_uid, stat.st_gid
            else:
                mode, uid, gid = 0o644, 0, 0
            _atomic_replace_bytes(target, contents, mode, uid, gid)
        if units_changed:
            _systemd_daemon_reload()
        _write_host_journal(journal_path, {"state": "committed", "files": entries})
    except Exception:
        _rollback_host_journal(work_dir, systemd_dir)
        raise


def _report_protected(error: Exception) -> str:
    # Report a short fixed category, never exception text which could contain
    # a path, URL query, token, or infrastructure configuration.
    name = type(error).__name__
    return f"Update stopped safely ({name})" if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,50}", name) else "Update stopped safely"


def _installed_stack_healthy(directory: Path, env: dict[str, str]) -> bool:
    """Check local API/UI health before finalizing an interrupted update."""
    import urllib.request

    endpoints = (
        f"http://127.0.0.1:{env.get('API_PORT', '8000')}/api/v1/health",
        f"http://127.0.0.1:{env.get('UI_PORT', '3010')}/",
    )
    for endpoint in endpoints:
        try:
            with urllib.request.urlopen(endpoint, timeout=4) as response:
                if response.status != 200:
                    return False
        except (OSError, urllib.error.URLError, TimeoutError):
            return False
    return True


def _running_schema_head(directory: Path) -> str:
    code = (
        "import asyncio,json,os\n"
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "async def main():\n"
        " engine=create_async_engine(os.environ['DATABASE_URL'])\n"
        " async with engine.connect() as connection:\n"
        "  result=await connection.exec_driver_sql('SELECT version_num FROM alembic_version ORDER BY version_num')\n"
        "  print(json.dumps([row[0] for row in result.fetchall()]))\n"
        " await engine.dispose()\n"
        "asyncio.run(main())\n"
    )
    command = compose_client.build_command(directory, ["exec", "-T", "api", "python", "-c", code])
    try:
        result = subprocess.run(
            command, cwd=directory, env=compose_client.controlled_environment(directory),
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("Running database migration head could not be verified") from exc
    if result.returncode != 0:
        raise UpdateError("Running database migration head could not be verified")
    try:
        revisions = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise UpdateError("Running database migration head could not be parsed") from exc
    if not isinstance(revisions, list) or len(revisions) != 1 or not isinstance(revisions[0], str):
        raise UpdateError("Running database has an unexpected migration head count")
    return revisions[0]


def _active_manifest(directory: Path, env: dict[str, str], public_key_file: Path) -> dict[str, object]:
    manifest_path = Path(env["CLIENT_RELEASE_MANIFEST_FILE"])
    if not manifest_path.is_absolute():
        manifest_path = directory / manifest_path
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise UpdateError("Installed release manifest is missing or unsafe")
    signed = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = _verify_manifest_signature(signed, public_key_file)
    images, schema = _manifest_images({"payload": payload})
    if images != {"api": env["CLIENT_API_IMAGE"], "ui": env["CLIENT_UI_IMAGE"]}:
        raise UpdateError("Running image pins do not match the installed signed manifest")
    return {"payload": payload, "schema": schema}


def _install_manifest_atomically(directory: Path, destination: Path, contents: bytes) -> None:
    """Publish a verified manifest without exposing a partial final file."""
    if destination.parent != directory or destination.is_symlink():
        raise UpdateError("Release manifest destination is unsafe")
    if destination.exists():
        if destination.is_file() and destination.read_bytes() == contents:
            return
        raise UpdateError("A different release manifest already uses this file name")

    temp_fd = -1
    temp_path: Path | None = None
    try:
        temp_fd, raw_temp_path = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=directory,
        )
        temp_path = Path(raw_temp_path)
        with os.fdopen(temp_fd, "wb") as output:
            temp_fd = -1
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        temp_path.chmod(0o644)
        try:
            # Hard-link publication is atomic and fails instead of replacing
            # a path that appeared after the initial existence check.
            os.link(temp_path, destination)
        except FileExistsError:
            if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != contents:
                raise UpdateError("A different release manifest already uses this file name")
        if os.name == "posix":
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError("Release manifest could not be installed atomically") from exc
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _running_release_healthy(directory: Path, env: dict[str, str], expected_head: str) -> bool:
    for service, variable in (("api", "CLIENT_API_IMAGE"), ("ui", "CLIENT_UI_IMAGE")):
        command = compose_client.build_command(directory, ["ps", "-q", service])
        result = subprocess.run(
            command, cwd=directory, env=compose_client.controlled_environment(directory),
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            return False
        container_ids = [item for item in (result.stdout or "").splitlines() if item.strip()]
        if len(container_ids) != 1:
            return False
        inspected = subprocess.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", container_ids[0]],
            cwd=directory, capture_output=True, text=True, timeout=30, check=False,
        )
        if inspected.returncode != 0 or inspected.stdout.strip() != env[variable]:
            return False
    return _installed_stack_healthy(directory, env) and _running_schema_head(directory) == expected_head


def _wait_for_release_healthy(
    directory: Path, env: dict[str, str], expected_head: str, *, timeout_seconds: int = 180,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            if _running_release_healthy(directory, env, expected_head):
                return True
        except (OSError, ValueError, UpdateError, subprocess.SubprocessError):
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(5, remaining))


def update_once(directory: Path, *, dry_run: bool = False) -> str:
    directory = directory.resolve(strict=True)
    env_file = directory / ".env"
    if env_file.is_symlink() or not env_file.is_file():
        raise UpdateError("Client .env is missing or unsafe")
    env = parse_env(env_file)
    for required in (
        "CLIENT_API_IMAGE", "CLIENT_UI_IMAGE", "CLIENT_RELEASE_MANIFEST_FILE",
        "KODEWAVES_LICENSE_TOKEN", "KODEWAVES_INSTALLATION_ID", "PUBLIC_HOST",
        "CLIENT_IDENTITY_KEY_FILE", "CLIENT_IDENTITY_GID",
    ):
        if not env.get(required):
            raise UpdateError(f"Client update requires {required}")
    current_version = _current_version(env["CLIENT_API_IMAGE"])
    status, status_url = _owner_status(env, current_version)
    update = status.get("update")
    if update is None:
        return "No active owner update is staged for this installation."
    if not isinstance(update, dict):
        raise UpdateError("Verified owner update claims are malformed")
    version = update.get("version")
    release_id = update.get("release_id")
    rollout_id = update.get("rollout_id")
    if (
        not isinstance(release_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", release_id)
        or not isinstance(rollout_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", rollout_id)
        or not isinstance(version, str)
    ):
        raise UpdateError("Verified owner update is not a forward release")
    initial_target_status = update.get("target_status", "staged")
    if initial_target_status not in {"staged", "downloading", "applying"}:
        raise UpdateError("Owner update target status is not resumable")
    rollout_state = update.get("rollout_state")
    if rollout_state not in {"active", "paused", "stopped"}:
        raise UpdateError("Verified owner rollout state is missing or invalid")
    if rollout_state in {"paused", "stopped"} and initial_target_status != "applying":
        raise UpdateError("Paused or stopped owner rollout is not an in-flight update")
    if rollout_state in {"paused", "stopped"} and _version(current_version) < _version(version):
        terminal_message = f"Owner {rollout_state} the rollout before this client activated it"
        _report(env, status_url, update, "failed", terminal_message)
        return f"Owner rollout was {rollout_state}; application activation was skipped and reported."
    if current_version == version and initial_target_status == "applying":
        public_key_file = directory / "release-public-key.txt"
        work_dir = directory / ".client-update-work" / f"{release_id}-{rollout_id}"
        backup_path = work_dir / "pre-update-recovery.tar.gz"
        try:
            if public_key_file.is_symlink() or not public_key_file.is_file():
                raise UpdateError("Trusted release public key is missing or unsafe")
            active_release = _active_manifest(directory, env, public_key_file)
            expected_head = active_release["schema"]["head"]
            healthy = _wait_for_release_healthy(directory, env, expected_head, timeout_seconds=30)
        except (UpdateError, OSError, ValueError):
            healthy = False
        if not healthy:
            if not backup_path.is_file() or backup_path.is_symlink():
                raise UpdateError("Release version is present but unhealthy; no trusted rollback archive is available")
            recovery._restore_to_docker_volumes_locked(
                archive_path=backup_path, compose_dir=directory, env_file=directory / ".env",
                release_public_key=public_key_file, confirm_maintenance=True,
                allow_release_rollback=True,
            )
            _report(parse_env(directory / ".env"), status_url, update, "rolled_back", "Health check failed after interrupted update")
            return f"Release {version} failed health checks; the verified backup was restored."
        _probe_systemd_unit_write(SYSTEMD_UNIT_DIR)
        work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        _rollback_host_journal(work_dir, SYSTEMD_UNIT_DIR)
        archive_path, extracted, payload = _download_verified_host_release(update, work_dir, public_key_file)
        try:
            images, schema = _manifest_images({"payload": payload})
            if images != {"api": env["CLIENT_API_IMAGE"], "ui": env["CLIENT_UI_IMAGE"]}:
                raise UpdateError("Resumed release images do not match the healthy installation")
            if _current_version(images["api"]) != version or schema["head"] != expected_head:
                raise UpdateError("Resumed release archive does not match the healthy installation")
            refreshed, refreshed_url = _owner_status(env, current_version)
            refreshed_update = refreshed.get("update")
            if refreshed_url != status_url or not isinstance(refreshed_update, dict) or any(
                refreshed_update.get(key) != update.get(key)
                for key in ("release_id", "version", "rollout_id", "archive_sha256")
            ) or refreshed_update.get("target_status") not in {"applying", "downloading", "staged"} or refreshed_update.get("rollout_state") not in {"active", "paused", "stopped"}:
                return "Owner rollout is no longer active; verified application health was retained without host-tool changes."
            if refreshed_update.get("rollout_state") in {"paused", "stopped"} and refreshed_update.get("target_status") != "applying":
                return "Owner rollout is no longer applying; verified application health was retained without host-tool changes."
            _apply_host_maintenance(directory, extracted, work_dir)
        finally:
            archive_path.unlink(missing_ok=True)
            shutil.rmtree(extracted, ignore_errors=True)
        _report(env, status_url, update, "applied")
        _rollback_host_journal(work_dir, SYSTEMD_UNIT_DIR)
        return f"Release {version} and its signed host maintenance update are healthy and confirmed."
    if _version(current_version) >= _version(version):
        raise UpdateError("Verified owner update is not a forward release")
    if dry_run:
        return f"Owner-approved release {version} is ready; no files or containers were changed."
    work_root = directory / ".client-update-work"
    if work_root.is_symlink():
        raise UpdateError("Client update work directory is unsafe")
    work_root.mkdir(mode=0o700, exist_ok=True)
    work_dir = work_root / f"{release_id}-{rollout_id}"
    if work_dir.is_symlink():
        raise UpdateError("Client update staging directory is unsafe")
    work_dir.mkdir(mode=0o700, exist_ok=True)
    archive_path = work_dir / "release.tar.gz"
    extracted = work_dir / "unpacked"
    backup_path = work_dir / "pre-update-recovery.tar.gz"
    archive_path.unlink(missing_ok=True)
    if extracted.exists():
        shutil.rmtree(extracted)
    public_key_file = directory / "release-public-key.txt"
    if public_key_file.is_symlink() or not public_key_file.is_file():
        raise UpdateError("Trusted release public key is missing or unsafe")
    # Check the active unit's sandbox before touching app images. Older clients
    # must perform the one-time service-unit migration described in INSTALL.md.
    _probe_systemd_unit_write(SYSTEMD_UNIT_DIR)
    old_env: bytes | None = None
    env_was_switched = False
    containers_activated = False
    target_images: dict[str, str] | None = None
    try:
        if initial_target_status == "staged":
            _report(env, status_url, update, "downloading")
        archive_path, extracted, manifest_payload = _download_verified_host_release(update, work_dir, public_key_file)
        target_images, target_schema = _manifest_images({"payload": manifest_payload})
        if _current_version(target_images["api"]) != version:
            raise UpdateError("Release metadata version does not match the signed API image")
        current_manifest_ref = env["CLIENT_RELEASE_MANIFEST_FILE"]
        current_manifest_path = Path(current_manifest_ref)
        if not current_manifest_path.is_absolute():
            current_manifest_path = directory / current_manifest_path
        if current_manifest_path.is_symlink() or not current_manifest_path.is_file():
            raise UpdateError("Installed release manifest is missing or unsafe")
        current_manifest = _active_manifest(directory, env, public_key_file)
        current_schema = current_manifest["schema"]
        if not isinstance(current_schema, dict) or not isinstance(current_schema.get("head"), str):
            raise UpdateError("Installed release manifest has no schema head")
        if current_schema["head"] not in target_schema["rollback_to"]:
            raise UpdateError("Release has no signed database rollback path from the installed schema")
        if _version(update["min_current_version"]) > _version(current_version):
            raise UpdateError("Installed version is below this release's minimum")
        if target_images["api"] == env["CLIENT_API_IMAGE"] and target_images["ui"] == env["CLIENT_UI_IMAGE"]:
            _report(env, status_url, update, "applied", "Release images already match the installation")
            return f"Release {version} is already installed."

        release_key = hashlib.sha256(release_id.encode("ascii")).hexdigest()[:12]
        manifest_name = f"client-release-{version}-{release_key}.json"
        candidate_manifest = directory / manifest_name
        _install_manifest_atomically(
            directory,
            candidate_manifest,
            (extracted / "client-release-manifest.json").read_bytes(),
        )
        candidate_ref = f"./{manifest_name}"
        new_values = {
            "CLIENT_API_IMAGE": target_images["api"],
            "CLIENT_UI_IMAGE": target_images["ui"],
            "CLIENT_RELEASE_MANIFEST_FILE": candidate_ref,
        }
        new_values.update(_model_update_values(env, extracted))
        # Validate the whole candidate configuration before pulling images.
        old_env = _atomic_env(directory, new_values)
        env_was_switched = True
        controlled = compose_client.controlled_environment(directory)
        failures = [item for item in validate_install(env_file, directory / "docker-compose.client.yaml") if not item.startswith("preflight passed;")]
        if failures:
            raise UpdateError("Candidate client configuration failed preflight")
        config = compose_client.build_command(directory, ["config", "--quiet"])
        subprocess.run(config, cwd=directory, env=controlled, timeout=60, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        model_services = ["ollama", "indic-stt", "indus-tts", "indic-vits-tts"] if new_values.keys() & MODEL_IMAGE_KEYS else []
        _compose(directory, ["pull", "api", "ui", *model_services])
        # The fresh owner-signed status check also prevents applying a rollout
        # that the owner paused or stopped during the download.
        refreshed, refreshed_url = _owner_status(env, current_version)
        refreshed_update = refreshed.get("update")
        if refreshed_url != status_url or not isinstance(refreshed_update, dict) or any(
            refreshed_update.get(key) != update.get(key)
            for key in ("release_id", "version", "rollout_id", "archive_sha256")
        ):
            _restore_env(directory, old_env)
            env_was_switched = False
            return "Owner rollout is no longer active; no application containers were changed."
        refreshed_state = refreshed_update.get("rollout_state")
        if refreshed_state in {"paused", "stopped"}:
            _restore_env(directory, old_env)
            env_was_switched = False
            if refreshed_update.get("target_status") == "applying":
                terminal_message = f"Owner {refreshed_state} the rollout before this client activated it"
                _report(env, status_url, update, "failed", terminal_message)
            return f"Owner rollout was {refreshed_state}; application activation was skipped."
        if refreshed_state != "active":
            raise UpdateError("Verified owner rollout state is missing or invalid")

        # Pull and manifest validation do not change running containers. Cold
        # snapshot immediately before the first image activation.
        _restore_env(directory, old_env)
        env_was_switched = False
        release_public_key = public_key_file
        if backup_path.is_symlink():
            raise UpdateError("Existing update recovery archive is unsafe")
        if backup_path.exists():
            recovery.validate_archive(backup_path, release_public_key=release_public_key)
        else:
            recovery._create_docker_backup_locked(
                compose_dir=directory, env_file=env_file, output=backup_path,
                release_public_key=release_public_key, confirm_maintenance=True,
            )
        refreshed, refreshed_url = _owner_status(env, current_version)
        refreshed_update = refreshed.get("update")
        if refreshed_url != status_url or not isinstance(refreshed_update, dict) or any(
            refreshed_update.get(key) != update.get(key)
            for key in ("release_id", "version", "rollout_id", "archive_sha256")
        ):
            return "Owner rollout is no longer active; backup was retained and no application containers were changed."
        refreshed_state = refreshed_update.get("rollout_state")
        if refreshed_state in {"paused", "stopped"}:
            if refreshed_update.get("target_status") == "applying":
                _report(env, status_url, update, "failed", f"Owner {refreshed_state} the rollout before this client activated it")
            return f"Owner rollout was {refreshed_state}; application activation was skipped."
        if refreshed_state != "active":
            raise UpdateError("Verified owner rollout state is missing or invalid")
        if initial_target_status != "applying":
            _report(env, status_url, update, "applying")
        _atomic_env(directory, new_values)
        env_was_switched = True
        _compose(directory, ["up", "--detach", "--wait", "--wait-timeout", "480", "api", "ui"], timeout=COMPOSE_TIMEOUT)
        if not _wait_for_release_healthy(directory, parse_env(env_file), target_schema["head"]):
            raise UpdateError("Updated API/UI or migrated database failed health verification")
        containers_activated = True
        post_health_env = parse_env(env_file)
        refreshed, refreshed_url = _owner_status(post_health_env, current_version)
        refreshed_update = refreshed.get("update")
        if refreshed_url != status_url or not isinstance(refreshed_update, dict) or any(
            refreshed_update.get(key) != update.get(key)
            for key in ("release_id", "version", "rollout_id", "archive_sha256")
        ) or refreshed_update.get("target_status") not in {"applying", "downloading", "staged"} or refreshed_update.get("rollout_state") not in {"active", "paused", "stopped"}:
            return "Owner rollout is no longer active; verified application health was retained without host-tool changes."
        # Once the new application has passed health checks, a pause/stop only
        # blocks new activations. Finish this authorized host update and send
        # its final status so the owner can close the in-flight target.
        if refreshed_update.get("rollout_state") in {"paused", "stopped"} and refreshed_update.get("target_status") != "applying":
            return "Owner rollout is no longer applying; verified application health was retained without host-tool changes."
        _apply_host_maintenance(directory, extracted, work_dir)
        try:
            _report(env, status_url, update, "applied")
        except Exception:
            return f"Release {version} is healthy; its completion report will retry on the next timer run."
        _rollback_host_journal(work_dir, SYSTEMD_UNIT_DIR)
        return f"Installed owner-approved release {version}."
    except Exception as exc:
        if containers_activated:
            return f"Release {version} is healthy; its completion report will retry on the next timer run."
        if env_was_switched and old_env is not None:
            try:
                if backup_path.is_file():
                    recovery._restore_to_docker_volumes_locked(
                        archive_path=backup_path, compose_dir=directory, env_file=env_file,
                        release_public_key=public_key_file, confirm_maintenance=True,
                        allow_release_rollback=True,
                    )
                else:
                    _restore_env(directory, old_env)
                if not backup_path.is_file() and containers_activated:
                    _compose(directory, ["up", "--detach", "--wait", "--wait-timeout", "480", "api", "ui"])
                final_status = "rolled_back" if backup_path.is_file() or containers_activated else "failed"
                _report(parse_env(env_file), status_url, update, final_status, _report_protected(exc))
            except Exception:
                # Do not hide a failed rollback or claim success. The cold
                # snapshot and both Docker volume sets remain for operator recovery.
                raise UpdateError("Update failed; automatic rollback also needs operator recovery") from exc
        else:
            try:
                _report(env, status_url, update, "failed", _report_protected(exc))
            except Exception:
                pass
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("Owner-approved update failed safely") from exc
    finally:
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)
        if extracted.exists():
            shutil.rmtree(extracted, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check", action="store_true", help="check owner status without downloading or changing the installation")
    args = parser.parse_args(argv)
    try:
        with recovery_operation_lock(args.directory):
            print(update_once(args.directory, dry_run=args.check))
        return 0
    except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as exc:
        # Keep terminal and systemd logs free of secrets, URLs and environment data.
        detail = str(exc) if isinstance(exc, ManualUnitMigrationRequired) else _report_protected(exc)
        print(f"Client update not completed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
