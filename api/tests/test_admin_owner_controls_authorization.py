from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api.routes.admin import client_installations as client_installations_admin
from api.routes.admin import plans as plans_admin
from api.routes.admin import settings as settings_admin
from api.routes.admin import users as users_admin
from api.routes import superuser as superuser_routes
from api.services.auth import depends as auth_dependencies


@pytest.mark.asyncio
async def test_owner_plan_settings_and_installation_routes_deny_tenants_and_api_keys(monkeypatch):
    tenant_user = SimpleNamespace(
        id=8, is_superuser=False, is_active=True, selected_organization_id=101,
    )
    other_tenant_user = SimpleNamespace(
        id=9, is_superuser=False, is_active=True, selected_organization_id=202,
    )
    users_by_token = {
        "Bearer tenant-session": tenant_user,
        "Bearer other-tenant-session": other_tenant_user,
    }
    get_user = AsyncMock(side_effect=lambda authorization, *_args: users_by_token[authorization])
    monkeypatch.setattr(auth_dependencies, "get_user", get_user)

    list_plans = AsyncMock(return_value=[])
    get_settings = AsyncMock(return_value={})
    list_installations = AsyncMock(return_value=[])
    monkeypatch.setattr(plans_admin.saas_plan_catalog, "list_plans", list_plans)
    monkeypatch.setattr(settings_admin.kodewaves_db_client, "get_settings_map", get_settings)
    monkeypatch.setattr(
        client_installations_admin, "list_client_installation_records", list_installations,
    )

    app = FastAPI()
    app.include_router(plans_admin.router, prefix="/admin")
    app.include_router(settings_admin.router, prefix="/admin")
    app.include_router(client_installations_admin.router, prefix="/admin")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://owner",
    ) as client:
        for authorization in ("Bearer tenant-session", "Bearer other-tenant-session"):
            headers = {"Authorization": authorization}
            responses = [
                await client.get("/admin/plans", headers=headers),
                await client.get("/admin/settings", headers=headers),
                await client.get("/admin/client-installations", headers=headers),
            ]
            assert [response.status_code for response in responses] == [403, 403, 403]

        api_key_responses = [
            await client.get("/admin/plans", headers={"X-API-Key": "organization-key"}),
            await client.get("/admin/settings", headers={"X-API-Key": "organization-key"}),
            await client.get(
                "/admin/client-installations", headers={"X-API-Key": "organization-key"},
            ),
        ]
        assert [response.status_code for response in api_key_responses] == [403, 403, 403]
        assert all("API keys cannot access owner controls" in response.json()["detail"]
                   for response in api_key_responses)

    list_plans.assert_not_awaited()
    get_settings.assert_not_awaited()
    list_installations.assert_not_awaited()
    assert get_user.await_count == 6


@pytest.mark.asyncio
async def test_owner_user_and_impersonation_routes_deny_tenants_and_api_keys(monkeypatch):
    """User enumeration and both impersonation paths stay owner-session only."""
    tenant_user = SimpleNamespace(is_superuser=False, is_active=True)
    other_tenant_user = SimpleNamespace(is_superuser=False, is_active=True)
    users_by_token = {
        "Bearer tenant-session": tenant_user,
        "Bearer other-tenant-session": other_tenant_user,
    }
    get_user = AsyncMock(side_effect=lambda authorization, *_args: users_by_token[authorization])
    monkeypatch.setattr(auth_dependencies, "get_user", get_user)

    get_session = MagicMock()
    monkeypatch.setattr(users_admin.kodewaves_db_client, "get_session", get_session)
    impersonate_db_lookup = AsyncMock()
    monkeypatch.setattr(superuser_routes.db_client, "get_user_by_id", impersonate_db_lookup)

    app = FastAPI()
    app.include_router(users_admin.router, prefix="/admin")
    app.include_router(superuser_routes.router)
    owner_routes = (
        ("GET", "/admin/users", None),
        ("POST", "/admin/users/123/impersonate", None),
        ("POST", "/superuser/impersonate", {"user_id": 123}),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://owner",
    ) as client:
        for authorization in ("Bearer tenant-session", "Bearer other-tenant-session"):
            for method, path, payload in owner_routes:
                response = await client.request(
                    method, path, headers={"Authorization": authorization}, json=payload,
                )
                assert response.status_code == 403, (method, path, authorization)

        for method, path, payload in owner_routes:
            response = await client.request(
                method, path, headers={"X-API-Key": "organization-key"}, json=payload,
            )
            assert response.status_code == 403, (method, path, "organization API key")
            assert "API keys cannot access owner controls" in response.json()["detail"]

    get_session.assert_not_called()
    impersonate_db_lookup.assert_not_awaited()
    assert get_user.await_count == 6


@pytest.mark.asyncio
async def test_active_superadmin_session_reaches_user_and_impersonation_handlers(monkeypatch):
    """Owner auth allows the routes to run; handler outcomes come from their own logic."""
    superadmin = SimpleNamespace(is_superuser=True, is_active=True)
    get_user = AsyncMock(return_value=superadmin)
    monkeypatch.setattr(auth_dependencies, "get_user", get_user)

    class EmptyResult:
        def scalars(self):
            return self

        def all(self):
            return []

        def scalar_one_or_none(self):
            return None

    class Session:
        execute = AsyncMock(return_value=EmptyResult())

    class SessionContext:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return False

    get_session = MagicMock(return_value=SessionContext())
    monkeypatch.setattr(users_admin.kodewaves_db_client, "get_session", get_session)

    app = FastAPI()
    app.include_router(users_admin.router, prefix="/admin")
    app.include_router(superuser_routes.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://owner",
    ) as client:
        users_response = await client.get(
            "/admin/users", headers={"Authorization": "Bearer superadmin-session"},
        )
        admin_impersonate_response = await client.post(
            "/admin/users/123/impersonate",
            headers={"Authorization": "Bearer superadmin-session"},
        )
        superuser_impersonate_response = await client.post(
            "/superuser/impersonate",
            headers={"Authorization": "Bearer superadmin-session"}, json={},
        )

    assert users_response.status_code == 200
    assert users_response.json() == []
    assert admin_impersonate_response.status_code == 404
    assert superuser_impersonate_response.status_code == 400
    assert get_user.await_count == 3
