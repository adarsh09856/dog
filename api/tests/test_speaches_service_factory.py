from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.service_factory import create_stt_service
from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService
from pipecat.services.speaches.stt import SpeachesSTTSettings
from pipecat.transcriptions.language import Language


def test_local_whisper_stt_is_rejected_in_speaches_factory():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.SPEACHES.value,
            base_url="http://localhost:9100/v1",
            api_key=None,
            model="Systran/faster-whisper-small",
            language="tr",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with pytest.raises(ValueError, match="Whisper STT has been removed"):
        create_stt_service(user_config, audio_config)


def test_multilingual_whisper_stt_is_rejected_in_speaches_factory():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.SPEACHES.value,
            base_url="http://localhost:9100/v1",
            api_key=None,
            model="Systran/faster-whisper-small",
            language="multi",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with pytest.raises(ValueError, match="Whisper STT has been removed"):
        create_stt_service(user_config, audio_config, keyterms=["Asha", "booking"])


def test_local_default_uses_indicconformer_with_selected_language():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.KODEWAVES.value,
            api_key="sovereign-local-cpu",
            model=None,
            language="hi",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with patch("api.services.pipecat.service_factory.SpeachesSTTService") as mock_service:
        create_stt_service(user_config, audio_config)

    settings = mock_service.call_args.kwargs["settings"]
    assert settings.model == "indicconformer-ctc-int8"
    assert settings.language == "hi"
    assert mock_service.call_args.kwargs["base_url"] == "http://indic-stt:8000/v1"


def test_resolved_local_whisper_model_is_rejected():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.SPEACHES.value,
            base_url="http://localhost:9100/v1",
            api_key="local-cpu-token",
            model="Systran/faster-whisper-small",
            language="hi",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with pytest.raises(ValueError, match="Whisper STT has been removed"):
        create_stt_service(user_config, audio_config)


def test_local_indic_recognizer_uses_the_selected_language():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.SPEACHES.value,
            base_url="http://localhost:9100/v1",
            api_key="local-cpu-token",
            model="indicconformer-ctc-int8",
            language="hi",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with patch("api.services.pipecat.service_factory.SpeachesSTTService") as mock_service:
        create_stt_service(user_config, audio_config)
    settings = mock_service.call_args.kwargs["settings"]
    assert settings.model == "indicconformer-ctc-int8"
    assert settings.language == Language.HI


def test_managed_local_indic_recognizer_uses_resolved_endpoint_and_language():
    user_config = SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.KODEWAVES.value,
            base_url="http://indic-stt:8000/v1",
            api_key="local-cpu-token",
            model="indicconformer-ctc-int8",
            language="ta-IN",
        )
    )
    audio_config = SimpleNamespace(transport_in_sample_rate=16000)

    with patch("api.services.pipecat.service_factory.SpeachesSTTService") as mock_service:
        create_stt_service(user_config, audio_config)

    assert mock_service.call_args.kwargs["base_url"] == "http://indic-stt:8000/v1"
    settings = mock_service.call_args.kwargs["settings"]
    assert settings.model == "indicconformer-ctc-int8"
    assert settings.language == "ta"


def test_bounded_speaches_stt_client_does_not_retry_a_stalled_request():
    service = BoundedSpeachesSTTService(
        api_key="test",
        base_url="http://localhost:9100/v1",
        settings=SpeachesSTTSettings(model="Systran/faster-whisper-small"),
    )
    try:
        assert service._client.max_retries == 0
        assert service._client.timeout.read == 45.0
    finally:
        import asyncio

        asyncio.run(service._client.close())
