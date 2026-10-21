"""No-network regressions for exact platform selections and mixed sources."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration import kodewaves_resolver as resolver


@pytest.fixture
def dependencies(monkeypatch):
    from api.services.catalog import local_inventory

    # These resolver tests use Docker endpoint strings and mocked providers;
    # do not perform host DNS lookups for their container names on Windows.
    monkeypatch.setattr(resolver, "normalize_local_ai_endpoint", lambda url: url)
    monkeypatch.setattr(local_inventory, "normalize_local_ai_endpoint", lambda url: url)
    monkeypatch.setattr(resolver.db_client, "get_organization_by_id", AsyncMock(return_value=NS(status="active")))
    settings = {"byok_policy": {"allow_user_byok": True}, "local_ai": {"enable_local_ai_engine": True}}
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_setting", AsyncMock(side_effect=lambda key: settings.get(key)))
    wallet = NS(credit_balance_minutes=20, bonus_minutes=0)
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_or_create_wallet", AsyncMock(return_value=wallet))
    keys = AsyncMock(return_value=None)
    monkeypatch.setattr(resolver.master_credential_service, "get_master_credential", keys)
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_master_credentials", AsyncMock(return_value=[]))
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_models", AsyncMock(return_value=[]))
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=None))
    return keys, wallet


def mixed_config():
    return EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sovereign-managed"},
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-tiny", "api_key": "local-cpu-token"},
        "tts": {"provider": "openai", "model": "tts-1-hd", "voice": "nova", "api_key": "synthetic-byok"},
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("tts", [None, {
    "provider": "kodewaves", "model": "default", "voice": "default",
    "api_key": "sovereign-managed",
}, {"provider": "speaches", "model": "default", "voice": "default", "api_key": "local-cpu-token"}])
async def test_missing_tts_selection_does_not_silently_choose_indus(dependencies, tts):
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "synthetic-byok"},
        "stt": {"provider": "deepgram", "model": "nova-3", "api_key": "synthetic-byok"},
        "tts": tts,
    })
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert error.value.status_code == 400
    assert "Select an installed self-hosted TTS model" in error.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("model,voice", [("indus-pocket-tts", "Inaya"), ("indic-parler-tts", "Divya")])
async def test_explicit_installed_tts_selection_is_preserved(dependencies, monkeypatch, model, voice):
    from api.services.catalog import local_inventory
    monkeypatch.setattr(local_inventory, "get_local_tts_models", AsyncMock(return_value={
        model: {"voices": [{"id": voice, "languages": ["hi-IN", "en-IN"]}]},
    }))
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "synthetic-byok"},
        "stt": {"provider": "deepgram", "model": "nova-3", "api_key": "synthetic-byok"},
        "tts": {"provider": "speaches", "model": model, "voice": voice, "language": "hi"},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert result.tts.model == model
    assert result.tts.voice == voice


@pytest.mark.asyncio
async def test_explicit_cloud_cannot_fall_back_to_local(dependencies):
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(mixed_config(), 1)
    assert error.value.status_code == 400
    assert "LLM provider" in error.value.detail


@pytest.mark.asyncio
async def test_mixed_sources_preserve_voice_and_enforce_master_balance(dependencies, monkeypatch):
    keys, wallet = dependencies
    keys.return_value = {"api_key": "synthetic-master"}
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        NS(layer="llm", model_identifier="gpt-4o-mini", provider="openai", status="PASS")
    ]))
    result = await resolver.apply_kodewaves_sovereign_resolution(mixed_config(), 1, enforce_balance=True)
    assert [result.resolution_info[layer]["source"] for layer in ("llm", "stt", "tts")] == ["master_key", "local", "user_key"]
    assert result.tts.voice == "nova"
    assert result.tts.model == "tts-1-hd"
    wallet.credit_balance_minutes = 0
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(mixed_config(), 1, enforce_balance=True)
    assert error.value.status_code == 402


@pytest.mark.parametrize("provider,model,voice", [
    ("openai", "tts-1-hd", "nova"),
    ("elevenlabs", "eleven_multilingual_v2", "custom-voice"),
    ("sarvam", "bulbul:v3", "meera"),
])
def test_master_tts_preserves_selected_model(provider, model, voice):
    result = resolver._build_master_tts(provider, model, "synthetic", voice)
    assert result.model == model
    assert result.voice == voice


@pytest.mark.asyncio
async def test_disabled_catalog_choice_is_not_replaced(dependencies):
    effective = EffectiveAIModelConfiguration.model_validate({"llm": {
        "provider": "kodewaves", "model": "disabled-model", "api_key": "sovereign-managed",
    }})
    with pytest.raises(HTTPException) as error:
        await resolver._resolve_master_llm(effective)
    assert "disabled-model" in error.value.detail


@pytest.mark.asyncio
async def test_explicit_provider_cannot_bypass_disabled_catalog(dependencies):
    keys, _ = dependencies
    keys.return_value = {"api_key": "synthetic-master"}
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(mixed_config(), 1)
    assert error.value.status_code == 400
    assert "disabled or unavailable" in error.value.detail


@pytest.mark.asyncio
async def test_disabled_byok_is_rejected_without_using_master_key(dependencies, monkeypatch):
    keys, _ = dependencies
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_setting", AsyncMock(return_value={"allow_user_byok": False}))
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(mixed_config(), 1)
    assert error.value.status_code == 403
    keys.assert_not_awaited()


@pytest.mark.asyncio
async def test_org_local_denial_overrides_public_access(dependencies, monkeypatch):
    config = mixed_config()
    config.llm.api_key = "sovereign-local-cpu"
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_org_ai_policy", AsyncMock(return_value=NS(local_allowed=False, s2s_allowed=True)))
    with pytest.raises(HTTPException) as error:
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_local_choices_preserve_speed_voice_and_auto_recognition(dependencies):
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen2.5:1.5b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-base", "language": "multi"},
        "tts": {"provider": "speaches", "model": "piper", "voice": "en_US-lessac-medium", "speed": 1.25},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert result.stt.language == "multi"
    assert result.tts.speed == 1.25
    assert result.tts.voice == "en_US-lessac-medium"
    assert result.tts.language == "en"
    assert result.resolution_info["overall_source"] == "local"


@pytest.mark.asyncio
async def test_piper_voice_limits_auto_tts_language_and_rejects_mismatch(dependencies):
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3.5:2b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-small", "language": "multi"},
        "tts": {"provider": "speaches", "model": "piper", "voice": "hi_IN-pratham-medium", "language": "multi"},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert result.stt.language == "multi"
    assert result.tts.language == "hi"

    config.tts.language = "ta"
    with pytest.raises(HTTPException, match="does not match the TTS language"):
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)


@pytest.mark.asyncio
async def test_indic_stt_requires_explicit_language_without_falling_back_to_whisper(dependencies, monkeypatch):
    from api.services.catalog import local_inventory

    monkeypatch.setattr(local_inventory, "get_local_stt_models", AsyncMock(return_value={
        "indicconformer-ctc-int8": {
            "task": "automatic-speech-recognition",
            "languages": ["ta-IN", "bn-IN"],
        },
    }))
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3.5:2b", "api_key": "sovereign-local-cpu"},
        # Legacy saved local Whisper agents are migrated to the explicitly
        # selected Indian recognizer during resolution.
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-small", "language": "ta"},
        "tts": {"provider": "speaches", "model": "piper", "voice": "te_IN-maya-medium", "language": "te"},
    })
    resolved = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert resolved.stt.model == "indicconformer-ctc-int8"
    assert resolved.stt.base_url == "http://indic-stt:8000/v1"
    assert resolved.stt.language == "ta"
    assert resolved.resolution_info["stt"]["provider"] == "indicconformer"

    config.stt.language = "multi"
    with pytest.raises(HTTPException, match="automatic language detection is not available"):
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)

    config.stt.language = "bn"
    config.stt.model = "indicconformer-ctc-int8"
    resolved_bengali = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert resolved_bengali.stt.model == "indicconformer-ctc-int8"
    assert resolved_bengali.stt.language == "bn"


@pytest.mark.asyncio
async def test_local_default_does_not_silently_fall_back_to_whisper(dependencies):
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3.5:2b", "api_key": "sovereign-local-cpu"},
        "tts": {"provider": "speaches", "model": "indus-pocket-tts", "voice": "Inaya", "language": "hi"},
    })
    with pytest.raises(HTTPException, match="Local Whisper has been removed"):
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)


@pytest.mark.asyncio
async def test_selected_kokoro_model_and_voice_survive_local_resolution(dependencies, monkeypatch):
    import aiohttp

    class Response:
        status = 200
        def raise_for_status(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def json(self): return {"data": [{
            "id": "speaches-ai/Kokoro-82M-v1.0-ONNX",
            "task": "text-to-speech",
            "voices": ["hf_alpha"],
        }]}

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def get(self, url):
            assert url.endswith("/v1/models")
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen2.5:1.5b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-base", "language": "multi"},
        "tts": {"provider": "speaches", "model": "speaches-ai/Kokoro-82M-v1.0-ONNX", "voice": "hf_alpha"},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert result.tts.model == "speaches-ai/Kokoro-82M-v1.0-ONNX"
    assert result.tts.voice == "hf_alpha"
    assert result.tts.base_url.endswith("/v1")


@pytest.mark.asyncio
async def test_indus_runtime_uses_same_admin_engine_as_voice_selection(dependencies, monkeypatch):
    from api.services.catalog import local_inventory

    settings = {"local_ai": {
        "enable_local_ai_engine": True,
        "indus_tts_endpoint": "http://selected-engine:9001/v1",
        "whisper_endpoint": "http://different-stt-engine:9002/v1",
    }}
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_setting", AsyncMock(side_effect=lambda key: settings.get(key)))
    inventory = AsyncMock(return_value={"indus-pocket-tts": {
        "voices": [{"id": "Inaya", "languages": ["hi-IN", "en-IN"]}],
    }})
    monkeypatch.setattr(local_inventory, "get_local_tts_models", inventory)
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3.5:2b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "model": "Systran/faster-whisper-small", "language": "multi"},
        "tts": {"provider": "speaches", "model": "indus-pocket-tts", "voice": "Inaya", "language": "hi"},
    })
    resolved = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert resolved.tts.base_url == "http://selected-engine:9001/v1"
    assert resolved.tts.model == "indus-pocket-tts"
    assert resolved.tts.voice == "Inaya"
    inventory.assert_awaited_once_with(resolved.tts.base_url)

    config.tts.language = "ta"
    with pytest.raises(HTTPException, match="has no voice"):
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)


@pytest.mark.asyncio
async def test_vits_preferred_voice_is_independent_of_stt_language(dependencies, monkeypatch):
    from api.services.catalog import local_inventory

    monkeypatch.setattr(local_inventory, "get_local_stt_models", AsyncMock(return_value={
        "indicconformer-ctc-int8": {"languages": ["hi-IN"]},
    }))
    monkeypatch.setattr(local_inventory, "get_local_tts_models", AsyncMock(return_value={
        "indic-vits-rasa-13": {
            "voices": [{"id": "KAN_M", "languages": ["kn-IN"]}],
        },
    }))
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3.5:2b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "model": "indicconformer-ctc-int8", "language": "hi"},
        "tts": {"provider": "speaches", "model": "indic-vits-rasa-13", "voice": "KAN_M", "language": "hi"},
    })
    resolved = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert resolved.stt.language == "hi"
    assert resolved.tts.voice == "KAN_M"

    config.tts.voice = "missing"
    with pytest.raises(HTTPException, match="Select a voice supported"):
        await resolver.apply_kodewaves_sovereign_resolution(config, 1)


@pytest.mark.asyncio
async def test_realtime_does_not_require_unused_stt_or_tts(dependencies, monkeypatch):
    monkeypatch.setattr(resolver.kodewaves_db_client, "get_setting", AsyncMock(return_value=None))
    config = EffectiveAIModelConfiguration.model_validate({
        "is_realtime": True,
        "llm": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "synthetic-byok"},
        "realtime": {"provider": "openai_realtime", "model": "gpt-realtime-2", "api_key": "synthetic-byok"},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert result.stt is None and result.tts is None
    assert result.realtime.model == "gpt-realtime-2"
    assert result.resolution_info["realtime"]["source"] == "user_key"


@pytest.mark.asyncio
async def test_workflow_configuration_resolves_master_credentials_once(dependencies, monkeypatch):
    from api.schemas.ai_model_configuration import OrganizationAIModelConfigurationV2
    from api.services.configuration import ai_model_configuration as configuration_service

    keys, _ = dependencies
    keys.return_value = {"api_key": "synthetic-master"}
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        NS(layer="llm", model_identifier="gpt-4o-mini", provider="openai", status="PASS", recommended=True),
    ]))
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_master_credentials", AsyncMock(return_value=[
        NS(provider="openai", is_enabled=True, credentials_encrypted="synthetic-encrypted"),
    ]))
    configuration = OrganizationAIModelConfigurationV2.model_validate({
        "mode": "kodewaves", "kodewaves": {
            "llm_model": "gpt-4o-mini", "llm_engine_type": "cloud",
            "stt_model": "Systran/faster-whisper-base", "stt_engine_type": "local_cpu",
            "tts_model": "piper", "tts_engine_type": "local_cpu",
            "voice": "hi_IN-pratham-medium", "speed": 1.2, "language": "multi",
        },
    })
    monkeypatch.setattr(configuration_service, "get_organization_ai_model_configuration_v2", AsyncMock(return_value=configuration))
    result = await configuration_service.get_effective_ai_model_configuration_for_workflow(
        organization_id=1, workflow_configurations={},
    )
    keys.assert_awaited_once_with("openai")
    assert result.resolution_info["llm"]["source"] == "master_key"
    assert result.resolution_info["overall_source"] == "master_key"
    assert result.tts.voice == "hi_IN-pratham-medium" and result.tts.speed == 1.2
    assert result.stt.language == "multi"


def test_cloud_auto_detect_is_not_normalized_to_english():
    from api.services.configuration.language_normalizer import normalize_stt_language
    assert normalize_stt_language("sarvam", "multi") == "unknown"
    assert normalize_stt_language("deepgram", "auto") == "multi"
    assert normalize_stt_language("gemini", "multi") == "auto"
    assert resolver._build_master_stt("sarvam", "saaras:v3", "synthetic", "multi").language == "unknown"


@pytest.mark.asyncio
async def test_selected_language_and_speed_reach_cloud_tts(dependencies, monkeypatch):
    keys, _ = dependencies
    keys.return_value = {"api_key": "synthetic-master"}
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        NS(layer="tts", model_identifier="bulbul:v2", provider="sarvam", status="PASS", recommended=True),
    ]))
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_master_credentials", AsyncMock(return_value=[
        NS(provider="sarvam", is_enabled=True, credentials_encrypted="synthetic-encrypted"),
    ]))
    config = EffectiveAIModelConfiguration.model_validate({
        "stt": {"provider": "speaches", "language": "en"},
        "tts": {"provider": "kodewaves", "model": "bulbul:v2", "voice": "anushka", "speed": 1.2},
    })
    await resolver._resolve_master_tts(config)
    assert config.tts.voice == "anushka" and config.tts.model == "bulbul:v2"
    assert config.tts.language == "en-IN" and config.tts.speed == 1.2


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["catalog", "byok", "explicit_master"])
async def test_google_catalog_gemini_tts_uses_ai_studio_service(dependencies, monkeypatch, source):
    from api.services.configuration.registry import GoogleGeminiTTSConfiguration
    keys, _ = dependencies
    keys.return_value = {"api_key": "synthetic-master"}
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_models", AsyncMock(return_value=[
        NS(layer="tts", model_identifier="gemini-3.8-flash-tts", provider="google", status="UNTESTED", recommended=True),
    ]))
    monkeypatch.setattr(resolver.kodewaves_db_client, "list_master_credentials", AsyncMock(return_value=[
        NS(provider="google", is_enabled=True, credentials_encrypted="synthetic"),
    ]))
    config = EffectiveAIModelConfiguration.model_validate({
        "llm": {"provider": "openai", "model": "qwen3:1.7b", "api_key": "sovereign-local-cpu"},
        "stt": {"provider": "speaches", "language": "multi"},
        "tts": {"provider": "kodewaves" if source == "catalog" else "google",
                "model": "gemini-3.8-flash-tts", "voice": "Puck",
                "api_key": "synthetic-byok" if source == "byok" else "sovereign-managed"},
    })
    result = await resolver.apply_kodewaves_sovereign_resolution(config, 1)
    assert isinstance(result.tts, GoogleGeminiTTSConfiguration)
    assert result.tts.voice == "Puck"
    assert result.tts.model == "gemini-3.8-flash-tts"
    assert result.resolution_info["tts"]["provider"] == "gemini"
    assert result.resolution_info["tts"]["source"] == ("user_key" if source == "byok" else "master_key")
