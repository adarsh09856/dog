from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from api.routes.admin import client_installations as client_installations_admin
from api.services.auth import depends as auth_dependencies


@pytest.mark.asyncio
async def test_integrity_alert_routes_deny_nonowners_and_org_keys_but_allow_superadmin(monkeypatch):
    non_superadmin = SimpleNamespace(
        id=8, is_superuser=False, is_active=True, selected_organization_id=101,
    )
    # This organization member belongs to a different tenant from the alert;
    # integrity alerts are global owner data and must never be tenant-readable.
    cross_tenant_user = SimpleNamespace(
        id=9, is_superuser=False, is_active=True, selected_organization_id=202,
    )
    superadmin = SimpleNamespace(id=7, is_superuser=True, is_active=True)
    users_by_token = {
        "Bearer tenant-a-session": non_superadmin,
        "Bearer tenant-b-session": cross_tenant_user,
        "Bearer owner-session": superadmin,
    }
    get_user = AsyncMock(side_effect=lambda authorization, *_args: users_by_token[authorization])

    monkeypatch.setattr(auth_dependencies, "get_user", get_user)
    alerts = AsyncMock(return_value=[{
        "id": 41, "installation_id": "client-1", "customer_id": "tenant-a-customer",
    }])
    acknowledge = AsyncMock(return_value=True)
    monkeypatch.setattr(client_installations_admin, "list_client_integrity_alerts", alerts)
    monkeypatch.setattr(client_installations_admin, "acknowledge_client_integrity_alert", acknowledge)

    app = FastAPI()
    app.include_router(client_installations_admin.router, prefix="/admin")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://owner") as client:
        for authorization in ("Bearer tenant-a-session", "Bearer tenant-b-session"):
            headers = {"Authorization": authorization}
            denied_list = await client.get("/admin/client-installations/alerts", headers=headers)
            denied_ack = await client.post(
                "/admin/client-installations/alerts/41/acknowledge", headers=headers,
            )
            assert denied_list.status_code == 403
            assert denied_ack.status_code == 403
        alerts.assert_not_awaited()
        acknowledge.assert_not_awaited()

        # Organization API keys stay scoped even if their creator is a
        # superadmin; they cannot read or acknowledge global owner alerts.
        api_key_headers = {"X-API-Key": "organization-key"}
        key_list = await client.get("/admin/client-installations/alerts", headers=api_key_headers)
        key_ack = await client.post(
            "/admin/client-installations/alerts/41/acknowledge", headers=api_key_headers,
        )
        assert key_list.status_code == 403
        assert key_ack.status_code == 403
        assert "API keys cannot access owner controls" in key_list.json()["detail"]
        assert "API keys cannot access owner controls" in key_ack.json()["detail"]
        alerts.assert_not_awaited()
        acknowledge.assert_not_awaited()

        owner_headers = {"Authorization": "Bearer owner-session"}
        allowed_list = await client.get("/admin/client-installations/alerts", headers=owner_headers)
        allowed_ack = await client.post(
            "/admin/client-installations/alerts/41/acknowledge", headers=owner_headers,
        )
        assert allowed_list.status_code == 200
        assert allowed_list.json() == [{
            "id": 41, "installation_id": "client-1", "customer_id": "tenant-a-customer",
        }]
        assert allowed_ack.status_code == 200
        assert allowed_ack.json() == {"acknowledged": True}
        alerts.assert_awaited_once_with()
        acknowledge.assert_awaited_once_with(41, 7)
        assert get_user.await_count == 6  # Tenant and owner sessions; API keys bypass user auth.
        alerts.assert_awaited_once_with()
        acknowledge.assert_awaited_once_with(41, 7)
