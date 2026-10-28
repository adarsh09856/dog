from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from api.routes import workflow


@pytest.mark.asyncio
@pytest.mark.parametrize("template_language", ["hi", "as", "brx", "doi", "gu", "ks", "kok", "mai", "mni", "sa", "sat", "sd"])
async def test_indian_template_rejects_mismatched_known_voice_before_creation(template_language):
    user = SimpleNamespace(id=1, selected_organization_id=11)
    selected = SimpleNamespace(tts=SimpleNamespace(provider='speaches', voice='af_heart', language=None), stt=SimpleNamespace(language='en'))
    request = workflow.CreateWorkflowRequest(name='Indian language booking', workflow_definition={
        'template_id': 'appointment-booking', 'template_language': template_language, 'nodes': [], 'edges': []})
    with patch('api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow', AsyncMock(return_value=selected)):
        with pytest.raises(HTTPException) as error:
            await workflow.create_workflow(request, user)
    assert error.value.status_code == 400
    assert 'matching voice' in error.value.detail


@pytest.mark.asyncio
async def test_booking_template_passes_through_real_calendar_tool_attachment():
    user = SimpleNamespace(id=1, selected_organization_id=11)
    request = workflow.CreateWorkflowRequest(name='Booking', workflow_definition={
        'template_id': 'appointment-booking', 'nodes': [], 'edges': []})
    attach = AsyncMock(side_effect=HTTPException(status_code=418, detail='attachment reached'))
    with patch('api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow', AsyncMock(return_value=None)), patch.object(workflow, '_attach_generated_booking_tool', attach):
        with pytest.raises(HTTPException) as error:
            await workflow.create_workflow(request, user)
    assert error.value.status_code == 418
    attach.assert_awaited_once_with(request.workflow_definition, user, 'appointment booking')


@pytest.mark.asyncio
async def test_template_rejects_unsupported_language_code():
    user = SimpleNamespace(id=1, selected_organization_id=11)
    request = workflow.CreateWorkflowRequest(name='Unsupported language', workflow_definition={
        'template_id': 'appointment-booking', 'template_language': 'xx-test', 'nodes': [], 'edges': []})
    with pytest.raises(HTTPException) as error:
        await workflow.create_workflow(request, user)
    assert error.value.status_code == 400
    assert 'supported template language' in error.value.detail
