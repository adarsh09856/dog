from types import SimpleNamespace
from unittest.mock import AsyncMock

from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TranscriptionFrame,
)
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


def test_audio_gap_summaries_are_persistable_without_text_or_audio_payload(monkeypatch):
    now = [20.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    observer = module.RealtimeFeedbackObserver(ws_sender=AsyncMock())
    output = BaseOutputTransport(TransportParams())
    observer._observe_voice_audio(SimpleNamespace(frame=TranscriptionFrame(
        text='synthetic', user_id='test', timestamp=''), source=output))

    observer._observe_voice_audio(SimpleNamespace(frame=TTSStartedFrame(context_id='tts-1')))
    now[0] = 20.1
    observer._observe_voice_audio(SimpleNamespace(frame=TTSAudioRawFrame(
        b'\x01\x00' * 320, 16000, 1, context_id='tts-1'), source=None))
    now[0] = 21.0
    tts_event = observer._observe_voice_audio(SimpleNamespace(
        frame=TTSStoppedFrame(context_id='tts-1')))
    assert tts_event['type'] == 'rtf-audio-health'
    assert tts_event['payload']['stage'] == 'tts_pcm'
    assert tts_event['payload']['max_gap_ms'] == 0.0
    assert 'text' not in tts_event['payload']

    now[0] = 22.0
    observer._observe_voice_audio(SimpleNamespace(frame=OutputAudioRawFrame(
        b'\x00\x00' * 640, 16000, 1), source=output))
    now[0] = 22.04
    observer._observe_voice_audio(SimpleNamespace(frame=OutputAudioRawFrame(
        (1000).to_bytes(2, 'little', signed=True) * 640, 16000, 1), source=output))
    now[0] = 22.08
    playback_event = observer._observe_voice_audio(SimpleNamespace(
        frame=BotStoppedSpeakingFrame(), source=output))
    assert playback_event['type'] == 'rtf-audio-health'
    assert playback_event['payload']['stage'] == 'transport_playback'
    assert playback_event['payload']['first_speech_frame_ms'] == 2040.0
    assert playback_event['payload']['max_gap_ms'] == 40.0
    assert 'text' not in playback_event['payload']
