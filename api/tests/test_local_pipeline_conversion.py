from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration, compile_ai_model_configuration_v2
from api.services.configuration.ai_model_configuration import convert_legacy_ai_model_configuration_to_v2
from api.services.configuration.registry import (
    OpenAILLMService, SpeachesSTTConfiguration, SpeachesTTSConfiguration,
    KodewavesEmbeddingsConfiguration,
)


def test_resolved_local_pipeline_keeps_selected_models_when_managed_embeddings_are_present():
    config = EffectiveAIModelConfiguration(
        llm=OpenAILLMService(model="qwen2.5:1.5b", api_key="local-cpu-token", base_url="http://ollama:11434/v1"),
        stt=SpeachesSTTConfiguration(model="Systran/faster-whisper-base", language="hi", api_key="local-cpu-token"),
        tts=SpeachesTTSConfiguration(model="speaches-ai/Kokoro-82M-v1.0-ONNX", voice="hf_alpha", api_key="local-cpu-token"),
        embeddings=KodewavesEmbeddingsConfiguration(api_key="sovereign-managed"),
    )
    saved = convert_legacy_ai_model_configuration_to_v2(config)
    assert saved.kodewaves.llm_model == "qwen2.5:1.5b"
    assert saved.kodewaves.stt_model == "Systran/faster-whisper-base"
    assert saved.kodewaves.tts_model == "speaches-ai/Kokoro-82M-v1.0-ONNX"
    assert saved.kodewaves.tts_engine_type == "local_cpu"
    restored = compile_ai_model_configuration_v2(saved)
    assert restored.llm.model == config.llm.model
    assert restored.stt.model == config.stt.model
    assert restored.tts.model == config.tts.model
    assert restored.tts.voice == "hf_alpha"
    assert restored.stt.language == "hi"
