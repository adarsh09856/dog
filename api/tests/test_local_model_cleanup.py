from api.services.configuration.local_defaults import DEFAULT_LOCAL_LLM_MODEL
from api.services.configuration.registry import SPEACHES_LLM_MODELS, SPEACHES_TTS_MODELS


def test_local_defaults_and_catalog_exclude_removed_models():
    assert DEFAULT_LOCAL_LLM_MODEL == "qwen3.5:2b"
    assert "qwen3:1.7b" not in SPEACHES_LLM_MODELS
    assert "piper" not in SPEACHES_TTS_MODELS
    assert "speaches-ai/Kokoro-82M-v1.0-ONNX" not in SPEACHES_TTS_MODELS
    assert SPEACHES_TTS_MODELS == ["indic-vits-rasa-13"]


def test_regional_vits_is_the_local_tts_default():
    from api.services.configuration.registry import SpeachesTTSConfiguration

    config = SpeachesTTSConfiguration()
    assert config.model == "indic-vits-rasa-13"
    assert config.voice == "KAN_F"
    assert config.base_url == "http://indic-vits-tts:8000/v1/audio/speech"
