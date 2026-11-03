"""Keep configured outbound transition speech ahead of the next LLM turn."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.pipecat.speech_playback import PlaybackOutcome
from api.services.workflow.pipecat_engine import PipecatEngine


@pytest.mark.asyncio
async def test_transition_waits_for_scripted_speech_before_advancing_node(
    three_node_workflow_no_variable_extraction,
):
    engine = PipecatEngine(
        llm=MagicMock(),
        task=SimpleNamespace(queue_frame=AsyncMock()),
        workflow=three_node_workflow_no_variable_extraction,
        call_context_vars={},
    )
    engine.set_node = AsyncMock()
    engine._perform_variable_extraction_if_needed = AsyncMock()
    speech = engine.speech_playback.create(mute_user=True)
    engine.queue_speech = AsyncMock(return_value=speech)
    result_callback = AsyncMock()
    transition = await engine._create_transition_func(
        "collect_details",
        "agent",
        transition_speech="Please tell me your preferred date and time.",
    )

    advancing = asyncio.create_task(
        transition(
            SimpleNamespace(arguments={}, result_callback=result_callback)
        )
    )
    try:
        await asyncio.sleep(0)
        assert not engine.set_node.await_count
        result_callback.assert_not_awaited()

        speech.finish(PlaybackOutcome.PLAYED)
        await asyncio.wait_for(advancing, timeout=1)

        engine.queue_speech.assert_awaited_once_with(
            "Please tell me your preferred date and time.",
            mute_user=True,
            append_to_context=True,
        )
        engine.set_node.assert_awaited_once_with(
            "agent", origin_visit_id=engine.active_agent.visit_id
        )
        result_callback.assert_awaited_once()
    finally:
        if not advancing.done():
            advancing.cancel()
            await asyncio.gather(advancing, return_exceptions=True)
        engine.speech_playback.cancel_all()
