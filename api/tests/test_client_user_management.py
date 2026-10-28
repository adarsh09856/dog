from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import installation


def test_client_user_routes_reject_hosted_edition(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "saas")
    with pytest.raises(HTTPException) as exc:
        installation._require_client_workspace(SimpleNamespace(selected_organization_id=1))
    assert exc.value.status_code == 404


def test_client_user_routes_require_selected_workspace(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(installation, "AUTH_PROVIDER", "local")
    with pytest.raises(HTTPException) as exc:
        installation._require_client_workspace(SimpleNamespace(selected_organization_id=None))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_admin_cannot_suspend_own_account(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(installation, "AUTH_PROVIDER", "local")
    administrator = SimpleNamespace(id=7, selected_organization_id=2)
    with pytest.raises(HTTPException) as exc:
        await installation.update_client_user_status(
            7, installation.ClientUserStatus(active=False), administrator
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_user_creation_uses_admin_workspace(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(installation, "AUTH_PROVIDER", "local")
    observed = {}

    async def create(organization_id, email, password):
        observed.update(organization_id=organization_id, email=email, password=password)
        return SimpleNamespace(id=8, email=email, is_active=True, is_superuser=False)

    monkeypatch.setattr(installation, "create_workspace_user", create)
    created = await installation.create_client_user(
        installation.ClientUserCreate(email="USER@example.com", password="long-password-123"),
        SimpleNamespace(selected_organization_id=2),
    )
    assert observed == {
        "organization_id": 2,
        "email": "USER@example.com",
        "password": "long-password-123",
    }
    assert created == {"id": 8, "email": "USER@example.com", "is_active": True, "is_superuser": False}


@pytest.mark.asyncio
async def test_client_workspace_creation_uses_admin_identity(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(installation, "AUTH_PROVIDER", "local")
    observed = {}

    async def create(administrator_id, name):
        observed.update(administrator_id=administrator_id, name=name)
        return 12

    monkeypatch.setattr(installation, "create_admin_workspace", create)
    created = await installation.create_client_workspace(
        installation.ClientWorkspaceCreate(name=" Operations "),
        SimpleNamespace(id=7, selected_organization_id=2),
    )
    assert observed == {"administrator_id": 7, "name": "Operations"}
    assert created == {"id": 12, "name": "Operations"}


@pytest.mark.asyncio
async def test_new_client_workspace_does_not_store_an_unrecoverable_api_key(monkeypatch):
    from api.db import client_workspace_management as workspaces
    from api.db.kodewaves_models import GlobalPlatformSettingModel
    from api.db.models import APIKeyModel

    administrator = SimpleNamespace(id=7, is_superuser=True, selected_organization_id=2)
    added = []

    class Transaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    class Session:
        def begin(self):
            return Transaction()

        async def execute(self, _statement):
            return SimpleNamespace()

        async def get(self, _model, _user_id, **_kwargs):
            return administrator

        def add(self, item):
            added.append(item)

        async def flush(self):
            for item in added:
                if isinstance(item, workspaces.OrganizationModel):
                    item.id = 12

    class SessionContext:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(workspaces.db_client, "async_session", SessionContext)
    monkeypatch.setattr(workspaces, "enforce_client_creation_limit", AsyncMock())

    organization_id = await workspaces.create_admin_workspace(7, "Operations")

    assert organization_id == 12
    assert administrator.selected_organization_id == 12
    assert any(isinstance(item, GlobalPlatformSettingModel) for item in added)
    assert not any(isinstance(item, APIKeyModel) for item in added)
