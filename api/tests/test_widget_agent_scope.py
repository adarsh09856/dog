from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from api.routes import widgets


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['create','update'])
@pytest.mark.parametrize('field', ['workflow_id','agent_id'])
async def test_widget_cannot_reference_an_agent_in_another_workspace(monkeypatch,action,field):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(widgets.db_client,'get_workflow',lookup)
    write = Mock(side_effect=AssertionError('Must not open a write transaction'))
    monkeypatch.setattr(widgets.widget_db,'save_widget',write)
    request = widgets.WidgetCreateRequest(**{field:99},name='Synthetic widget')
    user = SimpleNamespace(selected_organization_id=7)
    with pytest.raises(HTTPException) as error:
        if action=='create': await widgets.create_widget(request,user=user)
        else: await widgets.update_widget('synthetic',request,user=user)
    assert error.value.status_code == 404
    lookup.assert_awaited_once_with(99,organization_id=7)
    write.assert_not_called()
