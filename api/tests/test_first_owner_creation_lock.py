"""First-owner assignment must serialize with owner account mutations."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.user_client import UserClient


@pytest.mark.asyncio
async def test_user_creation_takes_owner_lock_before_count_and_insert(monkeypatch):
    count_result = SimpleNamespace(scalar_one_or_none=lambda: 0)

    async def execute(statement):
        if "count" in str(statement).lower():
            return count_result
        return None

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=execute),
        add=lambda user: setattr(session, "created_user", user),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    @asynccontextmanager
    async def async_session():
        yield session

    client = UserClient.__new__(UserClient)
    client.async_session = async_session
    monkeypatch.setattr(
        "api.db.user_client.enforce_client_creation_limit", AsyncMock()
    )

    user = await client.create_user_with_email(
        email="first@example.com", password_hash="hashed"
    )

    assert user.is_superuser is True
    assert "pg_advisory_xact_lock(492565710844)" in str(
        session.execute.await_args_list[0].args[0]
    )
    assert "count" in str(session.execute.await_args_list[1].args[0]).lower()
    session.commit.assert_awaited_once()

