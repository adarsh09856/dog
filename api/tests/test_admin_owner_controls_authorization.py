from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from api.routes.admin import client_installations as client_installations_admin
from api.routes.admin import plans as plans_admin
from api.routes.admin import settings as settings_admin
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
