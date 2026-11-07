"""Small durable outbox for integrity failures detected before API startup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def _outbox_dir(installation_id: str) -> Path:
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise OSError("Integrity outbox requires an installation identity")
    root = Path(os.getenv(
        "KODEWAVES_INTEGRITY_OUTBOX_DIR",
        "/app/kodewaves_pcm_cache/integrity-outbox",
    ))
    if root.is_symlink():
        raise OSError("Integrity outbox directory cannot be a symbolic link")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Keep a reused Docker volume from replaying one installation's alert
    # under another license identity. The opaque namespace cannot traverse paths.
    namespace = hashlib.sha256(installation_id.encode("utf-8")).hexdigest()
    path = root / namespace
    if path.is_symlink():
        raise OSError("Integrity outbox installation directory cannot be a symbolic link")
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def _fingerprint(finding: dict[str, Any]) -> str:
    canonical = json.dumps(finding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def persist_integrity_finding(finding: dict[str, Any], *, installation_id: str) -> None:
    """Atomically write a deduplicated finding to the mounted persistent volume."""
    directory = _outbox_dir(installation_id)
    target = directory / f"{_fingerprint(finding)}.json"
    if target.is_symlink():
        raise OSError("Integrity outbox entry cannot be a symbolic link")
    content = json.dumps(finding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", suffix=".tmp", dir=directory)
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        if os.name != "nt":
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def pending_integrity_findings(*, installation_id: str) -> list[dict[str, Any]]:
    """Read pending entries without creating the optional outbox on poll."""
    if not isinstance(installation_id, str) or not installation_id.strip():
        raise OSError("Integrity outbox requires an installation identity")
    root = Path(os.getenv(
        "KODEWAVES_INTEGRITY_OUTBOX_DIR",
        "/app/kodewaves_pcm_cache/integrity-outbox",
    ))
    if root.is_symlink():
        raise OSError("Integrity outbox directory cannot be a symbolic link")
    if not root.exists():
        return []
    namespace = hashlib.sha256(installation_id.encode("utf-8")).hexdigest()
    directory = root / namespace
    if directory.is_symlink():
        raise OSError("Integrity outbox installation directory cannot be a symbolic link")
    if not directory.exists():
        return []
    findings = []
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(value, dict)
            and set(value).issubset({"reason", "component", "expected_sha256", "observed_sha256"})
            and value.get("reason") in {
                "unknown", "modified_file", "missing_file", "added_file",
                "invalid_manifest", "missing_manifest", "missing_trust_root",
            }
            and isinstance(value.get("component"), str)
            and re.fullmatch(r"[A-Za-z0-9_./-]{1,500}", value["component"])
            and all(
                value.get(name) is None
                or (
                    isinstance(value.get(name), str)
                    and re.fullmatch(r"[0-9a-f]{64}", value[name])
                )
                for name in ("expected_sha256", "observed_sha256")
            )
        ):
            findings.append(value)
    return findings


def acknowledge_integrity_finding(finding: dict[str, Any], *, installation_id: str) -> None:
    """Remove the local copy only after the signed owner response acknowledges it."""
    path = _outbox_dir(installation_id) / f"{_fingerprint(finding)}.json"
    if path.is_symlink():
        raise OSError("Integrity outbox entry cannot be a symbolic link")
    try:
        path.unlink()
    except FileNotFoundError:
        return
