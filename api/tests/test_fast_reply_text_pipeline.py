import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from pipecat.services.openai.base_llm import OpenAILLMSettings

from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration import ai_model_configuration
from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
from api.services.workflow import pipecat_engine, text_chat_runner as runner


@pytest.mark.asyncio
async def test_language_switch_finishes_real_text_pipeline_without_qwen(monkeypatch):
    definition = NS(workflow_configurations={}, workflow_json={
        'nodes': [{'id': 'start', 'type': 'startCall', 'position': {'x': 0, 'y': 0},
                   'data': {'name': 'Start', 'prompt': 'Help the caller.',
                            'greeting_type': 'text', 'greeting': 'Hello.', 'is_start': True}}],
        'edges': [],
    })
    workflow = NS(id=1, organization_id=7, user=NS(provider_id='synthetic'), workflow_configurations={})
    run = NS(id=1, name='Language switch regression', workflow_id=1, definition=definition, workflow=workflow, initial_context={})
    monkeypatch.setattr(runner.db_client, 'get_workflow_run_with_context', AsyncMock(return_value=(run, None)))
    monkeypatch.setattr(runner.db_client, 'get_workflow', AsyncMock(return_value=workflow))
    monkeypatch.setattr(runner.db_client, 'update_workflow_run', AsyncMock())
    monkeypatch.setattr(runner.db_client, 'has_active_recordings', AsyncMock(return_value=False))
    monkeypatch.setattr(runner.db_client, 'get_organization_id_by_workflow_run_id', AsyncMock(return_value=7))
    config = EffectiveAIModelConfiguration.model_validate({
        'llm': {'provider': 'openai', 'model': 'qwen3.5:2b', 'api_key': 'synthetic'},
    })
    monkeypatch.setattr(ai_model_configuration, 'get_effective_ai_model_configuration_for_workflow', AsyncMock(return_value=config))
    service = BookingOpenAILLMService(api_key='synthetic', settings=OpenAILLMSettings(model='qwen3.5:2b'))
    service.get_chat_completions = AsyncMock(side_effect=AssertionError('A language setting must not invoke Qwen'))
    monkeypatch.setattr(runner, 'create_llm_service', lambda *a, **k: service)
    monkeypatch.setattr(pipecat_engine, 'compose_functions_for_node', AsyncMock(return_value=[]))
    monkeypatch.setattr(pipecat_engine, 'selected_voice_persona_instruction', AsyncMock(return_value=''))
    monkeypatch.setattr(pipecat_engine, 'get_disposition_mapping', AsyncMock(return_value={}))
    from pipecat.turns import user_turn_strategies
    from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
    monkeypatch.setattr(user_turn_strategies, 'default_user_turn_stop_strategies', lambda: [SpeechTimeoutUserTurnStopStrategy()])
    checkpoint = runner.default_text_chat_checkpoint()
    checkpoint['current_node_id'] = 'start'
    checkpoint['messages'] = [{'role': 'assistant', 'content': 'Hello.'}]
    try:
        # Match the production API lifespan, which warms Pipecat's deferred
        # sentence tokenizer before accepting the first text/voice turn.
        from pipecat.utils.prewarm import warm_deferred_imports
        await asyncio.to_thread(warm_deferred_imports)
        result = await asyncio.wait_for(runner.execute_text_chat_pending_turn(
            workflow_run_id=1, workflow_id=1, checkpoint=checkpoint,
            session_data={'turns': [{'id': 't1', 'status': 'pending',
                                     'user_message': {'text': 'Can you talk in English?'}}]},
        ), timeout=8)
        assert result.assistant_text == 'Yes, we can continue in English.'
        assert result.checkpoint['contact_conversation_state']['reply_language'] == 'English'
        service.get_chat_completions.assert_not_awaited()
    finally:
        await service._client.close()
