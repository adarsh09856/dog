"""Resolve server-managed SaaS plan entitlements for an organization."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException

from api.constants import KODEWAVES_EDITION


def active_plan_code(assignment: object, *, now: datetime | None = None) -> str | None:
    """Return an assigned plan code only while its optional expiry is in the future."""
    if not isinstance(assignment, dict):
        return None
    code = assignment.get("plan_code")
    if not isinstance(code, str) or not code.strip():
        return None
    expires_at = assignment.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= (now or datetime.now(UTC)):
            return None
    return code.strip()


async def get_org_saas_plan(organization_id: int):
    """Resolve the organization's active SaaS plan; client licenses remain authoritative."""
    if KODEWAVES_EDITION == "client":
        return None

    # Import lazily: database client setup imports workflow/campaign clients,
    # which also depend on the creation-limit service importing this module.
    from api.db.kodewaves_client import kodewaves_db_client

    assignment = await kodewaves_db_client.get_setting(
        f"org_plan_{organization_id}", raise_on_error=True
    )
    code = active_plan_code(assignment)
    if code:
        plan = await kodewaves_db_client.get_active_saas_plan(code)
        if plan is not None:
            return plan
    # Expired, missing, or deactivated assignments fall back to the configured
    # default plan. If none is configured, the historical starter behavior applies.
    plan = await kodewaves_db_client.get_default_saas_plan()
    if plan is not None:
        return plan
    return await kodewaves_db_client.get_active_saas_plan("starter")


_PLAN_FEATURE_COLUMNS = {
    "crm": "has_crm_access",
    "appointments": "has_appointments_access",
    "forms": "has_forms_access",
    "widgets": "has_widget_access",
    "byok": "allow_user_byok",
    "campaigns": "has_campaigns_access",
}


def resolve_plan_feature(plan, overrides: object, feature: str) -> bool:
    """An explicit owner grant/denial overrides the catalog plan default."""
    if feature not in _PLAN_FEATURE_COLUMNS:
        raise ValueError(f"Unknown SaaS plan feature: {feature}")
    flag = f"enable_{feature}"
    if isinstance(overrides, dict) and flag in overrides:
        return overrides[flag] is True
    column = _PLAN_FEATURE_COLUMNS[feature]
    return plan is None or column is None or bool(getattr(plan, column))


def resolve_plan_limit(plan, overrides: object, limit_name: str) -> int | None:
    """Resolve an owner quota, falling back to the plan when it is unset."""
    if limit_name not in {"max_agents", "max_concurrent_calls"}:
        raise ValueError(f"Unknown SaaS plan limit: {limit_name}")
    value = overrides.get(limit_name) if isinstance(overrides, dict) else None
    if value is None and plan is not None:
        value = getattr(plan, limit_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid SaaS {limit_name} quota")
    return value


async def is_saas_feature_allowed(organization_id: int | None, feature: str) -> bool:
    if KODEWAVES_EDITION == "client" or organization_id is None:
        return True
    from api.db.kodewaves_client import kodewaves_db_client

    overrides = await kodewaves_db_client.get_setting(
        f"org_features_{organization_id}", raise_on_error=True
    )
    plan = await get_org_saas_plan(organization_id)
    return resolve_plan_feature(plan, overrides, feature)


async def get_org_saas_limit(organization_id: int, limit_name: str) -> int | None:
    if KODEWAVES_EDITION == "client":
        return None
    from api.db.kodewaves_client import kodewaves_db_client

    overrides = await kodewaves_db_client.get_setting(
        f"org_quotas_{organization_id}", raise_on_error=True
    )
    plan = await get_org_saas_plan(organization_id)
    return resolve_plan_limit(plan, overrides, limit_name)


async def enforce_saas_feature(organization_id: int | None, feature: str) -> None:
    """Reject SaaS API actions when the active plan does not include a feature."""
    if KODEWAVES_EDITION == "client" or organization_id is None:
        return
    if not await is_saas_feature_allowed(organization_id, feature):
        raise HTTPException(
            status_code=403,
            detail=f"Your current plan does not include {feature} access or it has been disabled by the administrator.",
        )


def require_saas_feature(feature: str):
    """Create an authenticated route dependency for an organization plan feature."""
    if feature not in _PLAN_FEATURE_COLUMNS:
        raise ValueError(f"Unknown SaaS plan feature: {feature}")
    # Lazy import avoids the auth/db/service initialization cycle.
    from api.services.auth.depends import get_user

    async def dependency(user=Depends(get_user)):
        await enforce_saas_feature(user.selected_organization_id, feature)

    return dependency
