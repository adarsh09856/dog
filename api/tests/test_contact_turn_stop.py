from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import VADUserStoppedSpeakingFrame
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import SpeechTimeoutUserTurnStopStrategy
from pipecat.audio.vad.vad_analyzer import VADParams

from api.services.pipecat.contact_vad import ContactAwareSileroVADAnalyzer
from api.services.pipecat.contact_turn_stop import ContactAwareTurnStopStrategy


@pytest.mark.asyncio
async def test_phone_dictation_gets_longer_pause_and_normal_speech_restores_default(monkeypatch):
    pending = {"phone": True}
    observed = []

    async def capture_timeout(strategy, frame):
        observed.append(strategy._user_speech_timeout)

    monkeypatch.setattr(SpeechTimeoutUserTurnStopStrategy, "_handle_vad_user_stopped_speaking", capture_timeout)
    strategy = ContactAwareTurnStopStrategy(phone_pending=lambda: pending["phone"])
    await strategy._handle_vad_user_stopped_speaking(VADUserStoppedSpeakingFrame())
    pending["phone"] = False
    await strategy._handle_vad_user_stopped_speaking(VADUserStoppedSpeakingFrame())
    assert observed == [1.2, 0.6]


@pytest.mark.asyncio
async def test_phone_vad_uses_longer_stop_only_during_phone_collection():
    pending = {"phone": False}
    analyzer = ContactAwareSileroVADAnalyzer(
        phone_pending=lambda: pending["phone"],
        params=VADParams(stop_secs=0.2),
    )
    analyzer.set_sample_rate(16000)
    try:
        await analyzer.analyze_audio(bytes(1024))
        assert analyzer.params.stop_secs == 0.2

        pending["phone"] = True
        await analyzer.analyze_audio(bytes(1024))
        assert analyzer.params.stop_secs == 0.55

        pending["phone"] = False
        await analyzer.analyze_audio(bytes(1024))
        assert analyzer.params.stop_secs == 0.2
    finally:
        await analyzer.cleanup()
