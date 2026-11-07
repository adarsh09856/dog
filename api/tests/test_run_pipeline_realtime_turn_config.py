import pytest

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.turns.user_start import (
    ExternalUserTurnStartStrategy,
    MinWordsUserTurnStartStrategy,
    TranscriptionUserTurnStartStrategy,
)
from pipecat.turns.user_start.vad_user_turn_start_strategy import (
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import (
    ExternalUserTurnStopStrategy,
    SpeechTimeoutUserTurnStopStrategy,
    TurnAnalyzerUserTurnStopStrategy,
)

import api.services.pipecat.run_pipeline as run_pipeline_module
from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.run_pipeline import (
    DEFAULT_TURN_START_MIN_WORDS,
    DEFAULT_USER_TURN_STOP_TIMEOUT,
    EXTERNAL_TURN_USER_STOP_TIMEOUT,
    _create_non_realtime_user_turn_start_strategies,
    _create_non_realtime_user_turn_stop_strategies,
    _create_realtime_user_turn_config,
    _is_local_segmented_stt,
    _resolve_user_turn_stop_timeout,
    _uses_local_indic_phone_capture,
)


def _stt_config(provider, api_key, model="indicconformer-ctc-int8"):
    from types import SimpleNamespace

    return SimpleNamespace(stt=SimpleNamespace(
        provider=provider,
        api_key=api_key,
        model=model,
    ))


@pytest.mark.parametrize(
    "provider,api_key,expected",
    [
        ("speaches", None, True),
        ("speaches", "none", True),
        ("speaches", " None ", True),
        ("speaches", "   ", True),
        ("speaches", "local-cpu-token", True),
        ("kodewaves", "sovereign-local-cpu", True),
        # Blank managed-provider credentials can resolve to cloud STT, so they
        # must never activate local segmentation or phone rescue.
        ("kodewaves", None, False),
        ("kodewaves", "none", False),
        ("deepgram", None, False),
        ("deepgram", "local-cpu-token", False),
    ],
)
def test_local_stt_and_phone_capture_share_provider_safe_config_gate(
    provider, api_key, expected,
):
    user_config = _stt_config(provider, api_key)
    stt = object()

    assert _is_local_segmented_stt(user_config, is_realtime=False) is expected
    assert _uses_local_indic_phone_capture(
        stt, user_config, is_realtime=False
    ) is expected


def test_phone_capture_requires_local_indic_model_and_cascade_pipeline():
    user_config = _stt_config("speaches", "none", model="other-model")

    assert _is_local_segmented_stt(user_config, is_realtime=False)
    assert not _uses_local_indic_phone_capture(
        object(), user_config, is_realtime=False
    )
    user_config = _stt_config("speaches", "none")
    assert not _is_local_segmented_stt(user_config, is_realtime=True)
    assert not _uses_local_indic_phone_capture(
        object(), user_config, is_realtime=True
    )


def test_gemini_realtime_uses_local_vad_without_local_interruptions():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.GOOGLE_REALTIME.value
    )

    assert isinstance(vad_analyzer, SileroVADAnalyzer)
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is False
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_gemini_vertex_realtime_uses_same_turn_config_as_gemini_live():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.GOOGLE_VERTEX_REALTIME.value
    )

    assert isinstance(vad_analyzer, SileroVADAnalyzer)
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is False
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_nova_sonic_uses_local_vad_without_local_interruptions():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.AWS_NOVA_SONIC.value
    )

    assert isinstance(vad_analyzer, SileroVADAnalyzer)
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is False
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_openai_realtime_uses_provider_turn_frames_without_local_vad():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.OPENAI_REALTIME.value
    )

    assert vad_analyzer is None
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], ExternalUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is True
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], ExternalUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_azure_realtime_uses_provider_turn_frames_without_local_vad():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.AZURE_REALTIME.value
    )

    assert vad_analyzer is None
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], ExternalUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is True
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], ExternalUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_grok_realtime_uses_provider_turn_frames_without_local_vad():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.GROK_REALTIME.value
    )

    assert vad_analyzer is None
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], ExternalUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is True
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], ExternalUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_ultravox_realtime_uses_local_vad_with_local_interruptions():
    strategies, vad_analyzer = _create_realtime_user_turn_config(
        ServiceProviders.ULTRAVOX_REALTIME.value
    )

    assert isinstance(vad_analyzer, SileroVADAnalyzer)
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is True
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_unknown_realtime_providers_keep_local_vad():
    strategies, vad_analyzer = _create_realtime_user_turn_config("other_realtime")

    assert isinstance(vad_analyzer, SileroVADAnalyzer)
    assert len(strategies.start) == 1
    assert isinstance(strategies.start[0], VADUserTurnStartStrategy)
    assert strategies.start[0]._enable_interruptions is True
    assert len(strategies.stop) == 1
    assert isinstance(strategies.stop[0], SpeechTimeoutUserTurnStopStrategy)
    assert strategies.stop[0].wait_for_transcript is False


def test_non_realtime_default_uses_external_start_for_external_turn_stt():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {},
        uses_external_turns=True,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], ExternalUserTurnStartStrategy)
    assert strategies[0]._enable_interruptions is True


def test_non_realtime_default_uses_transcription_fallback_and_vad_for_standard_stt():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {},
        uses_external_turns=False,
    )

    assert len(strategies) == 2
    assert isinstance(strategies[0], TranscriptionUserTurnStartStrategy)
    assert isinstance(strategies[1], VADUserTurnStartStrategy)


def test_local_segmented_stt_waits_for_final_transcript_before_interrupting():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {}, uses_external_turns=False, local_segmented_stt=True,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], TranscriptionUserTurnStartStrategy)
    assert strategies[0]._use_interim is False


def test_non_realtime_can_use_min_words_start_strategy():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {"turn_start_strategy": "min_words", "turn_start_min_words": 4},
        uses_external_turns=False,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], MinWordsUserTurnStartStrategy)
    assert strategies[0]._min_words == 4


def test_external_turn_stt_overrides_an_explicit_min_words_request():
    """An STT that reports its own turn boundaries decides the turn start.

    min_words gates the start on transcript text, which would ignore the
    provider's turn detection on the start side while still using it to end the
    turn, and would resolve the start from a queued frame — the shape that lets
    a turn's own interruption flush the stop proposal queued behind it.
    """
    strategies = _create_non_realtime_user_turn_start_strategies(
        {"turn_start_strategy": "min_words", "turn_start_min_words": 4},
        uses_external_turns=True,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], ExternalUserTurnStartStrategy)


def test_external_turn_stt_overrides_a_retired_strategy_value():
    """A definition still carrying "provisional_vad" resolves, it does not raise."""
    strategies = _create_non_realtime_user_turn_start_strategies(
        {"turn_start_strategy": "provisional_vad"},
        uses_external_turns=True,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], ExternalUserTurnStartStrategy)


def test_retired_strategy_value_falls_back_to_default_without_external_turns():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {"turn_start_strategy": "provisional_vad"},
        uses_external_turns=False,
    )

    assert len(strategies) == 2
    assert isinstance(strategies[0], TranscriptionUserTurnStartStrategy)
    assert isinstance(strategies[1], VADUserTurnStartStrategy)


def test_non_realtime_min_words_start_strategy_has_default_threshold():
    strategies = _create_non_realtime_user_turn_start_strategies(
        {"turn_start_strategy": "min_words"},
        uses_external_turns=False,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], MinWordsUserTurnStartStrategy)
    assert strategies[0]._min_words == DEFAULT_TURN_START_MIN_WORDS


def test_non_realtime_uses_external_stop_for_external_turn_stt():
    strategies = _create_non_realtime_user_turn_stop_strategies(
        {},
        uses_external_turns=True,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], ExternalUserTurnStopStrategy)


def test_non_realtime_default_uses_speech_timeout_stop():
    strategies = _create_non_realtime_user_turn_stop_strategies(
        {},
        uses_external_turns=False,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], SpeechTimeoutUserTurnStopStrategy)


def test_local_ollama_segmented_stt_uses_speculative_turn_stop():
    from api.services.pipecat.local_turn_stop import SpeculativeLocalTurnStopStrategy

    strategies = _create_non_realtime_user_turn_stop_strategies(
        {},
        uses_external_turns=False,
        local_segmented_stt=True,
        local_cpu_pipeline=True,
        can_speculate=lambda _text: True,
        speech_timeout=lambda: 0.6,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], SpeculativeLocalTurnStopStrategy)
    strategies[0]._apply_speech_timeout()
    assert strategies[0]._user_speech_timeout == 0.6


def test_local_ollama_phone_collection_keeps_longer_pause():
    from api.services.pipecat.local_turn_stop import SpeculativeLocalTurnStopStrategy

    strategies = _create_non_realtime_user_turn_stop_strategies(
        {},
        uses_external_turns=False,
        local_segmented_stt=True,
        local_cpu_pipeline=True,
        phone_pending=lambda: True,
        speech_timeout=lambda: 1.2,
    )

    assert isinstance(strategies[0], SpeculativeLocalTurnStopStrategy)
    strategies[0]._apply_speech_timeout()
    assert strategies[0]._user_speech_timeout == 1.2


def test_non_realtime_can_use_turn_analyzer_stop_strategy(monkeypatch):
    monkeypatch.setattr(
        run_pipeline_module,
        "LocalSmartTurnAnalyzerV3",
        lambda *, params: params,
    )

    strategies = _create_non_realtime_user_turn_stop_strategies(
        {"turn_stop_strategy": "turn_analyzer", "smart_turn_stop_secs": 1.5},
        uses_external_turns=False,
    )

    assert len(strategies) == 1
    assert isinstance(strategies[0], TurnAnalyzerUserTurnStopStrategy)
    assert strategies[0]._turn_analyzer.stop_secs == 1.5


def test_external_turn_stt_uses_longer_stop_timeout():
    assert (
        _resolve_user_turn_stop_timeout({}, uses_external_turns=True)
        == EXTERNAL_TURN_USER_STOP_TIMEOUT
    )


def test_standard_stt_keeps_default_stop_timeout():
    assert (
        _resolve_user_turn_stop_timeout({}, uses_external_turns=False)
        == DEFAULT_USER_TURN_STOP_TIMEOUT
    )


def test_bounded_cpu_stt_cannot_be_cut_off_before_its_recognition_deadline():
    from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService

    timeout = _resolve_user_turn_stop_timeout(
        {}, uses_external_turns=False,
        recognition_timeout_seconds=BoundedSpeachesSTTService.recognition_timeout_seconds,
    )
    assert timeout > BoundedSpeachesSTTService.recognition_timeout_seconds


def test_workflow_config_can_override_user_turn_stop_timeout():
    assert (
        _resolve_user_turn_stop_timeout(
            {"user_turn_stop_timeout": "12.5"},
            uses_external_turns=True,
        )
        == 12.5
    )
