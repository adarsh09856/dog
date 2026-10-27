"""Verify the owner-signed protected source manifest before client services start."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from api.services.deployment_edition import IMAGE_EDITION
from api.services.owner_trust import (
    OwnerTrustError,
    trusted_owner_status_url,
    trusted_release_public_key,
)


class ReleaseIntegrityError(RuntimeError):
    def __init__(
        self, message: str, *, reason: str = "unknown", component: str = "release",
        expected_sha256: str | None = None, observed_sha256: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.component = re.sub(r"[^A-Za-z0-9_./-]", "_", component)[:500] or "release"
        self.expected_sha256 = expected_sha256
        self.observed_sha256 = observed_sha256

    def finding(self) -> dict[str, str | None]:
        return {
            "reason": self.reason,
            "component": self.component,
            "expected_sha256": self.expected_sha256,
            "observed_sha256": self.observed_sha256,
        }


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def protected_files(root: Path) -> dict[str, str]:
    """Hash every shipped application file and reject linked code before loading it."""
    roots = (root / "api", root / "pipecat" / "src", root / "scripts", root / "docs")
    hashes: dict[str, str] = {}

    def excluded(path: Path) -> bool:
        relative = path.relative_to(root).as_posix()
        return (
            "__pycache__" in path.parts
            or relative == "api/tests"
        )

    def reject_link(path: Path) -> None:
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            relative = path.relative_to(root).as_posix()
            raise ReleaseIntegrityError(
                "Symbolic links are not allowed in protected application code",
                reason="modified_file", component=relative,
            )

    for tree in roots:
        # Checking only the final root follows a linked ancestor (for example,
        # pipecat/src beneath a junction at pipecat) before it is inspected.
        current = root
        for part in tree.relative_to(root).parts:
            current = current / part
            reject_link(current)
        for current, directories, filenames in os.walk(tree, topdown=True, followlinks=False):
            parent = Path(current)
            directories[:] = [name for name in directories if not excluded(parent / name)]
            for name in directories:
                reject_link(parent / name)
            for name in filenames:
                path = parent / name
                if excluded(path):
                    continue
                reject_link(path)
                # Runtime behavior also depends on model assets, prompt/Jinja
                # templates, JSON schemas and configuration. A suffix allowlist
                # silently left those files outside the signed release boundary.
                relative = path.relative_to(root).as_posix()
                hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    for required in (
        "api/app.py",
        "api/services/release_integrity.py",
        "api/services/deployment_edition.py",
        "api/services/owner_public_keys.json",
        "pipecat/src/pipecat/__init__.py",
        "scripts/run_web.sh",
        "scripts/start_services_docker.sh",
        "docs/docs.json",
    ):
        if required not in hashes:
            raise ReleaseIntegrityError(
                f"Protected client release file is missing: {required}",
                reason="missing_file", component=required,
            )
    return dict(sorted(hashes.items()))


def verify_release_manifest(
    root: Path, manifest_path: Path, public_key: str
) -> dict[str, object]:
    try:
        signed = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = signed["payload"]
        signature = signed["signature"]
        if (
            payload.get("edition") != "client"
            or not isinstance(payload.get("files"), dict)
            or not isinstance(payload.get("ui_files"), dict)
            or not all(
                isinstance(path, str) and isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest)
                for path, digest in payload["files"].items()
            )
            or not all(
                isinstance(path, str) and isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest)
                for path, digest in payload["ui_files"].items()
            )
        ):
            raise ReleaseIntegrityError("Invalid client release manifest")
        images = payload.get("images")
        schema = payload.get("schema_compatibility")
        if (images is None) != (schema is None):
            raise ReleaseIntegrityError("Release image and schema metadata must be signed together")
        if images is not None:
            if not isinstance(images, dict) or set(images) != {"api", "ui"}:
                raise ReleaseIntegrityError("Invalid client release image metadata")
            for name, image in images.items():
                if (
                    not isinstance(image, dict)
                    or image.get("kind") not in {"registry_digest", "image_id"}
                    or not isinstance(image.get("reference"), str)
                    or not (
                        re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", image["reference"])
                        if image["kind"] == "registry_digest"
                        else re.fullmatch(r"sha256:[0-9a-f]{64}", image["reference"])
                    )
                ):
                    raise ReleaseIntegrityError(f"Invalid client release image metadata: {name}")
            if (
                not isinstance(schema, dict)
                or not isinstance(schema.get("head"), str)
                or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", schema["head"])
                or not isinstance(schema.get("upgrade_from"), list)
                or not isinstance(schema.get("rollback_to"), list)
                or not all(
                    isinstance(revision, str)
                    and re.fullmatch(r"[A-Za-z0-9_]{1,64}", revision)
                    for revision in schema["upgrade_from"] + schema["rollback_to"]
                )
                or len(set(schema["upgrade_from"])) != len(schema["upgrade_from"])
                or len(set(schema["rollback_to"])) != len(schema["rollback_to"])
                or schema["head"] not in schema["upgrade_from"]
                or not set(schema["rollback_to"]).issubset(schema["upgrade_from"])
            ):
                raise ReleaseIntegrityError("Invalid client release schema compatibility metadata")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(_decode(public_key)).verify(
            _decode(signature), canonical
        )
        observed_files = protected_files(root)
        if payload["files"] != observed_files:
            expected_files = payload["files"]
            component = next(
                path for path in sorted(set(expected_files) | set(observed_files))
                if expected_files.get(path) != observed_files.get(path)
            )
            expected = expected_files.get(component)
            observed = observed_files.get(component)
            reason = "added_file" if expected is None else "missing_file" if observed is None else "modified_file"
            raise ReleaseIntegrityError(
                "Protected client release files differ from the signed manifest",
                reason=reason, component=component,
                expected_sha256=expected, observed_sha256=observed,
            )
        return payload
    except ReleaseIntegrityError:
        raise
    except (OSError, KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise ReleaseIntegrityError(
            "Client release manifest is missing or invalid",
            reason="invalid_manifest", component="manifest",
        ) from exc


def verify_configured_release(root: Path | None = None) -> None:
    configured_edition = os.getenv("KODEWAVES_EDITION", "saas").strip().lower()
    image_edition = IMAGE_EDITION or configured_edition
    if IMAGE_EDITION is not None and configured_edition != IMAGE_EDITION:
        raise ReleaseIntegrityError(
            "Runtime edition does not match the built image",
            reason="unknown", component="runtime_edition",
        )
    if image_edition != "client":
        return
    manifest = os.getenv("KODEWAVES_RELEASE_MANIFEST", "")
    if not manifest:
        raise ReleaseIntegrityError(
            "Client release manifest is required", reason="missing_manifest", component="manifest"
        )
    try:
        public_key = trusted_release_public_key()
    except OwnerTrustError as exc:
        raise ReleaseIntegrityError(str(exc), reason="missing_trust_root", component="owner_trust") from exc
    payload = verify_release_manifest(
        root or Path(__file__).resolve().parents[2], Path(manifest), public_key
    )
    images = payload.get("images")
    if images:
        for service, variable in (
            ("api", "KODEWAVES_API_IMAGE"),
            ("ui", "KODEWAVES_UI_IMAGE"),
        ):
            image = images[service]
            if (
                image["kind"] == "registry_digest"
                and os.getenv(variable, "") != image["reference"]
            ):
                raise ReleaseIntegrityError(
                    f"Configured {service.upper()} image does not match the signed release",
                    reason="unknown", component=f"{service}_image",
                )


def report_startup_integrity_failure(error: ReleaseIntegrityError) -> None:
    """Best-effort owner alert before a failed client process exits."""
    runtime_image_edition = IMAGE_EDITION or os.getenv("KODEWAVES_EDITION", "saas").strip().lower()
    if runtime_image_edition != "client":
        return
    token = os.getenv("KODEWAVES_LICENSE_TOKEN", "")
    if not token:
        return
    try:
        import httpx

        response = httpx.post(
            trusted_owner_status_url(),
            json={
                "nonce": secrets.token_urlsafe(32),
                "integrity_ok": False,
                "integrity_finding": error.finding(),
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - startup must still fail if reporting is unavailable
        print(f"Owner integrity alert delivery failed: {type(exc).__name__}", file=sys.stderr)


def verify_release_before_startup(root: Path | None = None) -> None:
    """Enforce integrity even if a deployment bypasses the image entrypoint."""
    try:
        verify_configured_release(root)
    except ReleaseIntegrityError as error:
        report_startup_integrity_failure(error)
        raise


if __name__ == "__main__":
    verify_release_before_startup()
