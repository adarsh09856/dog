"""Owner catalog updates preserve explicit zero grants and reject negative limits."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api.routes.admin import plans
from api.db import saas_plan_catalog


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_plan_write_preserves_zero_minutes_and_resource_quotas(monkeypatch, operation):
    record = SimpleNamespace(id="00000000-0000-0000-0000-000000000007")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(saas_plan_catalog.kodewaves_db_client, "get_session", get_session)
    payload = plans.PlanItem(name="Restricted", code="restricted", monthly_price_cents=100, included_minutes=0,
                             max_agents=0, max_concurrent_calls=0, is_public=False,
                             has_campaigns_access=False)
    if operation == "create":
        await plans.upsert_plan(payload, _user=SimpleNamespace(id=1))
    else:
        await plans.update_plan(record.id, payload, _user=SimpleNamespace(id=1))

    assert record.included_monthly_minutes == 0
    assert record.max_agents == 0
    assert record.max_concurrent_calls == 0
    assert record.is_public is False
    assert record.has_campaigns_access is False
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("field", ["included_minutes", "included_monthly_minutes", "max_agents", "max_concurrent_calls"])
def test_catalog_rejects_negative_grants_and_limits(field):
    with pytest.raises(ValidationError):
        plans.PlanItem(name="Invalid", code="invalid", **{field: -1})


@pytest.mark.asyncio
async def test_selecting_default_serializes_and_clears_prior_defaults(monkeypatch):
    record = SimpleNamespace(id="00000000-0000-0000-0000-000000000007", code="stable-code")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)),
        commit=AsyncMock(), refresh=AsyncMock(),
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(saas_plan_catalog.kodewaves_db_client, "get_session", get_session)
    payload = plans.PlanItem(name="Default", code="stable-code", is_default=True)
    await plans.update_plan(record.id, payload, _user=SimpleNamespace(id=1))

    calls = session.execute.await_args_list
    assert "pg_advisory_xact_lock" in str(calls[0].args[0])
    assert calls[0].args[1] == {"key": "kodewaves:saas-plan-catalog"}
    clear_defaults = calls[2].args[0]
    assert "UPDATE saas_plans" in str(clear_defaults)
    assert clear_defaults.compile().params["is_default"] is False
    assert record.is_default is True
    assert record.code == "stable-code"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(record)


def test_plan_values_preserve_public_visibility_setting():
    values = plans._plan_values(plans.PlanItem(
        name="Owner assigned", code="owner-assigned", is_public=False,
    ))
    assert values["is_public"] is False


@pytest.mark.asyncio
async def test_inactive_default_is_rejected_before_database_changes(monkeypatch):
    get_session = AsyncMock(side_effect=AssertionError("Invalid default opened a transaction"))
    monkeypatch.setattr(saas_plan_catalog.kodewaves_db_client, "get_session", get_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as rejected:
        await plans.upsert_plan(plans.PlanItem(name="Inactive", code="inactive", is_active=False, is_public=False, is_default=True))
    assert rejected.value.status_code == 422
    get_session.assert_not_called()


@pytest.mark.asyncio
async def test_new_plan_cannot_be_activated_or_published_without_an_explicit_price(monkeypatch):
    get_session = AsyncMock(side_effect=AssertionError("Invalid plan opened a transaction"))
    monkeypatch.setattr(saas_plan_catalog.kodewaves_db_client, "get_session", get_session)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as rejected:
        await plans.upsert_plan(plans.PlanItem(
            name="Unpriced", code="unpriced", is_active=False, is_public=True,
        ))
    assert rejected.value.status_code == 422
    get_session.assert_not_called()


@pytest.mark.asyncio
async def test_new_explicitly_free_plan_can_be_published(monkeypatch):
    record = SimpleNamespace(id="free-plan", name="Free")
    save_plan = AsyncMock(return_value=record)
    monkeypatch.setattr(saas_plan_catalog, "save_plan", save_plan)

    await plans.upsert_plan(plans.PlanItem(
        name="Free", code="free", monthly_price_cents=0,
        annual_price_cents=0, is_active=True, is_public=True,
    ))

    assert save_plan.await_args.args[0]["monthly_price_cents"] == 0


@pytest.mark.asyncio
async def test_plan_edit_keeps_existing_zero_price_behavior(monkeypatch):
    record = SimpleNamespace(id="00000000-0000-0000-0000-000000000007")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: record)),
        commit=AsyncMock(), refresh=AsyncMock(),
    )

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(saas_plan_catalog.kodewaves_db_client, "get_session", get_session)
    await plans.update_plan(record.id, plans.PlanItem(
        name="Existing Free", code="existing-free", monthly_price_cents=0,
        annual_price_cents=0, is_active=True, is_public=True,
    ), _user=SimpleNamespace(id=1))
    session.commit.assert_awaited_once()
