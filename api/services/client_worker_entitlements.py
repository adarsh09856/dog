"""Execution-time feature gates for queued work in client installations."""

from api.services.deployment_edition import runtime_edition
from api.services.installation_license import (
    load_license,
    require_feature,
    validate_installation_license,
)
from api.services.owner_installation_status import require_current_owner_status


async def require_client_worker_features(*features: str) -> None:
    """Revalidate client entitlements before a worker touches data or providers.

    Hosted SaaS workers are not installation-license-bound. Client jobs are
    checked at execution time because the grant or owner status may have
    changed after the HTTP request enqueued them.
    """
    if runtime_edition() != "client":
        return

    license_data = load_license()
    validate_installation_license(license_data)
    for feature in features:
        require_feature(license_data, feature)
    await require_current_owner_status(license_data)
