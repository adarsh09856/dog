from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pipecat.services.speaches.stt import SpeachesSTTService


@pytest.mark.asyncio
@pytest.mark.parametrize("language,expected", [("hi-IN", "hi"), ("en", "en"), (None, None)])
async def test_speaches_preserves_language_or_requests_auto_detection(language, expected):
    service = SpeachesSTTService.__new__(SpeachesSTTService)
    service._settings = SimpleNamespace(model="selected-model", language=language,
                                        prompt=None, temperature=0)
    create = AsyncMock(return_value=SimpleNamespace(text="transcript"))
    service._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    await service._transcribe(b"audio")
    payload = create.await_args.kwargs
    assert payload["model"] == "selected-model"
    if expected is None:
        assert "language" not in payload
    else:
        assert payload["language"] == expected
