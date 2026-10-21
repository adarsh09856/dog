from api.services.pipecat.tts_cache.models import SynthesisRequest


def test_local_speech_cache_preserves_selected_voice_and_spoken_text():
    request = SynthesisRequest.from_payload(
        organization_id=7, provider='speaches', adapter_version=1,
        endpoint='http://speech/v1', credential='local', sample_rate=24000,
        channels=1, payload={'input': 'नमस्ते hello', 'model': 'kokoro', 'voice': 'hf_alpha'},
    )
    assert request.text_preview == 'नमस्ते hello'
    assert request.voice_id == 'hf_alpha'
    assert request.model == 'kokoro'


def test_existing_provider_cache_metadata_keeps_its_payload_contract():
    request = SynthesisRequest.from_payload(
        organization_id=7, provider='minimax', adapter_version=1,
        endpoint='https://speech/v1', credential='test', sample_rate=24000,
        channels=1, payload={'text': 'Hello', 'model': 'speech', 'voice_setting': {'voice_id': 'selected'}},
    )
    assert request.text_preview == 'Hello'
    assert request.voice_id == 'selected'
