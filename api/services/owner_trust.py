"""Read owner verification keys baked into an approved client API image."""

import base64
import binascii
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


class OwnerTrustError(RuntimeError):
    pass


TRUST_FILE = Path(__file__).with_name("owner_public_keys.json")


def _decode_trusted_key(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("invalid owner verification key")
    unpadded = value.rstrip("=")
    padding = len(value) - len(unpadded)
    required_padding = -len(unpadded) % 4
    if len(unpadded) % 4 == 1 or padding not in (0, required_padding):
        raise ValueError("invalid owner verification key")
    encoded = unpadded + "=" * required_padding
    decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != unpadded:
        raise ValueError("non-canonical owner verification key")
    if len(decoded) != 32:
        raise ValueError("invalid owner verification key")
    return decoded


def _trusted_key(name: str) -> str:
    try:
        value = json.loads(TRUST_FILE.read_text(encoding="ascii"))[name]
        _decode_trusted_key(value)
        return value
    except (OSError, KeyError, TypeError, ValueError, binascii.Error) as exc:
        raise OwnerTrustError("Approved client image is missing its owner trust keys") from exc


def trusted_license_public_key() -> str:
    return _trusted_key("license")


def trusted_license_public_keys() -> tuple[str, ...]:
    """Return primary and transitional owner license keys baked into the image."""
    primary = trusted_license_public_key()
    try:
        previous = json.loads(TRUST_FILE.read_text(encoding="ascii")).get("license_previous", "")
        if not isinstance(previous, str):
            raise TypeError("invalid previous license keys")
        keys = [primary]
        for value in previous.split(","):
            key = value.strip()
            if key:
                _decode_trusted_key(key)
                if key not in keys:
                    keys.append(key)
        return tuple(keys)
    except (OSError, TypeError, ValueError, binascii.Error) as exc:
        raise OwnerTrustError("Approved client image has invalid owner trust keys") from exc


def trusted_release_public_key() -> str:
    return _trusted_key("release")


def trusted_owner_status_url() -> str:
    try:
        value = json.loads(TRUST_FILE.read_text(encoding="ascii"))["owner_status_url"]
        if not isinstance(value, str):
            raise TypeError("invalid owner status URL")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment
            or any(ord(character) < 33 or character in {'"', "\\"} for character in value)
        ):
            raise ValueError("invalid owner status URL")
        return value
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise OwnerTrustError("Approved client image is missing its owner status endpoint") from exc
