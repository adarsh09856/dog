from types import SimpleNamespace
from unittest.mock import AsyncMock

from pipecat.frames.frames import OutputAudioRawFrame, TranscriptionFrame
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams

from api.services.pipecat import realtime_feedback_observer as module


def test_transport_silence_is_not_first_speech_and_internal_silence_is_counted(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())
    output = BaseOutputTransport(TransportParams())
    observer._observe_voice_audio(SimpleNamespace(frame=TranscriptionFrame(
        text='synthetic', user_id='test', timestamp=''), source=output))

    def push(pcm, timestamp):
        now[0] = timestamp
        observer._observe_voice_audio(SimpleNamespace(frame=OutputAudioRawFrame(
            pcm, 16000, 1), source=output))

    silence = b'\x00\x00' * 640
    speech = (1000).to_bytes(2, 'little', signed=True) * 640
    push(silence, 10.04)
    assert observer._output_audio_trace['first_frame_at'] == 10.04
    assert observer._output_audio_trace['first_speech_at'] is None
    push(speech, 12.0)
    push(silence, 12.04)
    push(silence, 12.08)
    push(speech, 12.12)
    assert observer._output_audio_trace['first_speech_at'] == 12.0
    assert observer._output_audio_trace['max_internal_silence_ms'] == 80.0
    push(silence, 12.16)
    assert observer._output_audio_trace['max_internal_silence_ms'] == 80.0
