from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services import bootstrap_client_admin as bootstrap


@pytest.mark.asyncio
async def test_bootstrap_refuses_hosted_edition_before_database_access(monkeypatch):
    monkeypatch.setattr(bootstrap, "KODEWAVES_EDITION", "saas")
    with pytest.raises(ValueError, match="client installation"):
        await bootstrap.bootstrap_client_admin("owner@example.com", "long-password-123")


@pytest.mark.asyncio
async def test_bootstrap_refuses_short_password_before_database_access(monkeypatch):
    monkeypatch.setattr(bootstrap, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(bootstrap, "AUTH_PROVIDER", "local")
    with pytest.raises(ValueError, match="at least 12"):
        await bootstrap.bootstrap_client_admin("admin@example.com", "short")


@pytest.mark.asyncio
async def test_client_bootstrap_does_not_create_an_unrecoverable_default_api_key(monkeypatch):
    from api.db.models import APIKeyModel

    monkeypatch.setattr(bootstrap, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(bootstrap, "AUTH_PROVIDER", "local")
    monkeypatch.setattr(bootstrap, "load_license", lambda: object())
    monkeypatch.setattr(bootstrap, "validate_installation_license", lambda _license: None)
    monkeypatch.setattr(bootstrap, "verify_configured_release", lambda: None)
    monkeypatch.setattr(bootstrap, "hash_password", lambda _password: "hashed")
    monkeypatch.setattr(bootstrap, "enforce_client_creation_limit", AsyncMock())

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
            return SimpleNamespace(scalar_one=lambda: 0)

        def add(self, item):
            added.append(item)

        async def flush(self):
            for item in added:
                if isinstance(item, bootstrap.UserModel) and item.id is None:
                    item.id = 101
                elif isinstance(item, bootstrap.OrganizationModel) and item.id is None:
                    item.id = 202

    class SessionContext:
        async def __aenter__(self):
            return Session()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(bootstrap.db_client, "async_session", SessionContext)

    administrator_id = await bootstrap.bootstrap_client_admin(
        "Admin@Example.com", "long-enough-password"
    )

    assert administrator_id == 101
    assert any(isinstance(item, bootstrap.UserModel) and item.is_superuser for item in added)
    assert not any(isinstance(item, APIKeyModel) for item in added)
