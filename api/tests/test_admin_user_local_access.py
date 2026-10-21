from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes.admin import users


@pytest.mark.asyncio
async def test_local_ai_access_change_invalidates_catalog_for_all_workers(monkeypatch):
    user = SimpleNamespace(selected_organization_id=12, is_superuser=False, is_active=True)

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __init__(self):
            self.results = iter((Result(user), Result(None)))
            self.commit = AsyncMock()

        async def execute(self, _statement):
            return next(self.results)

    session = Session()

    @asynccontextmanager
    async def get_session():
        yield session

    monkeypatch.setattr(users.kodewaves_db_client, "get_session", get_session)
    monkeypatch.setattr(users.kodewaves_db_client, "set_setting", AsyncMock())
    monkeypatch.setattr(users.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(users.catalog_service, "notify_changed", AsyncMock())

    result = await users.update_admin_user(
        7,
        users.UpdateUserRequest(has_local_ai_access=True),
        _user=SimpleNamespace(is_superuser=True),
    )

    assert result == {"message": "User #7 updated successfully"}
    assert session.commit.await_count == 1
    assert users.kodewaves_db_client.set_setting.await_count == 2
    users.catalog_service.notify_changed.assert_awaited_once()
