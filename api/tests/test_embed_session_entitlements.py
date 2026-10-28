"""Existing public sessions must honor current organization entitlements."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.services.workflow import embed_session_service as service


@pytest.mark.asyncio
async def test_existing_session_loses_access_when_widgets_are_disabled(monkeypatch):
    session = SimpleNamespace(embed_token_id=7, expires_at=None)
    token = SimpleNamespace(is_active=True, allowed_domains=[], organization_id=42)
    monkeypatch.setattr(service.db_client, "get_embed_session_by_token", AsyncMock(return_value=session))
    monkeypatch.setattr(service.db_client, "get_embed_token_by_id", AsyncMock(return_value=token))
    entitlement = AsyncMock(side_effect=HTTPException(status_code=403, detail="Widgets disabled"))
    monkeypatch.setattr(service, "enforce_saas_feature", entitlement)

    with pytest.raises(HTTPException) as denied:
        await service.resolve_embed_session("existing-session", "https://client.example")

    assert denied.value.status_code == 403
    entitlement.assert_awaited_once_with(42, "widgets")


@pytest.mark.asyncio
async def test_allowed_existing_session_still_resolves(monkeypatch):
    session = SimpleNamespace(embed_token_id=7, expires_at=None)
    token = SimpleNamespace(is_active=True, allowed_domains=[], organization_id=42)
    monkeypatch.setattr(service.db_client, "get_embed_session_by_token", AsyncMock(return_value=session))
    monkeypatch.setattr(service.db_client, "get_embed_token_by_id", AsyncMock(return_value=token))
    entitlement = AsyncMock()
    monkeypatch.setattr(service, "enforce_saas_feature", entitlement)

    assert await service.resolve_embed_session("existing-session", "https://client.example") == (session, token)
    entitlement.assert_awaited_once_with(42, "widgets")
