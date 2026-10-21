"""CRM transaction contract checks; no real database is contacted."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from api.db.kodewaves_client import kodewaves_db_client


@pytest.fixture
def session(monkeypatch):
    session = NS(execute=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(), add=Mock())
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(kodewaves_db_client, "get_session", lambda: context)
    return session


@pytest.mark.asyncio
async def test_foreign_stage_rejected_before_new_contact_is_added(session):
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with pytest.raises(LookupError, match="Stage not found"):
        await kodewaves_db_client.save_contact(7, {"phone": "synthetic", "stage_id": str(uuid4())})
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert session.execute.call_args.args[0].compile().params["organization_id_1"] == 7


@pytest.mark.asyncio
async def test_empty_values_clear_existing_contact_fields(session):
    contact = NS(custom_fields={"old": "value"}, tags=["old"], stage_id=uuid4())
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=contact))
    result = await kodewaves_db_client.save_contact(7, {
        "tags": [], "custom_fields": {}, "notes": "", "stage_id": None,
    }, str(uuid4()))
    assert result.tags == []
    assert result.custom_fields == {"notes": ""}
    assert result.stage_id is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeline_rejects_foreign_contact_without_reading_activities(session):
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
    with pytest.raises(LookupError, match="Contact not found"):
        await kodewaves_db_client.get_contact_timeline(7, uuid4())
    session.execute.assert_awaited_once()
    assert session.execute.call_args.args[0].compile().params["organization_id_1"] == 7
