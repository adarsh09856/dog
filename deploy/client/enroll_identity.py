#!/usr/bin/env python3
"""Create a local installation key and enroll it with the trusted owner."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from validate_install import PINNED_IMAGE, parse_env, validate_identity_key


class EnrollmentError(ValueError):
    """The installation cannot be safely enrolled or confirmed."""


def _private_key(path: Path, group: int, *, allow_create: bool = True) -> bytes:
    """Create once or reuse the same key; never replace an enrolled identity."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        if not allow_create:
            raise EnrollmentError("Enrolled installation key is missing; contact the owner for recovery")
        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        created = False
        try:
            descriptor = os.open(path, create_flags, 0o600)
            created = True
            with os.fdopen(descriptor, "wb") as key_file:
                key = secrets.token_bytes(32)
                key_file.write(key)
                key_file.flush()
                if os.name != "nt":
                    os.fchown(key_file.fileno(), -1, group)
                    os.fchmod(key_file.fileno(), 0o640)
            return key
        except OSError as exc:
            # This invocation exclusively created the file and has not enrolled
            # it yet. Remove only that incomplete file so a corrected group ID
            # can be retried without ever replacing a pre-existing identity.
            if created:
                try:
                    path.unlink()
                except OSError:
                    pass
            raise EnrollmentError("Cannot create the private key with the requested group") from exc
    except OSError as exc:
        raise EnrollmentError("Cannot open the installation private key") from exc
    with os.fdopen(descriptor, "rb") as key_file:
        metadata = os.fstat(key_file.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != 32:
            raise EnrollmentError("Installation key must be a regular 32-byte file")
        return key_file.read()


def _image_helper(image: str, request: dict) -> dict:
    """Use the pinned image's baked trust and cryptography without network access."""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--pull=never", "--network=none", "-i", "--entrypoint", "python",
             image, "-m", "api.services.installation_enrollment_cli"],
            input=json.dumps(request), text=True, capture_output=True, timeout=60, check=False,
        )
        if result.returncode != 0:
            raise EnrollmentError("Approved API image could not prepare or verify enrollment")
        output = json.loads(result.stdout)
        if not isinstance(output, dict):
            raise ValueError("invalid helper output")
        return output
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise EnrollmentError("Approved API image enrollment helper is unavailable") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise EnrollmentError("Owner endpoint redirected the enrollment request")


def _post_json(url: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as response:
            data = response.read(1_048_577)
        if len(data) > 1_048_576:
            raise EnrollmentError("Owner response is too large")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("invalid owner response")
        return result
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise EnrollmentError("Owner request could not be completed") from exc


def _enrollment_url(status_url: str) -> str:
    parsed = urlsplit(status_url)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment or not parsed.path.endswith("/client-installations/check")
    ):
        raise EnrollmentError("Approved image has an invalid owner status endpoint")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path[:-len("check")] + "enroll", "", ""))


def enroll(env_file: Path, enrollment_token: str | None) -> None:
    """Enroll locally and verify a signed owner status without transmitting the key."""
    env = parse_env(env_file)
    image = env.get("CLIENT_API_IMAGE", "")
    token = env.get("KODEWAVES_LICENSE_TOKEN", "")
    installation_id = env.get("KODEWAVES_INSTALLATION_ID", "")
    public_host = env.get("PUBLIC_HOST", "")
    key_file = env.get("CLIENT_IDENTITY_KEY_FILE", "")
    group = env.get("CLIENT_IDENTITY_GID", "")
    if not PINNED_IMAGE.fullmatch(image):
        raise EnrollmentError("CLIENT_API_IMAGE must be pinned to an approved sha256 digest")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise EnrollmentError("A signed installation license is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", installation_id):
        raise EnrollmentError("A valid installation ID is required")
    if enrollment_token is not None and not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", enrollment_token):
        raise EnrollmentError("A valid one-time enrollment token is required")
    if not key_file or not Path(key_file).is_absolute() or "$" in key_file:
        raise EnrollmentError("CLIENT_IDENTITY_KEY_FILE must be an absolute local path")
    if not re.fullmatch(r"[0-9]{1,10}", group) or not 1 <= int(group) <= 2**31 - 1:
        raise EnrollmentError("CLIENT_IDENTITY_GID must be a nonzero numeric group ID")
    key = _private_key(Path(key_file), int(group), allow_create=enrollment_token is not None)
    errors = validate_identity_key(env)
    if errors:
        raise EnrollmentError(errors[0])
    common = {
        "license_token": token, "installation_id": installation_id, "public_host": public_host,
        "private_key": base64.urlsafe_b64encode(key).rstrip(b"=").decode("ascii"),
    }
    status_url = None
    if enrollment_token is not None:
        prepared = _image_helper(image, {**common, "action": "prepare_enrollment", "enrollment_token": enrollment_token})
        status_url = prepared["owner_status_url"]
        enrollment_url = _enrollment_url(status_url)
        payload = {
            "enrollment_token": enrollment_token, "public_key": prepared["public_key"],
            "nonce": prepared["nonce"], "issued_at": prepared["issued_at"], "signature": prepared["signature"],
        }
        try:
            reply = _post_json(enrollment_url, token, payload)
            if reply.get("enrolled") is not True:
                raise EnrollmentError("Owner did not confirm enrollment")
        except EnrollmentError:
            # A lost response may mean the one-time token was consumed. The signed
            # status check below safely confirms whether this same key is enrolled.
            pass
    check = _image_helper(image, {**common, "action": "prepare_status"})
    if status_url is not None and check["owner_status_url"] != status_url:
        raise EnrollmentError("Approved owner endpoint changed during enrollment")
    status_url = check["owner_status_url"]
    _enrollment_url(status_url)  # Validate the baked HTTPS origin and expected path.
    response = _post_json(status_url, token, {
        "nonce": check["nonce"], "integrity_ok": True, "integrity_finding": None,
        "proof_issued_at": check["issued_at"], "proof_signature": check["signature"],
    })
    verified = _image_helper(image, {
        "action": "verify_status", "license_token": token, "installation_id": installation_id,
        "public_host": public_host, "nonce": check["nonce"], "signed_status": response.get("signed_status"),
    })
    if verified.get("verified") is not True:
        raise EnrollmentError("Owner enrollment could not be verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--verify-only", action="store_true", help="Verify an existing key without enrolling or replacing it")
    args = parser.parse_args()
    try:
        token = None if args.verify_only else getpass.getpass("One-time owner enrollment token: ").strip()
        enroll(args.env_file, token)
    except (EnrollmentError, KeyError, OSError, ValueError) as exc:
        print(f"Enrollment failed: {exc}", file=sys.stderr)
        return 1
    print("Owner confirmed the enrolled installation identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
