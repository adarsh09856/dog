"""Superuser maintenance promotions serialize with owner account changes."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import create_superuser


@pytest.mark.asyncio
async def test_existing_account_promotion_takes_owner_lock(monkeypatch):
    user = SimpleNamespace(id=1, is_superuser=False, password_hash="old")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: user)),
        commit=AsyncMock(),
    )

    @asynccontextmanager
    async def async_session():
        yield session

    monkeypatch.setattr(create_superuser.db_client, "get_user_by_email", AsyncMock(return_value=user))
    monkeypatch.setattr(create_superuser.db_client, "async_session", async_session)
    monkeypatch.setattr(create_superuser, "hash_password", lambda _: "new-hash")

    result = await create_superuser.create_or_promote_superuser(
        "owner@example.com", "new-password"
    )

    assert result is user and user.is_superuser is True
    assert "pg_advisory_xact_lock(492565710844)" in str(
        session.execute.await_args_list[0].args[0]
    )
    assert user.password_hash == "new-hash"
    session.commit.assert_awaited_once()

