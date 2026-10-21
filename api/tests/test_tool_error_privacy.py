from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from api.services.workflow.tools.custom_tool import execute_http_tool


@pytest.mark.asyncio
@pytest.mark.parametrize('diagnostics', [False, True])
async def test_upstream_error_body_is_not_shared_with_live_caller(diagnostics):
    tool = SimpleNamespace(name='Lookup', tool_uuid='test', definition={
        'type': 'http_api', 'config': {'method': 'GET', 'url': 'https://example.com/lookup'},
    })
    response = Mock(status_code=500, text='private database password=secret')
    response.json.return_value = {'debug': 'private database password=secret'}
    client = AsyncMock()
    client.request.return_value = response
    with patch('api.services.workflow.tools.custom_tool.httpx.AsyncClient') as factory:
        factory.return_value.__aenter__.return_value = client
        result = await execute_http_tool(tool, {}, include_request_headers=diagnostics)
    assert result['status'] == 'error'
    assert result['status_code'] == 500
    assert ('private database' in str(result)) is diagnostics
