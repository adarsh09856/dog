from api.services.configuration.local_defaults import DEFAULT_LOCAL_LLM_MODEL
from api.services.configuration.registry import SPEACHES_LLM_MODELS, SPEACHES_TTS_MODELS


def test_local_defaults_and_catalog_exclude_removed_models():
    assert DEFAULT_LOCAL_LLM_MODEL == "qwen3.5:2b"
    assert "qwen3:1.7b" not in SPEACHES_LLM_MODELS
    assert "piper" not in SPEACHES_TTS_MODELS
    assert "speaches-ai/Kokoro-82M-v1.0-ONNX" not in SPEACHES_TTS_MODELS
    assert SPEACHES_TTS_MODELS == ["indus-pocket-tts"]


def test_indus_default_is_cpu_local_and_old_compose_endpoint_is_removed():
    from api.services.configuration.registry import SpeachesTTSConfiguration

    config = SpeachesTTSConfiguration()
    assert config.model == "indus-pocket-tts"
    assert config.voice == "Inaya"
    assert config.base_url == "http://indus-tts:8000/v1/audio/speech"
