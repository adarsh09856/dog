from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService
from pipecat.services.speaches.stt import SpeachesSTTSettings


@pytest.mark.asyncio
async def test_explicit_choice_changes_only_call_decoder_when_installed():
    service = BoundedSpeachesSTTService(api_key='test', settings=SpeachesSTTSettings(
        model='indicconformer-ctc-int8', language='hi'))
    service._client.models.list = AsyncMock(return_value=SimpleNamespace(data=[
        SimpleNamespace(id='indicconformer-ctc-int8', languages=['hi-IN', 'en-IN', 'ta-IN'])
    ]))
    try:
        assert await service.select_caller_language('English')
        assert service._settings.language == 'en'
        assert await service.select_caller_language('Hindi')
        assert service._settings.language == 'hi'
        assert await service.select_caller_language('Tamil')
        assert service._settings.language == 'ta'
    finally:
        await service._client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('language', [None, 'multi', 'auto'])
async def test_caller_reply_language_does_not_disable_auto_recognition(language):
    service = BoundedSpeachesSTTService(api_key='test', settings=SpeachesSTTSettings(
        model='indicconformer-ctc-int8', language=language))
    service._client.models.list = AsyncMock()
    try:
        assert await service.select_caller_language('English')
        assert service._settings.language == language
        service._client.models.list.assert_not_awaited()
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_missing_decoder_cannot_change_recognition_setting():
    service = BoundedSpeachesSTTService(api_key='test', settings=SpeachesSTTSettings(
        model='indicconformer-ctc-int8', language='hi'))
    service._client.models.list = AsyncMock(return_value=SimpleNamespace(data=[
        SimpleNamespace(id='indicconformer-ctc-int8', languages=['hi-IN'])
    ]))
    try:
        assert not await service.select_caller_language('English')
        assert service._settings.language == 'hi'
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_local_auto_stt_sends_phone_capture_hint_only_while_phone_slot_is_open():
    service = BoundedSpeachesSTTService(api_key='test', settings=SpeachesSTTSettings(
        model='indicconformer-ctc-int8', language='auto'))
    create = AsyncMock(return_value=SimpleNamespace(
        text='नौ पाँच तीन', language='hi', model_extra={
            'language_confidence': 0.9, 'detected_language': 'hi', 'language_route': 'detector'
        }
    ))
    service._client.audio.transcriptions.create = create
    service.phone_capture_pending = lambda: True
    try:
        with patch('api.services.pipecat.speaches_stt._normalize_quiet_pcm16_wav', return_value=b'wav'):
            await service._transcribe(b'raw')

        assert create.await_args.kwargs['extra_body'] == {'phone_capture': True}
    finally:
        await service._client.close()
