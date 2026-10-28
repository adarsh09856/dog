from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes.admin import users


@pytest.mark.asyncio
async def test_local_ai_access_change_invalidates_catalog_for_all_workers(monkeypatch):
    update_account = AsyncMock(return_value=12)
    monkeypatch.setattr(users.owner_user_management, "update_account", update_account)
    monkeypatch.setattr(users.kodewaves_db_client, "set_setting", AsyncMock())
    monkeypatch.setattr(users.kodewaves_db_client, "get_setting", AsyncMock(return_value={}))
    monkeypatch.setattr(users.catalog_service, "notify_changed", AsyncMock())

    result = await users.update_admin_user(
        7,
        users.UpdateUserRequest(has_local_ai_access=True),
        _user=SimpleNamespace(id=1, is_superuser=True),
    )

    assert result == {"message": "User #7 updated successfully"}
    update_account.assert_awaited_once_with(1, 7, {})
    assert users.kodewaves_db_client.set_setting.await_count == 2
    users.catalog_service.notify_changed.assert_awaited_once()
