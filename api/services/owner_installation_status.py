"""Poll owner revocation status off the voice path and gate new client calls."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import time
from dataclasses import dataclass

import httpx
from loguru import logger
from redis.asyncio import Redis

from api.constants import REDIS_URL
from api.services.installation_license import (
    InstallationLicense,
    InstallationLicenseError,
    load_license,
    validate_installation_license,
    verify_installation_status_claims,
)
from api.services.installation_identity import owner_check_payload
from api.services.owner_trust import (
    OwnerTrustError,
    trusted_license_public_keys,
    trusted_owner_status_url,
)
from api.services.release_integrity import (
    ReleaseIntegrityError,
    verify_configured_release,
)

def _owner_status_poll_seconds(value: str | None = None) -> int:
    """Return a bounded owner-check interval; default to one minute."""
    raw = os.getenv("KODEWAVES_OWNER_STATUS_POLL_SECONDS", "60") if value is None else value
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return 60
    return min(max(seconds, 1), 3600)


POLL_SECONDS = _owner_status_poll_seconds()
OUTAGE_GRACE_SECONDS = 24 * 60 * 60
_logged_initial_owner_check = False


@dataclass(frozen=True)
class OwnerStatusSnapshot:
    last_owner_check: int
    using_outage_grace: bool


def _status_key(installation_id: str) -> str:
    return f"kodewaves:owner-installation-status:v1:{installation_id}"


def _status_url() -> str:
    try:
        return trusted_owner_status_url()
    except OwnerTrustError as exc:
        raise InstallationLicenseError(str(exc)) from exc


def _trusted_owner_key() -> tuple[str, ...]:
    try:
        return trusted_license_public_keys()
    except OwnerTrustError as exc:
        raise InstallationLicenseError(str(exc)) from exc


async def poll_owner_status_once(redis_client: Redis, client: httpx.AsyncClient) -> bool:
    """Save only a verified response; never replace last good status on failure."""
    global _logged_initial_owner_check
    token = os.getenv("KODEWAVES_LICENSE_TOKEN", "")
    public_key = _trusted_owner_key()
    license_data = load_license(token, public_key)
    validate_installation_license(license_data)
    try:
        # Hashing the runtime tree performs blocking filesystem IO. Keep the
        # periodic integrity check off the same event loop as live call audio.
        await asyncio.to_thread(verify_configured_release)
        integrity_ok = True
        integrity_finding = None
    except ReleaseIntegrityError as exc:
        integrity_ok = False
        integrity_finding = exc.finding()
        await redis_client.hset(
            _status_key(license_data.installation_id),
            mapping={
                "integrity_failed_latched": "1",
                "pending_integrity_finding": json.dumps(integrity_finding, sort_keys=True),
            },
        )
    pending = await redis_client.hget(
        _status_key(license_data.installation_id), "pending_integrity_finding"
    )
    if pending:
        integrity_ok = False
        integrity_finding = json.loads(pending)
    nonce = secrets.token_urlsafe(32)
    response = await client.post(
        _status_url(),
        json=owner_check_payload(
            installation_id=license_data.installation_id, license_token=token, nonce=nonce,
            integrity_ok=integrity_ok, integrity_finding=integrity_finding,
            private_key_path=os.getenv("KODEWAVES_INSTALLATION_KEY_FILE", ""),
        ),
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
    )
    response.raise_for_status()
    signed_status = response.json()["signed_status"]
    status = verify_installation_status_claims(
        signed_status,
        public_key=public_key,
        installation_id=license_data.installation_id,
        license_token=token,
        nonce=nonce,
    )
    if pending:
        # Do not erase a newer finding written by another polling process.
        await redis_client.eval(
            "if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2] then "
            "return redis.call('HDEL', KEYS[1], ARGV[1]) end return 0",
            1,
            _status_key(license_data.installation_id),
            "pending_integrity_finding",
            pending,
        )
    if status["revoked"]:
        # A slower active response from another worker must not undo a
        # revocation already observed by this installation.
        await redis_client.hset(
            _status_key(license_data.installation_id),
            mapping={"revoked_latched": "1"},
        )
    await redis_client.hset(
        _status_key(license_data.installation_id),
        mapping={"signed_status": signed_status, "nonce": nonce},
    )
    if not _logged_initial_owner_check:
        try:
            await require_current_owner_status(license_data, redis_client)
        except InstallationLicenseError:
            pass
        else:
            logger.info(
                "Initial owner installation check succeeded for {}",
                license_data.installation_id,
            )
            _logged_initial_owner_check = True
    return status["revoked"]


async def require_current_owner_status(
    license_data: InstallationLicense, redis_client: Redis | None = None
) -> OwnerStatusSnapshot:
    """Deny new calls if revoked, unchecked, or beyond the outage grace."""
    _status_url()
    own_client = redis_client is None
    redis_client = redis_client or Redis.from_url(REDIS_URL)
    try:
        try:
            fields = await redis_client.hgetall(_status_key(license_data.installation_id))
        except Exception as exc:
            raise InstallationLicenseError("Owner status cache is unavailable") from exc
        if fields.get(b"integrity_failed_latched") == b"1":
            raise InstallationLicenseError("Protected installation files were modified")
        if fields.get(b"revoked_latched") == b"1":
            raise InstallationLicenseError("Installation license was revoked by the owner")
        signed_status = fields.get(b"signed_status")
        nonce = fields.get(b"nonce")
        if not signed_status or not nonce:
            raise InstallationLicenseError("Owner installation check has not succeeded")
        now = int(time.time())
        status = verify_installation_status_claims(
            signed_status.decode("ascii"),
            public_key=_trusted_owner_key(),
            installation_id=license_data.installation_id,
            license_token=os.getenv("KODEWAVES_LICENSE_TOKEN", ""),
            nonce=nonce.decode("ascii"),
            now=now,
            # An IP allowlist is meaningful only when the source address was
            # checked recently by the owner. Do not let the general outage
            # grace preserve an old IP decision after owner connectivity ends.
            max_stale_seconds=(0 if license_data.ip_ranges else OUTAGE_GRACE_SECONDS),
        )
        if status["revoked"]:
            raise InstallationLicenseError("Installation license was revoked by the owner")
        if license_data.ip_ranges and status.get("binding_valid") is not True:
            raise InstallationLicenseError("Installation source IP is outside the licensed ranges")
        # The signed payload was just verified, including its timestamps.
        payload = signed_status.decode("ascii").split(".", 1)[0]
        padded = payload + "=" * (-len(payload) % 4)
        status = json.loads(base64.urlsafe_b64decode(padded))
        return OwnerStatusSnapshot(
            last_owner_check=status["issued_at"],
            using_outage_grace=status["expires_at"] <= now,
        )
    finally:
        if own_client:
            await redis_client.aclose()


async def poll_owner_status_forever() -> None:
    redis_client = Redis.from_url(REDIS_URL)
    try:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    revoked = await poll_owner_status_once(redis_client, client)
                    if revoked:
                        logger.warning("Owner revoked this client installation; new calls are denied")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - keep retrying after network or cache failures
                    logger.warning("Owner installation status check failed: {}", exc)
                await asyncio.sleep(POLL_SECONDS)
    finally:
        await redis_client.aclose()
