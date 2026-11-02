"""Perform enrollment cryptography inside an approved client API image.

This helper communicates through stdin/stdout so license and private-key
material do not appear in process arguments. It makes no network requests.
"""

from __future__ import annotations

import base64
import json
import secrets
import sys
import time
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services.installation_identity import _decode_urlsafe, sign_enrollment, sign_owner_check
from api.services.installation_license import _canonical_domain, load_license, verify_installation_status_claims
from api.services.owner_trust import trusted_license_public_keys, trusted_owner_status_url


class _EnrollmentHelperFailure(Exception):
    """Carry a fixed stage and exception type without exposing request secrets."""

    def __init__(self, stage: str, error_type: str):
        self.stage = stage
        self.error_type = error_type


def execute(request: dict[str, Any]) -> dict[str, Any]:
    """Use the image's baked owner trust to prepare or verify enrollment."""
    stage = "request_validation"
    try:
        token = request["license_token"]
        stage = "owner_license_trust"
        keys = trusted_license_public_keys()
        stage = "license_token_validation"
        license_data = load_license(token, keys)
        stage = "installation_id_binding"
        if request["installation_id"] != license_data.installation_id:
            raise ValueError("Installation ID does not match the license")
        stage = "licensed_domain_binding"
        if _canonical_domain(request["public_host"]) not in license_data.domains:
            raise ValueError("Public hostname does not match the license")

        action = request["action"]
        if action == "verify_status":
            stage = "signed_owner_status_validation"
            status = verify_installation_status_claims(
                request["signed_status"], public_key=keys, installation_id=license_data.installation_id,
                license_token=token, nonce=request["nonce"],
            )
            if status["revoked"] or status.get("binding_valid") is False or (
                license_data.ip_ranges and status.get("binding_valid") is not True
            ):
                raise ValueError("Owner status does not permit this installation")
            return {"verified": True}

        stage = "installation_key_decode"
        seed = _decode_urlsafe(request["private_key"], 32)
        stage = "installation_key_construction"
        key = Ed25519PrivateKey.from_private_bytes(seed)
        public_key = base64.urlsafe_b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )).rstrip(b"=").decode("ascii")
        nonce = secrets.token_urlsafe(32)
        issued_at = int(time.time())
        common = {
            "installation_id": license_data.installation_id,
            "license_token": token,
            "nonce": nonce,
            "issued_at": issued_at,
        }
        if action == "prepare_enrollment":
            stage = "enrollment_signature"
            signature = sign_enrollment(
                seed, public_key=public_key, enrollment_token=request["enrollment_token"], **common
            )
            stage = "owner_status_endpoint"
            return {
                "owner_status_url": trusted_owner_status_url(), "public_key": public_key,
                "nonce": nonce, "issued_at": issued_at, "signature": signature,
            }
        if action == "prepare_status":
            stage = "owner_status_signature"
            signature = sign_owner_check(seed, integrity_ok=True, integrity_finding=None, **common)
            stage = "owner_status_endpoint"
            return {
                "owner_status_url": trusted_owner_status_url(), "nonce": nonce,
                "issued_at": issued_at, "signature": signature,
            }
        raise ValueError("Unknown enrollment action")
    except _EnrollmentHelperFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - report only fixed stage and safe type
        raise _EnrollmentHelperFailure(stage, type(exc).__name__) from None


def main() -> int:
    stage = "request_parsing"
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Enrollment request must be an object")
        result = execute(request)
    except _EnrollmentHelperFailure as exc:
        print(f"Enrollment helper failed: {exc.stage}:{exc.error_type}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - avoid disclosing private input on failure
        print(f"Enrollment helper failed: {stage}:{type(exc).__name__}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
