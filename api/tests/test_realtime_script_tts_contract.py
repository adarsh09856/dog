"""Provider-independent contracts for configured speech in realtime calls."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import EndFrame, LLMTextFrame, TTSSpeakFrame
from pipecat.processors.filters.identity_filter import IdentityFilter
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker
from pipecat.tests.mock_transport import MockOutputTransport
from pipecat.tests.mock_tts_service import MockTTSService
from pipecat.transports.base_transport import TransportParams

from api.schemas.ai_model_configuration import (
    OrganizationAIModelConfigurationV2,
    compile_ai_model_configuration_v2,
)
from api.services.pipecat.agent_generation_processor import AgentGenerationProcessor
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.pipeline_builder import build_realtime_pipeline
from api.services.pipecat.realtime.conversation import (
    RealtimeConversationMixin,
    RealtimeScriptTTSSpeakFrame,
)
from api.services.pipecat.worker_runner import run_pipeline_worker
from api.services.workflow.pipecat_engine import PipecatEngine


class _PassThroughFrameProcessor(FrameProcessor):
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class _RealtimeService(RealtimeConversationMixin, _PassThroughFrameProcessor):
    def __init__(self):
        super().__init__()
        self._context = object()
        self.opening_transcripts = []

    async def _handle_initial_greeting(self, _context, _greeting_text):
        raise AssertionError("A scripted greeting must not trigger provider speech")

    async def _handle_context(self, _context):
        raise AssertionError("A scripted message must not trigger an LLM response")

    async def _open_after_prerecorded_greeting(self, transcript):
        self.opening_transcripts.append(transcript)


class _ControlledTTS(MockTTSService):
    def __init__(self):
        super().__init__(mock_audio_duration_ms=80, frame_delay=0)
        self.requested = asyncio.Queue()

    async def run_tts(self, text, context_id):
        await self.requested.put(text)
        async for frame in super().run_tts(text, context_id):
            yield frame


class _RecordingOutput(MockOutputTransport):
    def __init__(self):
        super().__init__(
            params=TransportParams(
                audio_out_enabled=True,
                audio_out_sample_rate=16000,
                audio_out_end_silence_secs=0,
            )
        )
        self.first_audio = asyncio.Event()
        self.audio_frames = []

    async def write_audio_frame(self, frame):
        self.audio_frames.append(frame)
        self.first_audio.set()
        return await super().write_audio_frame(frame)


def test_realtime_audio_helpers_remain_on_the_conversation_mixin():
    assert callable(RealtimeConversationMixin._send_user_audio)
    assert callable(RealtimeConversationMixin._prepare_user_audio)
    assert callable(RealtimeConversationMixin._prepare_audio_frame)


@pytest.mark.asyncio
async def test_scripted_opening_seeds_provider_and_forwards_exact_text():
    service = _RealtimeService()
    service.push_frame = AsyncMock()
    text = "Your appointment is at eight AM."
    frame = RealtimeScriptTTSSpeakFrame(text, append_to_context=True)

    await service.process_frame(frame, FrameDirection.DOWNSTREAM)

    assert service.opening_transcripts == [text]
    service.push_frame.assert_awaited_once_with(frame, FrameDirection.DOWNSTREAM)


@pytest.mark.asyncio
async def test_later_scripted_followup_forwards_without_reseeding_or_generating():
    service = _RealtimeService()
    service.push_frame = AsyncMock()
    await service.handle_prerecorded_greeting(service._context, "Welcome.")
    service.push_frame.reset_mock()
    frame = RealtimeScriptTTSSpeakFrame("The office closes at five.")

    await service.process_frame(frame, FrameDirection.DOWNSTREAM)

    assert service.opening_transcripts == ["Welcome."]
    service.push_frame.assert_awaited_once_with(frame, FrameDirection.DOWNSTREAM)


@pytest.mark.asyncio
async def test_realtime_scripts_play_once_in_order_through_tts_and_call_output():
    engine = PipecatEngine(workflow=None, call_context_vars={})
    engine._is_realtime = True
    realtime = _RealtimeService()
    tts = _ControlledTTS()
    output = _RecordingOutput()
    worker = PipelineWorker(
        Pipeline(
            [realtime, AgentGenerationProcessor(skip_tts_text=True), tts, output]
        ),
        enable_rtvi=False,
    )
    engine.call_worker = worker
    engine.active_agent.llm = realtime
    engine.active_agent.tts = tts
    engine.set_transport_output(output)
    started = asyncio.Event()

    @worker.event_handler("on_pipeline_started")
    async def on_started(*_):
        started.set()

    runner = asyncio.create_task(run_pipeline_worker(worker))
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        scripts = [
            "Welcome. How can I help?",
            "Your appointment is at eight AM.",
        ]
        mock_first_audio_ms = []
        audio_frames_per_script = []
        for script in scripts:
            previous_audio_count = len(output.audio_frames)
            before = time.perf_counter()
            speech = await engine.queue_speech(text=script, mute_user=False, timeout=2)
            await asyncio.wait_for(output.first_audio.wait(), timeout=1)
            mock_first_audio_ms.append((time.perf_counter() - before) * 1000)
            assert await asyncio.wait_for(speech.wait(), timeout=1)
            audio_frames_per_script.append(
                len(output.audio_frames) - previous_audio_count
            )
            output.first_audio.clear()

        assert [await tts.requested.get() for _ in scripts] == scripts
        assert realtime.opening_transcripts == [scripts[0]]
        assert audio_frames_per_script == [2, 2]
        assert len(output.audio_frames) == 4
        assert max(mock_first_audio_ms) < 1000
        print(
            "controlled mock TTS first audio max: "
            f"{max(mock_first_audio_ms):.2f} ms"
        )
    finally:
        if not runner.done():
            await worker.queue_frame(EndFrame())
        await asyncio.wait_for(runner, timeout=3)


@pytest.mark.asyncio
async def test_provider_transcript_is_marked_to_skip_auxiliary_tts():
    generation = AgentGenerationProcessor(skip_tts_text=True)
    generation.push_frame = AsyncMock()
    text = LLMTextFrame("Transcript for provider-generated audio.")

    await generation.process_frame(text, FrameDirection.DOWNSTREAM)

    assert text.skip_tts is True
    generation.push_frame.assert_awaited_once_with(text, FrameDirection.DOWNSTREAM)


def test_auxiliary_script_tts_is_in_the_existing_single_input_pipeline():
    input_processor = IdentityFilter()
    output = IdentityFilter()
    script_tts = IdentityFilter()
    realtime_llm = IdentityFilter()
    generation = IdentityFilter()
    pipeline = build_realtime_pipeline(
        transport=type(
            "Transport",
            (),
            {"input": lambda _self: input_processor, "output": lambda _self: output},
        )(),
        realtime_llm=realtime_llm,
        audio_buffer=IdentityFilter(),
        user_context_aggregator=IdentityFilter(),
        assistant_context_aggregator=IdentityFilter(),
        call_monitor_processor=IdentityFilter(),
        agent_generation_processor=generation,
        pipeline_metrics_aggregator=IdentityFilter(),
        termination_funnel=IdentityFilter(),
        script_tts=script_tts,
    )
    processors = pipeline.processors

    assert processors.count(input_processor) == 1
    assert processors.index(realtime_llm) < processors.index(generation)
    assert processors.index(generation) < processors.index(script_tts)
    assert processors.index(script_tts) < processors.index(output)


def test_byok_script_tts_keeps_its_selected_provider_model_voice_and_language():
    config = OrganizationAIModelConfigurationV2.model_validate(
        {
            "mode": "byok",
            "byok": {
                "mode": "realtime",
                "realtime": {
                    "realtime": {
                        "provider": "google_realtime",
                        "api_key": "rt-key",
                        "model": "gemini-3.1-flash-live-preview",
                        "voice": "Puck",
                        "language": "hi",
                    },
                    "llm": {
                        "provider": "openai",
                        "api_key": "llm-key",
                        "model": "gpt-4.1-mini",
                    },
                    "script_tts": {
                        "provider": "speaches",
                        "api_key": "local-cpu-token",
                        "model": "indic-vits-rasa-13",
                        "voice": "KAN_F",
                        "language": "hi",
                        "base_url": "http://tts.test/v1/audio/speech",
                    },
                },
            },
        }
    )

    effective = compile_ai_model_configuration_v2(config)

    assert effective.realtime.voice == "Puck"
    assert effective.tts.provider == "speaches"
    assert effective.tts.model == "indic-vits-rasa-13"
    assert effective.tts.voice == "KAN_F"
    assert effective.tts.language == "hi"
    assert effective.tts.base_url == "http://tts.test/v1/audio/speech"


def test_managed_realtime_script_tts_is_separate_from_native_s2s_voice():
    config = OrganizationAIModelConfigurationV2(
        mode="kodewaves",
        kodewaves={
            "is_realtime": True,
            "realtime_provider": "google",
            "realtime_model": "gemini-3.1-flash-live-preview",
            "voice": "Kore",
            "script_tts_engine_type": "local_cpu",
            "script_tts_model": "indic-vits-rasa-13",
            "script_tts_voice": "KAN_F",
            "script_tts_language": "hi",
            "script_tts_speed": 1.1,
        },
    )

    effective = compile_ai_model_configuration_v2(config)

    assert effective.realtime.voice == "Kore"
    assert effective.tts.provider == "kodewaves"
    assert effective.tts.api_key == "sovereign-local-cpu"
    assert effective.tts.model == "indic-vits-rasa-13"
    assert effective.tts.voice == "KAN_F"
    assert effective.tts.language == "hi"
    assert effective.tts.speed == 1.1


def test_legacy_realtime_config_starts_without_auxiliary_tts(monkeypatch):
    from api.services.pipecat import run_pipeline

    config = OrganizationAIModelConfigurationV2(
        mode="kodewaves",
        kodewaves={
            "is_realtime": True,
            "realtime_provider": "google",
            "realtime_model": "gemini-3.1-flash-live-preview",
            "voice": "Puck",
        },
    )
    effective = compile_ai_model_configuration_v2(config)
    monkeypatch.setattr(
        run_pipeline,
        "create_tts_service",
        lambda *_args, **_kwargs: pytest.fail(
            "legacy realtime config must not construct standalone TTS"
        ),
    )

    assert effective.tts is None
    assert run_pipeline.create_optional_realtime_script_tts(
        effective, AudioConfig(16000, 16000)
    ) is None

    input_processor = IdentityFilter()
    output_processor = IdentityFilter()
    pipeline = build_realtime_pipeline(
        transport=SimpleNamespace(
            input=lambda: input_processor,
            output=lambda: output_processor,
        ),
        realtime_llm=IdentityFilter(),
        audio_buffer=IdentityFilter(),
        user_context_aggregator=IdentityFilter(),
        assistant_context_aggregator=IdentityFilter(),
        call_monitor_processor=IdentityFilter(),
        agent_generation_processor=IdentityFilter(),
        pipeline_metrics_aggregator=IdentityFilter(),
        termination_funnel=IdentityFilter(),
        script_tts=None,
    )
    assert pipeline.processors.count(input_processor) == 1
    assert pipeline.processors.count(output_processor) == 1
    assert len(pipeline.processors) == 12


@pytest.mark.asyncio
async def test_legacy_realtime_queue_keeps_native_voice_and_emits_one_speak_frame():
    engine = PipecatEngine(workflow=None, call_context_vars={})
    engine._is_realtime = True
    engine.active_agent.llm = SimpleNamespace(queue_frame=AsyncMock())
    engine.active_agent.tts = None

    await engine.queue_speech(
        text="Welcome. How can I help?",
        mute_user=False,
        timeout=2,
    )

    speak_frames = [
        call.args[0]
        for call in engine.active_agent.llm.queue_frame.await_args_list
        if isinstance(call.args[0], TTSSpeakFrame)
    ]
    assert len(speak_frames) == 1
    assert speak_frames[0].text == "Welcome. How can I help?"
    assert not isinstance(speak_frames[0], RealtimeScriptTTSSpeakFrame)


def test_byok_script_tts_factory_uses_selected_provider_model_voice_and_language(
    monkeypatch,
):
    from api.services.pipecat import service_factory, speaches_tts

    class _CapturedTTS:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(speaches_tts, "SpeachesLiveTTSService", _CapturedTTS)
    config = OrganizationAIModelConfigurationV2.model_validate(
        {
            "mode": "byok",
            "byok": {
                "mode": "realtime",
                "realtime": {
                    "realtime": {
                        "provider": "google_realtime",
                        "api_key": "rt-key",
                        "model": "gemini-3.1-flash-live-preview",
                        "voice": "Puck",
                    },
                    "llm": {
                        "provider": "openai",
                        "api_key": "llm-key",
                        "model": "gpt-4.1-mini",
                    },
                    "script_tts": {
                        "provider": "speaches",
                        "api_key": "local-cpu-token",
                        "model": "indic-vits-rasa-13",
                        "voice": "KAN_F",
                        "language": "hi",
                        "speed": 1.1,
                        "base_url": "http://tts.test/v1/audio/speech",
                    },
                },
            },
        }
    )
    effective = compile_ai_model_configuration_v2(config)

    service = service_factory.create_tts_service(
        effective,
        AudioConfig(16000, 16000),
    )

    assert service.kwargs["base_url"] == "http://tts.test/v1/audio/speech"
    assert service.kwargs["speech_language"] == "hi"
    assert service.kwargs["settings"].model == "indic-vits-rasa-13"
    assert service.kwargs["settings"].voice == "KAN_F"
    assert service.kwargs["settings"].speed == 1.1
