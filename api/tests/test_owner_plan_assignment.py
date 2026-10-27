"""Unrelated owner edits must not remove purchased plan terms."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from api.db import saas_plan_catalog as catalog
from api.routes.admin import users


@pytest.mark.asyncio
async def test_same_plan_preserves_paid_expiry_and_payment_metadata(monkeypatch):
    original = {"plan_code": "stable-code", "expires_at": "2030-01-01T00:00:00+00:00", "payment_id": "paid-order"}
    setting = SimpleNamespace(value=original.copy())
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None,
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(code="stable-code")),
        SimpleNamespace(scalar_one_or_none=lambda: setting),
    ]), commit=AsyncMock(), add=Mock())

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(catalog.kodewaves_db_client, "get_session", get_session)
    assert await catalog.assign_org_plan(42, "stable-code") is False
    assert setting.value == original
    session.commit.assert_not_awaited()
    session.add.assert_not_called()
    assert session.execute.await_args_list[0].args[1] == {"org_id": 42}


@pytest.mark.asyncio
async def test_changed_paid_plan_is_a_finite_owner_grant(monkeypatch):
    setting = SimpleNamespace(value={"plan_code": "old"})
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None,
        SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(monthly_price_cents=100, annual_price_cents=0)),
        SimpleNamespace(scalar_one_or_none=lambda: setting),
    ]), commit=AsyncMock())

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(catalog.kodewaves_db_client, "get_session", get_session)
    before = datetime.now(UTC)
    assert await catalog.assign_org_plan(42, "new") is True
    expiry = datetime.fromisoformat(setting.value["expires_at"])
    assert before + timedelta(days=30) <= expiry <= datetime.now(UTC) + timedelta(days=30)
    assert setting.value["source"] == "owner_grant"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_unknown_plan_rejected_before_changing_any_user(monkeypatch, operation):
    monkeypatch.setattr(catalog.kodewaves_db_client, "get_active_saas_plan", AsyncMock(return_value=None))
    touched_user = AsyncMock(side_effect=AssertionError("User changed before plan validation"))
    monkeypatch.setattr(users.db_client, "get_user_by_email", touched_user)
    monkeypatch.setattr(users.kodewaves_db_client, "get_session", Mock(side_effect=AssertionError("User transaction opened")))
    with pytest.raises(HTTPException) as rejected:
        if operation == "create":
            await users.create_admin_user(users.CreateUserRequest(email="test@example.com", password="test-only", plan_code="missing"))
        else:
            await users.update_admin_user(7, users.UpdateUserRequest(plan_code="missing", is_superuser=True))
    assert rejected.value.status_code == 422
    touched_user.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_superuser", [False, True])
async def test_owner_created_user_receives_role_and_selected_catalog_plan(monkeypatch, is_superuser):
    monkeypatch.setattr(catalog.kodewaves_db_client, "get_active_saas_plan", AsyncMock(return_value=SimpleNamespace(code="growth-v2")))
    assign = AsyncMock()
    monkeypatch.setattr(catalog, "assign_org_plan", assign)
    monkeypatch.setattr(users, "hash_password", lambda password: "test-hash")
    monkeypatch.setattr(users.db_client, "get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(users.db_client, "create_user_with_email", AsyncMock(return_value=SimpleNamespace(id=7, provider_id="test-provider")))
    monkeypatch.setattr(users.db_client, "get_or_create_organization_by_provider_id", AsyncMock(return_value=(SimpleNamespace(id=42), True)))
    monkeypatch.setattr(users.db_client, "add_user_to_organization", AsyncMock())
    monkeypatch.setattr(users.db_client, "update_user_selected_organization", AsyncMock())
    monkeypatch.setattr(users, "ensure_organization_bootstrapped", AsyncMock())
    monkeypatch.setattr(users.kodewaves_db_client, "get_or_create_wallet", AsyncMock())
    grant_minutes = AsyncMock()
    monkeypatch.setattr(users.kodewaves_db_client, "add_minutes", grant_minutes)

    result = await users.create_admin_user(users.CreateUserRequest(
        email="test@example.com", password="test-only", plan_code="growth-v2", initial_minutes=0,
        is_superuser=is_superuser,
    ))
    assert result["organization_id"] == 42
    users.db_client.create_user_with_email.assert_awaited_once_with(
        email="test@example.com", password_hash="test-hash", name=None,
        is_superuser=is_superuser,
    )
    assign.assert_awaited_once_with(42, "growth-v2")
    grant_minutes.assert_not_awaited()
