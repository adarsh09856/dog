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
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath

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
    restore_parser.add_argument("--destination", required=True, type=Path)
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
        else:
            result = restore_to_directory(args.archive, args.destination)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Recovery archive rejected: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
