from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
from pipecat.services.openai.base_llm import OpenAILLMSettings
import pytest

@pytest.mark.parametrize('model', ['qwen3.5:2b', 'gpt-4o-mini'])
def test_custom_assist_transition_is_not_removed_after_a_greeting(model):
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model=model))
    prompt = 'You are the reception agent.\n\nWorkflow step routing: Follow the configured route.\n- assist_caller: Transfer a product-support request to the technical-support node.'
    result = service.build_chat_completion_params({
        'messages': [{'role': 'system', 'content': prompt}, {'role': 'assistant', 'content': 'Hello. How can I help?'}, {'role': 'user', 'content': 'I need technical support for my device.'}],
        'tools': [{'type': 'function', 'function': {'name': 'assist_caller', 'description': 'Enter technical support', 'parameters': {'type': 'object', 'properties': {}}}}],
    })
    assert [t['function']['name'] for t in result.get('tools', [])] == ['assist_caller']
    assert any('assist_caller:' in m.get('content', '') for m in result['messages'])
    assert not any('Continue the conversation here' in m.get('content', '') for m in result['messages'])

@pytest.mark.parametrize('model', ['qwen3.5:2b', 'gpt-4o-mini'])
def test_opening_without_a_caller_cannot_run_transition_or_action_tools(model):
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model=model))
    result = service.build_chat_completion_params({
        'messages': [{'role': 'system', 'content': 'Greet briefly, then assist the caller.'}],
        'tools': [{'type': 'function', 'function': {'name': 'assist_caller', 'parameters': {'type': 'object'}}}],
        'tool_choice': 'required',
    })
    assert 'tools' not in result
    assert 'tool_choice' not in result


@pytest.mark.parametrize('model', ['qwen3.5:2b', 'gpt-4o-mini'])
def test_hidden_end_route_is_removed_without_hiding_custom_support_route(model):
    from copy import deepcopy

    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model=model))
    prompt = ('Support the caller.\n\nWorkflow step routing: Follow the matching route.\n'
              '- finish_call: End the call on farewell.\n'
              '- assist_caller: Enter technical support.\n\nKeep private data confidential.')
    context = {
        'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': 'I need technical support.'}],
        'tools': [{'type': 'function', 'function': {'name': name, 'parameters': {'type': 'object'}}}
                  for name in ['finish_call', 'assist_caller']],
    }
    original = deepcopy(context)
    result = service.build_chat_completion_params(context)
    system = result['messages'][0]['content']
    assert '- finish_call:' not in system
    assert '- assist_caller:' in system
    assert 'Keep private data confidential.' in system
    assert context == original
    context['messages'][-1]['content'] = 'Goodbye, end the call.'
    farewell = service.build_chat_completion_params(context)
    assert '- finish_call:' in farewell['messages'][0]['content']
    assert 'finish_call' in [tool['function']['name'] for tool in farewell['tools']]


def test_only_routing_section_is_filtered_and_empty_section_is_removed():
    service = BookingOpenAILLMService(api_key='test', settings=OpenAILLMSettings(model='qwen3.5:2b'))
    text = ('Documentation mentions finish_call.\n\n'
            'Workflow step routing: Follow the matching route.\n- finish_call: End on farewell.\n\n'
            'Answer in the caller language.')
    caller = 'Explain this text: - finish_call: example'
    result = service.build_chat_completion_params({
        'messages': [{'role': 'system', 'content': text}, {'role': 'user', 'content': caller}],
        'tools': [{'type': 'function', 'function': {'name': 'finish_call', 'parameters': {'type': 'object'}}}],
    })
    assert result['messages'][0]['content'] == 'Documentation mentions finish_call.\n\nAnswer in the caller language.'
    assert result['messages'][-1]['content'] == caller
    assert 'tools' not in result
