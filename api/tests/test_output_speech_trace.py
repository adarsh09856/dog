from types import SimpleNamespace
from unittest.mock import AsyncMock

from pipecat.frames.frames import (
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TranscriptionFrame,
)
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import TransportParams

from api.services.pipecat import realtime_feedback_observer as module


def _observe_tts_trace(monkeypatch, observer, context_id, pcm_frames, *, start=10.0):
    now = [start]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    observer._observe_voice_audio(SimpleNamespace(
        frame=TTSStartedFrame(context_id=context_id), source=None
    ))
    for offset, pcm in pcm_frames:
        now[0] = start + offset
        observer._observe_voice_audio(SimpleNamespace(
            frame=TTSAudioRawFrame(
                audio=pcm,
                sample_rate=24000,
                num_channels=1,
                context_id=context_id,
            ),
            source=None,
        ))
    now[0] += 0.01
    return observer._observe_voice_audio(SimpleNamespace(
        frame=TTSStoppedFrame(context_id=context_id), source=None
    ))


def test_tts_trace_keeps_first_pcm_and_reports_first_non_silent_pcm(monkeypatch):
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())
    silence = b"\x00\x00" * 240
    speech = (1000).to_bytes(2, "little", signed=True) * 240

    event = _observe_tts_trace(
        monkeypatch,
        observer,
        "tts-silence-then-speech",
        [(0.04, silence), (0.16, speech)],
    )

    assert event["payload"]["first_audio_ms"] == 40.0
    assert event["payload"]["first_non_silent_pcm_ms"] == 160.0


def test_tts_trace_reports_no_non_silent_pcm_for_all_silent_audio(monkeypatch):
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())
    silence = b"\x00\x00" * 240

    event = _observe_tts_trace(
        monkeypatch,
        observer,
        "tts-all-silence",
        [(0.04, silence), (0.08, silence)],
    )

    assert event["payload"]["first_audio_ms"] == 40.0
    assert event["payload"]["first_non_silent_pcm_ms"] is None


def test_tts_trace_reports_first_non_silent_pcm_when_first_frame_has_audio(monkeypatch):
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())
    speech = (1000).to_bytes(2, "little", signed=True) * 240

    event = _observe_tts_trace(
        monkeypatch,
        observer,
        "tts-first-frame-speech",
        [(0.04, speech)],
    )

    assert event["payload"]["first_audio_ms"] == 40.0
    assert event["payload"]["first_non_silent_pcm_ms"] == 40.0


def test_tts_trace_ignores_pcm_frame_without_complete_sample(monkeypatch):
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())

    event = _observe_tts_trace(
        monkeypatch,
        observer,
        "tts-one-byte-frame",
        [(0.04, b"\x01")],
    )

    assert event["payload"]["first_audio_ms"] == 40.0
    assert event["payload"]["first_non_silent_pcm_ms"] is None


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
