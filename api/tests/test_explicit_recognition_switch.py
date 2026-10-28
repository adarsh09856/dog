from types import SimpleNamespace
from unittest.mock import AsyncMock

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
