import base64
import io
import wave
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from api.services.catalog import speech_diagnostics as diagnostics
from api.routes.admin import settings


def wav_bytes(frames=1600):
    out = io.BytesIO()
    with wave.open(out, 'wb') as clip:
        clip.setnchannels(1); clip.setsampwidth(2); clip.setframerate(16000)
        clip.writeframes(bytes(frames * 2))
    return out.getvalue()


@pytest.mark.parametrize('audio', [b'not a wav', b'', b'RIFFtruncated'])
def test_invalid_audio_is_rejected(audio):
    with pytest.raises(ValueError): diagnostics.decode_test_audio(base64.b64encode(audio).decode())


def test_pcm_audio_round_trips_without_changing_samples():
    audio = wav_bytes()
    assert diagnostics.decode_test_audio(base64.b64encode(audio).decode()) == audio


def test_local_whisper_management_routes_are_removed():
    paths = {route.path for route in settings.router.routes}
    assert not any("/whisper/" in path for path in paths)
    assert "/settings/indic-stt/test" in paths


@pytest.mark.asyncio
async def test_auto_detection_omits_forced_language_and_silence_is_not_a_pass(monkeypatch):
    requests = []
    class Response:
        status=200
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
        async def json(self): return {'text': ''}
    class Session(Response):
        def post(self,url,**kwargs): requests.append((url,kwargs)); return Response()
    monkeypatch.setattr(diagnostics.aiohttp, 'ClientSession', lambda **kwargs: Session())
    result = await diagnostics.transcribe_test_audio('http://whisper/v1', wav_bytes(), 'selected-model', 'auto')
    assert result['success'] is False
    assert 'No speech' in result['error']
    fields = requests[0][1]['data']._fields
    names = [field[0]['name'] for field in fields]
    assert names == ['file', 'model']
    assert fields[1][2] == 'selected-model'
