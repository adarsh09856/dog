from api.services.pipecat.service_factory import create_llm_service_from_provider
import asyncio
import pytest


def test_local_qwen_models_have_concise_voice_completion_limit():
    service = create_llm_service_from_provider(
        "openai",
        "qwen2.5:1.5b",
        "test-key",
        base_url="http://localhost:11434/v1",
    )
    assert service._settings.max_tokens == 192


def test_cloud_model_does_not_receive_local_qwen_limit():
    service = create_llm_service_from_provider("openai", "gpt-4.1", "test-key")
    assert service._settings.max_tokens != 192


def test_qwen3_voice_calls_disable_thinking_in_provider_request():
    service = create_llm_service_from_provider('openai', 'qwen3:1.7b', 'local-cpu-token')
    params = service.build_chat_completion_params({'messages': [{'role': 'user', 'content': 'Hello'}]})
    assert params['reasoning_effort'] == 'none'
    assert params['max_tokens'] == 192
    assert params['temperature'] == 0.1


@pytest.mark.parametrize('model', ['qwen3:1.7b', 'qwen3.5:2b-q4_K_M'])
def test_local_qwen3_prompt_disables_thinking_for_fast_speech(model):
    service = create_llm_service_from_provider(
        'ollama', model, 'sovereign-local-cpu', base_url='http://localhost:11434/v1',
    )
    params = service.build_chat_completion_params({
        'messages': [
            {'role': 'system', 'content': 'Answer the caller naturally.'},
            {'role': 'user', 'content': 'नमस्ते'},
        ],
    })
    assert params['messages'][0]['content'].endswith('/no_think') == model.startswith('qwen3:')
    assert params['extra_body']['think'] is False


def test_local_qwen3_adds_thinking_control_when_no_system_prompt_exists():
    service = create_llm_service_from_provider(
        'ollama', 'qwen3:1.7b', 'sovereign-local-cpu', base_url='http://localhost:11434/v1',
    )
    params = service.build_chat_completion_params({
        'messages': [{'role': 'user', 'content': 'Hello'}],
    })
    assert params['messages'][0] == {'role': 'system', 'content': '/no_think'}


@pytest.mark.parametrize('provider', ['openai', 'ollama', 'speaches', 'kodewaves'])
@pytest.mark.parametrize('model', ['qwen3:1.7b', 'qwen3.5:2b-q4_K_M'])
def test_qwen_voice_budget_is_identical_through_local_provider_aliases(provider, model):
    service = create_llm_service_from_provider(
        provider, model, 'sovereign-local-cpu',
        base_url='http://localhost:11434/v1', temperature=0.4,
    )
    try:
        params = service.build_chat_completion_params({'messages': [{'role': 'user', 'content': 'Hello'}]})
        assert params['reasoning_effort'] == 'none'
        assert params['max_tokens'] == 192
        assert params['temperature'] == 0.4
        assert service._client.max_retries == 0
        assert service._client.timeout.read == 45.0
        assert params['messages'][0]['content'].endswith('/no_think') == model.startswith('qwen3:')
    finally:
        asyncio.run(service._client.close())


def test_qwen35_uses_api_reasoning_control_without_inserting_prompt_messages():
    service = create_llm_service_from_provider(
        'ollama', 'qwen3.5:2b', 'sovereign-local-cpu', base_url='http://localhost:11434/v1',
    )
    messages = [{'role': 'user', 'content': 'Hello'}]
    try:
        params = service.build_chat_completion_params({'messages': messages})
        assert params['messages'] == messages
        assert params['extra_body']['think'] is False
        assert params['reasoning_effort'] == 'none'
    finally:
        asyncio.run(service._client.close())


@pytest.mark.parametrize("provider", ["ollama", "speaches", "kodewaves"])
def test_missing_local_model_uses_shared_bootstrap_selection(provider):
    from api.services.configuration.local_defaults import DEFAULT_LOCAL_LLM_MODEL
    from api.services.configuration.registry import SpeachesLLMConfiguration

    service = create_llm_service_from_provider(
        provider, None, "sovereign-local-cpu", base_url="http://localhost:11434/v1",
    )
    assert service._settings.model == DEFAULT_LOCAL_LLM_MODEL
    assert SpeachesLLMConfiguration().model == DEFAULT_LOCAL_LLM_MODEL
