import os
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from api.schemas.ai_model_configuration import (
    EffectiveAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
    KodewavesManagedAIModelConfiguration,
    compile_ai_model_configuration_v2,
)
from api.services.configuration.language_normalizer import (
    normalize_stt_language,
    normalize_tts_language,
    select_piper_voice_for_language,
)
from api.services.configuration.kodewaves_resolver import (
    apply_kodewaves_sovereign_resolution,
)
from api.services.pipecat.service_factory import (
    create_llm_service_from_provider,
    create_realtime_llm_service,
)


def test_deepgram_language_normalization():
    """Verify Deepgram language normalization converts regional BCP-47 to primary codes."""
    assert normalize_stt_language("deepgram", "hi-IN") == "hi"
    assert normalize_stt_language("deepgram", "en-US") == "en"
    assert normalize_stt_language("deepgram", "en-GB") == "en"
    assert normalize_stt_language("deepgram", "es-ES") == "es"
    assert normalize_stt_language("deepgram", "hi") == "hi"
    assert normalize_stt_language("deepgram", "multi") == "multi"
    assert normalize_stt_language("deepgram", None) == "en"


def test_sarvam_language_normalization():
    """Verify Sarvam language normalization ensures BCP-47 format with country tag."""
    assert normalize_stt_language("sarvam", "hi") == "hi-IN"
    assert normalize_stt_language("sarvam", "en") == "en-IN"
    assert normalize_stt_language("sarvam", "bn") == "bn-IN"
    assert normalize_stt_language("sarvam", "hi-IN") == "hi-IN"


def test_piper_voice_selection_by_language():
    """Verify Piper default voices are accurately selected based on language."""
    assert select_piper_voice_for_language("hi") == "hi_IN-priyamvada-medium"
    assert select_piper_voice_for_language("hi-IN") == "hi_IN-priyamvada-medium"
    assert select_piper_voice_for_language("en") == "en_US-lessac-medium"
    assert select_piper_voice_for_language("en-US") == "en_US-lessac-medium"


@pytest.mark.asyncio
async def test_resolver_byok_priority():
    """Verify BYOK key takes precedence over master credentials."""
    effective = EffectiveAIModelConfiguration.model_validate({
        "stt": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "hi-IN",
            "api_key": "user-byok-deepgram-key",
        },
        "llm": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "api_key": "user-byok-groq-key",
        },
        "tts": {
            "provider": "cartesia",
            "model": "sonic-3.5",
            "voice": "test-voice",
            "api_key": "user-byok-cartesia-key",
        },
    })

    with patch("api.services.credentials.master_credential_service.master_credential_service.get_master_credential", new_callable=AsyncMock) as mock_master:
        mock_master.return_value = "master-key-should-not-be-used"

        resolved = await apply_kodewaves_sovereign_resolution(effective, organization_id=1)

        assert resolved.stt.api_key == "user-byok-deepgram-key"
        assert resolved.llm.api_key == "user-byok-groq-key"
        assert resolved.tts.api_key == "user-byok-cartesia-key"

        # Check metadata source
        info = resolved.resolution_info
        assert info["stt"]["source"] == "user_key"
        assert info["llm"]["source"] == "user_key"
        assert info["tts"]["source"] == "user_key"
        assert info["stt"]["language"] == "hi"  # Normalized from hi-IN for Deepgram


@pytest.mark.asyncio
async def test_resolver_master_key_fallback():
    """Verify master credential is used when no user BYOK key is provided."""
    effective = EffectiveAIModelConfiguration.model_validate({
        "stt": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": "en-US",
            "api_key": None,
        },
        "llm": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": None,
        },
        "tts": {
            "provider": "elevenlabs",
            "model": "eleven_multilingual_v2",
            "voice": "21m00Tcm4TlvDq8ikWAM",
            "api_key": None,
        },
    })

    async def fake_master(provider):
        mapping = {
            "deepgram": {"api_key": "master-deepgram-key"},
            "openai": {"api_key": "master-openai-key"},
            "elevenlabs": {"api_key": "master-elevenlabs-key"},
        }
        return mapping.get(provider)

    with patch("api.services.credentials.master_credential_service.master_credential_service.get_master_credential", side_effect=fake_master):
        resolved = await apply_kodewaves_sovereign_resolution(effective, organization_id=2)

        assert resolved.stt.api_key == "master-deepgram-key"
        assert resolved.llm.api_key == "master-openai-key"
        assert resolved.tts.api_key == "master-elevenlabs-key"

        info = resolved.resolution_info
        assert info["stt"]["source"] == "master_key"
        assert info["llm"]["source"] == "master_key"
        assert info["tts"]["source"] == "master_key"


@pytest.mark.asyncio
async def test_resolver_zero_silent_fallback_error():
    """Verify that an explicit provider without any credentials raises HTTPException(400) immediately."""
    effective_stt_fail = EffectiveAIModelConfiguration.model_validate({
        "stt": {
            "provider": "deepgram",
            "model": "nova-3",
            "api_key": None,
        },
        "llm": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "api_key": "user-groq-key",
        },
        "tts": {
            "provider": "cartesia",
            "model": "sonic-3.5",
            "voice": "test-voice",
            "api_key": "user-cartesia-key",
        },
    })

    # Master credentials return None (either missing or disabled)
    with patch("api.services.credentials.master_credential_service.master_credential_service.get_master_credential", new_callable=AsyncMock) as mock_master:
        mock_master.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await apply_kodewaves_sovereign_resolution(effective_stt_fail, organization_id=3)

        assert exc_info.value.status_code == 400
        assert "deepgram" in exc_info.value.detail.lower()
        assert "no active master credentials" in exc_info.value.detail.lower() or "no valid api key" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_resolver_local_cpu_resolution():
    """Verify local CPU engine configurations resolve cleanly without sentinel tokens."""
    org_config = OrganizationAIModelConfigurationV2(
        mode="kodewaves",
        kodewaves=KodewavesManagedAIModelConfiguration(
            stt_engine_type="local_cpu",
            llm_engine_type="local_cpu",
            tts_engine_type="local_cpu",
            stt_model="Systran/faster-whisper-tiny",
            llm_model="qwen2.5:0.5b",
            tts_model="piper-medium",
            voice="hi_IN-priyamvada-medium",
        ),
    )
    effective = compile_ai_model_configuration_v2(org_config)

    async def fake_get_setting(key):
        if key == "local_ai":
            return {"enable_local_ai_engine": True, "local_ai_access_policy": "public"}
        return None

    with patch("api.db.kodewaves_client.kodewaves_db_client.get_setting", side_effect=fake_get_setting):
        resolved = await apply_kodewaves_sovereign_resolution(effective, organization_id=4)

        assert "8000" in (resolved.stt.base_url or "")
        assert "11434" in (resolved.llm.base_url or "")
        assert "5000" in (resolved.tts.base_url or "")

        info = resolved.resolution_info
        assert info["stt"]["source"] == "local"
        assert info["llm"]["source"] == "local"
        assert info["tts"]["source"] == "local"


def test_gemini_llm_api_key_without_service_account():
    """Verify Gemini LLM initializes directly with API key and does not require service account JSON."""
    service = create_llm_service_from_provider(
        provider="google",
        model="gemini-3.5-flash",
        api_key="AIzaSyDummyTestKeyForVerification",
    )
    assert service is not None
    # Verify settings model was preserved
    assert "gemini-3.5-flash" in service._settings.model


def test_ollama_llm_factory_initialization():
    """Verify Ollama LLM initializes directly with endpoint and model."""
    service = create_llm_service_from_provider(
        provider="ollama",
        model="qwen2.5:0.5b",
        api_key=None,
        base_url="http://ollama:11434/v1",
    )
    assert service is not None
    assert str(service._client.base_url).rstrip("/") == "http://ollama:11434/v1"
    assert service._settings.model == "qwen2.5:0.5b"
