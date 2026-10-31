from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.services.saas_entitlements import active_plan_code
from api.services.saas_entitlements import resolve_plan_feature, resolve_plan_limit

FEATURE_COLUMNS = {
    "crm": "has_crm_access",
    "appointments": "has_appointments_access",
    "forms": "has_forms_access",
    "widgets": "has_widget_access",
    "campaigns": "has_campaigns_access",
    "byok": "allow_user_byok",
}


@pytest.fixture(autouse=True)
def isolated_entitlement_settings(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client

    monkeypatch.setattr(kodewaves_db_client, "get_setting", AsyncMock(return_value=None))


@pytest.mark.parametrize("feature,column", FEATURE_COLUMNS.items())
def test_owner_can_explicitly_grant_or_disable_plan_feature(feature, column):
    assert resolve_plan_feature(
        SimpleNamespace(**{column: False}), {f"enable_{feature}": True}, feature
    ) is True
    assert resolve_plan_feature(
        SimpleNamespace(**{column: True}), {f"enable_{feature}": False}, feature
    ) is False


@pytest.mark.parametrize("limit_name", ["max_agents", "max_concurrent_calls"])
def test_owner_quota_replaces_plan_default_and_preserves_zero(limit_name):
    plan = SimpleNamespace(**{limit_name: 2})
    assert resolve_plan_limit(plan, {limit_name: 10}, limit_name) == 10
    assert resolve_plan_limit(plan, {limit_name: 0}, limit_name) == 0
    assert resolve_plan_limit(plan, {}, limit_name) == 2


@pytest.mark.asyncio
async def test_owner_disabled_crm_blocks_http_even_when_plan_allows(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.db.kodewaves_client import kodewaves_db_client
    from api.routes import crm
    from api.services import saas_entitlements as entitlements
    from api.services.auth.depends import get_user

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        entitlements, "get_org_saas_plan",
        AsyncMock(return_value=SimpleNamespace(has_crm_access=True)),
    )
    setting = AsyncMock(return_value={"enable_crm": False})
    monkeypatch.setattr(kodewaves_db_client, "get_setting", setting)
    app = FastAPI()
    app.include_router(crm.router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=7, selected_organization_id=42
    )

    response = TestClient(app).get("/crm/contacts")

    assert response.status_code == 403
    setting.assert_awaited_once_with("org_features_42", raise_on_error=True)


@pytest.mark.asyncio
async def test_entitlement_storage_failure_does_not_grant_access(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client
    from api.services import saas_entitlements as entitlements

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(kodewaves_db_client, "get_setting", AsyncMock(side_effect=RuntimeError("store unavailable")))
    with pytest.raises(RuntimeError, match="store unavailable"):
        await entitlements.enforce_saas_feature(42, "crm")


@pytest.mark.asyncio
async def test_high_plan_limit_is_not_reduced_by_an_unrelated_default(monkeypatch):
    from api.services.call_concurrency import service

    monkeypatch.setattr(service, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(service, "get_org_saas_limit", AsyncMock(return_value=10))
    monkeypatch.setattr(service.db_client, "get_configuration", AsyncMock(return_value=None))
    assert await service.CallConcurrencyService().get_org_concurrent_limit(42) == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("source,feature", [("campaign:7", "campaigns"), ("public_embed", "widgets")])
async def test_owner_feature_disabled_denies_call_before_slot_admission(monkeypatch, source, feature):
    from api.services.call_concurrency import service

    gate = AsyncMock(side_effect=HTTPException(status_code=403, detail="Disabled by owner"))
    acquire = AsyncMock()
    monkeypatch.setattr(service, "enforce_saas_feature", gate)
    monkeypatch.setattr(service.rate_limiter, "try_acquire_concurrent_slot_details", acquire)
    with pytest.raises(service.CallConcurrencyLimitError):
        await service.CallConcurrencyService().acquire_org_slot(42, source=source)
    gate.assert_awaited_once_with(42, feature)
    acquire.assert_not_awaited()


@pytest.mark.parametrize(
    ("module_name", "path", "column"),
    [
        ("crm", "/crm/contacts", "has_crm_access"),
        ("appointments", "/appointments", "has_appointments_access"),
        ("forms", "/forms", "has_forms_access"),
        ("widgets", "/widgets", "has_widget_access"),
        ("campaign", "/campaign/", "has_campaigns_access"),
        ("workflow_embed", "/workflow/42/embed-token", "has_widget_access"),
    ],
)
def test_disabled_feature_is_rejected_through_real_http_router(
    monkeypatch, module_name, path, column
):
    from importlib import import_module

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.services import saas_entitlements as entitlements
    from api.services.auth.depends import get_user

    plan_lookup = AsyncMock(return_value=SimpleNamespace(**{column: False}))
    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(entitlements, "get_org_saas_plan", plan_lookup)
    app = FastAPI()
    app.include_router(import_module(f"api.routes.{module_name}").router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=7, selected_organization_id=42
    )

    response = TestClient(app).get(path)

    assert response.status_code == 403
    assert "current plan does not include" in response.json()["detail"]
    plan_lookup.assert_awaited_once_with(42)


def test_enabled_appointment_feature_reaches_only_selected_workspace(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import appointments
    from api.services import saas_entitlements as entitlements
    from api.services.auth.depends import get_user

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        entitlements, "get_org_saas_plan",
        AsyncMock(return_value=SimpleNamespace(has_appointments_access=True)),
    )
    listing = AsyncMock(return_value=[])
    monkeypatch.setattr(appointments.appointment_db, "list_appointments", listing)
    app = FastAPI()
    app.include_router(appointments.router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=7, selected_organization_id=42
    )

    response = TestClient(app).get("/appointments")

    assert response.status_code == 200
    assert response.json() == []
    listing.assert_awaited_once_with(42)


def test_active_plan_code_accepts_legacy_assignment_without_expiry():
    assert active_plan_code({"plan_code": "pro"}) == "pro"


def test_active_plan_code_rejects_expired_assignment():
    now = datetime(2026, 10, 25, tzinfo=UTC)
    assignment = {
        "plan_code": "pro",
        "expires_at": (now - timedelta(seconds=1)).isoformat(),
    }
    assert active_plan_code(assignment, now=now) is None


def test_active_plan_code_accepts_future_assignment():
    now = datetime(2026, 10, 25, tzinfo=UTC)
    assignment = {
        "plan_code": "pro",
        "expires_at": (now + timedelta(days=1)).isoformat(),
    }
    assert active_plan_code(assignment, now=now) == "pro"


def test_active_plan_code_fails_closed_on_malformed_expiry():
    assert active_plan_code({"plan_code": "pro", "expires_at": "not-a-date"}) is None


@pytest.mark.asyncio
async def test_plan_resolver_uses_default_after_assignment_expiry(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client
    from api.services import saas_entitlements as entitlements

    default_plan = SimpleNamespace(code="starter")
    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        kodewaves_db_client,
        "get_setting",
        AsyncMock(return_value={
            "plan_code": "pro",
            "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        }),
    )
    active_plan = AsyncMock(return_value=None)
    default = AsyncMock(return_value=default_plan)
    monkeypatch.setattr(kodewaves_db_client, "get_active_saas_plan", active_plan)
    monkeypatch.setattr(kodewaves_db_client, "get_default_saas_plan", default)

    assert await entitlements.get_org_saas_plan(42) is default_plan
    active_plan.assert_not_awaited()
    default.assert_awaited_once()


@pytest.mark.asyncio
async def test_plan_resolver_fails_closed_when_no_active_default_or_starter_exists(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client
    from api.services import saas_entitlements as entitlements

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(kodewaves_db_client, "get_setting", AsyncMock(return_value=None))
    monkeypatch.setattr(kodewaves_db_client, "get_default_saas_plan", AsyncMock(return_value=None))
    monkeypatch.setattr(kodewaves_db_client, "get_active_saas_plan", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as error:
        await entitlements.get_org_saas_plan(42)

    assert error.value.status_code == 503
    assert "No active SaaS plan" in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(("feature", "column"), FEATURE_COLUMNS.items())
async def test_disabled_plan_feature_is_denied_at_server_boundary(monkeypatch, feature, column):
    from api.services import saas_entitlements as entitlements

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        entitlements,
        "get_org_saas_plan",
        AsyncMock(return_value=SimpleNamespace(**{column: False})),
    )

    with pytest.raises(HTTPException) as exc_info:
        await entitlements.enforce_saas_feature(42, feature)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_client_edition_uses_license_middleware_instead_of_saas_plan(monkeypatch):
    from api.services import saas_entitlements as entitlements

    resolve_plan = AsyncMock(side_effect=AssertionError("SaaS plan must not be queried"))
    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(entitlements, "get_org_saas_plan", resolve_plan)

    await entitlements.enforce_saas_feature(42, "crm")
    resolve_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_saas_feature_check_denies_missing_selected_organization(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client
    from api.services import saas_entitlements as entitlements

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    get_setting = AsyncMock()
    plan_lookup = AsyncMock()
    monkeypatch.setattr(kodewaves_db_client, "get_setting", get_setting)
    monkeypatch.setattr(entitlements, "get_org_saas_plan", plan_lookup)

    assert await entitlements.is_saas_feature_allowed(None, "crm") is False
    with pytest.raises(HTTPException) as error:
        await entitlements.enforce_saas_feature(None, "crm")

    assert error.value.status_code == 403
    assert "organization" in error.value.detail.lower()
    get_setting.assert_not_awaited()
    plan_lookup.assert_not_awaited()


def test_saas_http_feature_guard_rejects_user_without_selected_organization(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import crm
    from api.services import saas_entitlements as entitlements
    from api.services.auth.depends import get_user

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "saas")
    app = FastAPI()
    app.include_router(crm.router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=7, selected_organization_id=None
    )

    response = TestClient(app).get("/crm/contacts")

    assert response.status_code == 403
    assert "organization" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_client_edition_allows_license_middleware_to_authorize_missing_org(monkeypatch):
    from api.services import saas_entitlements as entitlements

    monkeypatch.setattr(entitlements, "KODEWAVES_EDITION", "client")

    assert await entitlements.is_saas_feature_allowed(None, "crm") is True
    await entitlements.enforce_saas_feature(None, "crm")


@pytest.mark.asyncio
async def test_org_call_limit_is_capped_by_active_plan(monkeypatch):
    from api.services.call_concurrency import service as service_module
    from api.db.kodewaves_client import kodewaves_db_client

    monkeypatch.setattr(service_module, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        service_module,
        "get_org_saas_limit",
        AsyncMock(return_value=3),
    )
    monkeypatch.setattr(
        service_module.db_client,
        "get_configuration",
        AsyncMock(return_value=SimpleNamespace(value={"value": 8})),
    )
    monkeypatch.setattr(
        kodewaves_db_client,
        "get_setting",
        AsyncMock(return_value={"default_org_concurrency_limit": 10}),
    )

    assert await service_module.CallConcurrencyService().get_org_concurrent_limit(42) == 3


@pytest.mark.asyncio
async def test_zero_plan_call_limit_is_not_treated_as_missing(monkeypatch):
    from api.services.call_concurrency import service as service_module
    from api.db.kodewaves_client import kodewaves_db_client

    monkeypatch.setattr(service_module, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        service_module,
        "get_org_saas_limit",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(service_module.db_client, "get_configuration", AsyncMock(return_value=None))
    monkeypatch.setattr(
        kodewaves_db_client,
        "get_setting",
        AsyncMock(return_value={"default_org_concurrency_limit": 10}),
    )

    assert await service_module.CallConcurrencyService().get_org_concurrent_limit(42) == 0


@pytest.mark.asyncio
async def test_agent_creation_is_denied_at_organization_plan_limit(monkeypatch):
    from api.db.models import WorkflowModel
    from api.services import client_creation_limits as limits_module

    monkeypatch.setattr(limits_module, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        limits_module,
        "get_org_saas_limit",
        AsyncMock(return_value=3),
    )
    count_result = SimpleNamespace(scalar_one=lambda: 3)
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None, count_result]))

    with pytest.raises(HTTPException) as exc_info:
        await limits_module.enforce_saas_creation_limit(
            session,
            organization_id=42,
            limit_name="max_agents",
            model=WorkflowModel,
        )

    assert exc_info.value.status_code == 403
    assert "max_agents" in exc_info.value.detail
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_saas_agent_creation_without_organization_fails_closed(monkeypatch):
    from api.db.models import WorkflowModel
    from api.services import client_creation_limits as limits_module

    monkeypatch.setattr(limits_module, "KODEWAVES_EDITION", "saas")
    plan_lookup = AsyncMock()
    monkeypatch.setattr(limits_module, "get_org_saas_limit", plan_lookup)
    session = SimpleNamespace(execute=AsyncMock())

    with pytest.raises(HTTPException) as error:
        await limits_module.enforce_saas_creation_limit(
            session,
            organization_id=None,
            limit_name="max_agents",
            model=WorkflowModel,
        )

    assert error.value.status_code == 403
    assert "organization" in error.value.detail.lower()
    session.execute.assert_not_awaited()
    plan_lookup.assert_not_awaited()
