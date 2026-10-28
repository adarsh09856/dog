"""Owner mutations recheck authority and prevent control-plane lockout."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from api.db import owner_user_management as controls


def account(user_id, *, owner=True):
    return SimpleNamespace(id=user_id, is_superuser=owner, is_active=True,
                           email=f"owner{user_id}@example.com", selected_organization_id=None)


def patch_session(monkeypatch, actor, target=None, wallet=None):
    results = [None, SimpleNamespace(scalar_one_or_none=lambda: actor)]
    if target is not None:
        results.append(SimpleNamespace(scalar_one_or_none=lambda: target))
    if wallet is not None:
        results.append(SimpleNamespace(scalar_one_or_none=lambda: wallet))
    session = SimpleNamespace(execute=AsyncMock(side_effect=results), commit=AsyncMock(),
                              add=Mock(), delete=AsyncMock())

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(controls.kodewaves_db_client, "get_session", get_session)
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["is_superuser", "is_active"])
async def test_owner_cannot_demote_or_suspend_self(monkeypatch, field):
    actor = account(1)
    session = patch_session(monkeypatch, actor)
    with pytest.raises(HTTPException) as denied:
        await controls.update_account(1, 1, {field: False})
    assert denied.value.status_code == 409
    assert actor.is_superuser and actor.is_active
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_cannot_delete_self(monkeypatch):
    session = patch_session(monkeypatch, account(1))
    with pytest.raises(HTTPException) as denied:
        await controls.delete_account(1, 1)
    assert denied.value.status_code == 400
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_actor_demoted_since_authentication_cannot_remove_another_owner(monkeypatch, operation):
    actor = account(1, owner=False)
    session = patch_session(monkeypatch, actor)
    with pytest.raises(HTTPException) as denied:
        if operation == "update":
            await controls.update_account(1, 2, {"is_superuser": False})
        else:
            await controls.delete_account(1, 2)
    assert denied.value.status_code == 403
    assert "pg_advisory_xact_lock(492565710844)" in str(session.execute.await_args_list[0].args[0])
    session.commit.assert_not_awaited()
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_owner_can_be_demoted_with_atomic_audit(monkeypatch):
    actor, target = account(1), account(2)
    session = patch_session(monkeypatch, actor, target)
    await controls.update_account(1, 2, {"is_superuser": False})
    assert actor.is_superuser and not target.is_superuser
    audit = session.add.call_args.args[0]
    assert audit.action == "user.update" and audit.actor_id == 1
    assert audit.changes == {"is_superuser": False}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_suspension_also_freezes_selected_workspace(monkeypatch):
    actor, target = account(1), account(2, owner=False)
    target.selected_organization_id = 42
    wallet = SimpleNamespace(is_frozen=False)
    session = patch_session(monkeypatch, actor, target, wallet)
    assert await controls.update_account(1, 2, {"is_active": False}) == 42
    assert not target.is_active and wallet.is_frozen
    assert session.add.call_args.args[0].action == "user.status"
    session.commit.assert_awaited_once()
