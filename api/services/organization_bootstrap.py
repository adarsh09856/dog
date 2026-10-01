"""Once-per-organization sovereign provisioning for Kodewaves.

In Kodewaves sovereign mode, organizations operate independently without external
Kodewaves MPS (Managed Platform Services) or auto-provisioned Cloudonix SIP.
Telephony is configured directly by administrators or users (Twilio, Exotel, Plivo,
Telnyx, Custom SIP Trunks, WebRTC).
"""

from datetime import timedelta

from loguru import logger

from api.db import db_client
from api.db.organization_configuration_client import LEASE_COMPLETED
from api.enums import OrganizationConfigurationKey
from api.schemas.ai_model_configuration import (
    DograhManagedAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
)
from api.services.configuration.ai_model_configuration import (
    get_organization_ai_model_configuration_v2,
    upsert_organization_ai_model_configuration_v2,
)

# A holder that dies mid-provisioning leaves its lease pending.
BOOTSTRAP_LEASE_STALE_AFTER = timedelta(minutes=5)

_BOOTSTRAP_KEY = OrganizationConfigurationKey.ORGANIZATION_BOOTSTRAP.value


async def ensure_organization_bootstrapped(
    organization_id: int,
    *,
    created_by: str,
) -> bool:
    """Ensure an organization is bootstrapped for sovereign operation.

    Cheap enough to call on every authenticated request: an organization that
    has completed bootstrap costs a single indexed read. Returns True when the
    organization is fully provisioned.
    """
    if await _is_bootstrap_complete(organization_id):
        return True

    owner_token = await db_client.claim_configuration_lease(
        organization_id,
        _BOOTSTRAP_KEY,
        BOOTSTRAP_LEASE_STALE_AFTER,
    )
    if owner_token is None:
        # Another request holds the lease
        return False

    try:
        # Mark lease completed for Kodewaves sovereign platform
        await db_client.complete_configuration_lease(
            organization_id, _BOOTSTRAP_KEY, owner_token
        )
        return True
    except Exception:
        await db_client.release_configuration_lease(
            organization_id, _BOOTSTRAP_KEY, owner_token
        )
        logger.warning(
            "Failed to bootstrap organization {}; will retry on a later request",
            organization_id,
            exc_info=True,
        )
        return False


async def _is_bootstrap_complete(organization_id: int) -> bool:
    row = await db_client.get_configuration(organization_id, _BOOTSTRAP_KEY)
    return bool(row and (row.value or {}).get("status") == LEASE_COMPLETED)


async def _has_managed_sip_connectivity(organization_id: int) -> bool:
    """Sovereign platform has direct user-configured SIP trunks."""
    return True


async def provision_managed_sip_connectivity(
    organization_id: int,
    *,
    created_by: str,
) -> bool:
    """Sovereign SIP: no external Cloudonix auto-provisioning."""
    return True
