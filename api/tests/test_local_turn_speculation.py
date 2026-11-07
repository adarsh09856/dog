from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import (
    EagerEndOfTurnCancelFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)

from api.services.pipecat.local_turn_stop import SpeculativeLocalTurnStopStrategy


def strategy():
    s = SpeculativeLocalTurnStopStrategy()
    s._vad_stopped = True
    s._stt_wait_done = True
    s.trigger_user_turn_inference_triggered = AsyncMock()
    s.trigger_user_turn_finalized = AsyncMock()
    s.trigger_user_turn_speculation_cancelled = AsyncMock()
    return s


def transcript(text):
    return TranscriptionFrame(text=text, user_id='caller', timestamp='', finalized=True)


@pytest.mark.asyncio
async def test_final_segment_prepares_but_does_not_finalize_before_pause_window():
    s = strategy()
    await s._handle_transcription(transcript('मुझे मदद चाहिए'))
    assert s._user_speech_timeout == 0.6
    s.trigger_user_turn_inference_triggered.assert_awaited_once()
    assert s.trigger_user_turn_inference_triggered.call_args.kwargs['speculation'].text == 'मुझे मदद चाहिए'
    s.trigger_user_turn_finalized.assert_not_awaited()
    await s.trigger_user_turn_stopped()
    s.trigger_user_turn_finalized.assert_awaited_once_with(enable_user_speaking_frames=None, confirms_speculation=True)
    assert s.trigger_user_turn_inference_triggered.await_count == 1


@pytest.mark.asyncio
async def test_final_transcript_before_vad_stop_still_starts_speculation(monkeypatch):
    from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
        SpeechTimeoutUserTurnStopStrategy,
    )

    async def mark_vad_stopped(strategy, _frame):
        strategy._vad_stopped = True

    async def accept_final_transcript(strategy, frame):
        strategy._text += frame.text
        strategy._transcript_finalized = frame.finalized
        strategy._stt_wait_done = True

    monkeypatch.setattr(
        SpeechTimeoutUserTurnStopStrategy,
        '_handle_transcription',
        accept_final_transcript,
    )
    monkeypatch.setattr(
        SpeechTimeoutUserTurnStopStrategy,
        '_handle_vad_user_stopped_speaking',
        mark_vad_stopped,
    )
    s = strategy()
    s._vad_stopped = False
    await s._handle_transcription(transcript('मुझे मदद चाहिए'))
    s.trigger_user_turn_inference_triggered.assert_not_awaited()

    await s._handle_vad_user_stopped_speaking(VADUserStoppedSpeakingFrame())
    s.trigger_user_turn_inference_triggered.assert_awaited_once()


@pytest.mark.asyncio
async def test_resumed_voice_withdraws_before_confirmation():
    s = strategy()
    await s._handle_transcription(transcript('मुझे अपनी समस्या'))
    await s._handle_vad_user_started_speaking(VADUserStartedSpeakingFrame())
    assert s._local_speculation is None
    s.trigger_user_turn_speculation_cancelled.assert_awaited_once()
    s.trigger_user_turn_finalized.assert_not_awaited()


@pytest.mark.asyncio
async def test_interim_transcript_withdraws_stale_finalized_text():
    s = strategy()
    await s._handle_transcription(transcript('मुझे मदद चाहिए'))

    await s.process_frame(
        InterimTranscriptionFrame(text='और जानकारी', user_id='caller', timestamp='')
    )

    assert s._local_speculation is None
    s.trigger_user_turn_speculation_cancelled.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_action_cancellation_requires_fresh_confirmed_inference():
    s = strategy()
    await s._handle_transcription(transcript('Book it'))
    await s.process_frame(EagerEndOfTurnCancelFrame())
    await s.trigger_user_turn_stopped()
    assert s.trigger_user_turn_inference_triggered.await_count == 2
    assert s.trigger_user_turn_inference_triggered.call_args.kwargs == {}
    assert not s.trigger_user_turn_finalized.call_args.kwargs.get('confirms_speculation', False)


@pytest.mark.asyncio
async def test_reset_withdraws_provisional_response():
    s = strategy()
    await s._handle_transcription(transcript('first segment'))
    await s._reset(clear_vad_user_speaking=True)
    assert s._text == ''
    assert s._local_speculation is None
    s.trigger_user_turn_speculation_cancelled.assert_awaited_once()

@pytest.mark.asyncio
async def test_provisional_inference_skips_booking_contact_shortcuts(monkeypatch):
    from types import SimpleNamespace

    from pipecat.services.openai.llm import OpenAILLMService

    from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
    native = AsyncMock()
    monkeypatch.setattr(OpenAILLMService, '_process_context', native)
    service = object.__new__(BookingOpenAILLMService)
    service._speculation_gate = SimpleNamespace(is_speculating=True)
    service._contact_conversation_state = {'pending_phone': '+919000000001'}
    context = object()
    await service._process_context(context)
    native.assert_awaited_once_with(context)
    assert service._contact_conversation_state == {'pending_phone': '+919000000001'}

@pytest.mark.asyncio
async def test_changed_segment_withdraws_old_provisional_text():
    s = strategy()
    await s._handle_transcription(transcript('first part '))
    await s._handle_transcription(transcript('continued'))
    s.trigger_user_turn_speculation_cancelled.assert_awaited_once()
    assert s._local_speculation.text == 'first part continued'
    await s.trigger_user_turn_stopped()
    assert s.trigger_user_turn_finalized.call_args.kwargs['confirms_speculation']


@pytest.mark.asyncio
async def test_native_tool_guard_cancels_instead_of_executing_speculative_booking():
    from types import SimpleNamespace

    from pipecat.frames.frames import EagerEndOfTurnCancelFrame

    from api.services.pipecat.booking_tool_choice import BookingOpenAILLMService
    service = BookingOpenAILLMService(api_key='test', model='test', base_url='http://localhost:11434/v1')
    service._speculation_gate.begin_speculation(True)
    service.broadcast_frame = AsyncMock()
    try:
        await service.run_function_calls([SimpleNamespace(function_name='book_appointment')])
        service.broadcast_frame.assert_awaited_once_with(EagerEndOfTurnCancelFrame)
    finally:
        await service._client.close()


@pytest.mark.asyncio
async def test_contact_turn_uses_confirmed_handler_instead_of_speculative_model():
    s = strategy()
    s._can_speculate = lambda text: False
    await s._handle_transcription(transcript('मेरा नाम आदर्श है'))
    s.trigger_user_turn_inference_triggered.assert_not_awaited()
    await s.trigger_user_turn_stopped()
    s.trigger_user_turn_inference_triggered.assert_awaited_once_with()
    assert not s.trigger_user_turn_finalized.call_args.kwargs.get('confirms_speculation', False)


@pytest.mark.asyncio
async def test_phone_pause_window_returns_to_default_when_collection_ends():
    pending = {'phone': True}
    s = strategy()
    s._can_speculate = lambda _: False
    s._speech_timeout = lambda: 1.2 if pending['phone'] else 0.6
    await s._handle_transcription(transcript('फोर है'))
    assert s._user_speech_timeout == 1.2
    pending['phone'] = False
    await s._handle_transcription(transcript('another request'))
    assert s._user_speech_timeout == 0.6
