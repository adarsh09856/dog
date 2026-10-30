from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.db import db_client
from api.db import campaign_client as campaign_client_module
from api.db.models import CampaignModel


class _Session:
    def __init__(self, parent):
        self.parent = parent
        self.added = []
        self.committed = False

    def add(self, item):
        self.added.append(item)

    def add_all(self, items):
        self.added.extend(items)

    async def flush(self):
        self.added[-1].id = 101

    async def execute(self, _statement):
        return SimpleNamespace(scalar_one=lambda: self.parent)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    async def refresh(self, _item):
        return None


class _SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_redial_rejects_at_signed_campaign_cap_before_writing_child(monkeypatch):
    parent = SimpleNamespace(
        id=7,
        orchestrator_metadata={},
        workflow_id=9,
        source_type="csv",
        source_id="contacts.csv",
        telephony_configuration_id=None,
        created_by=3,
        organization_id=5,
        retry_config=None,
        rate_limit_per_second=1,
    )
    session = _Session(parent)
    monkeypatch.setattr(db_client, "async_session", lambda: _SessionContext(session))
    enforce_limit = AsyncMock(side_effect=HTTPException(403, "Installation max_campaigns limit reached"))
    monkeypatch.setattr(campaign_client_module, "enforce_client_creation_limit", enforce_limit)

    with pytest.raises(HTTPException, match="max_campaigns") as error:
        await db_client.create_redial_campaign(parent, "redial", None, [])

    assert error.value.status_code == 403
    enforce_limit.assert_awaited_once_with(
        session,
        limit_name="max_campaigns",
        model=CampaignModel,
    )
    assert session.added == []
    assert session.committed is False
    assert parent.orchestrator_metadata == {}
