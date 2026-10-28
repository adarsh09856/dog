import asyncio
from types import SimpleNamespace

import pytest

from api.services.workflow.pipecat_engine_context_summarizer import (
    ContextSummarizationManager,
)
from pipecat.utils.context.llm_context_summarization import (
    LLMContextSummarizationUtil,
)


class _Context:
    def __init__(self, messages):
        self.messages = messages

    def set_messages(self, messages):
        self.messages = messages


@pytest.mark.asyncio
async def test_restarting_and_cleanup_await_cancelled_summarization_tasks():
    manager = ContextSummarizationManager(
        SimpleNamespace(
            active_agent=SimpleNamespace(current_node=SimpleNamespace(name="test-node"))
        )
    )
    stopped = []

    async def wait_forever():
        task = asyncio.current_task()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(task)

    manager._summarize_context_in_background = wait_forever

    await manager.start()
    first_task = manager._summarization_task
    await asyncio.sleep(0)

    await manager.start()
    second_task = manager._summarization_task
    await asyncio.sleep(0)

    assert first_task is not None and first_task.done()
    assert first_task in stopped
    assert second_task is not None and not second_task.done()

    await manager.cleanup()

    assert second_task.done()
    assert second_task in stopped
    assert manager._summarization_task is None


@pytest.mark.asyncio
async def test_start_without_current_node_does_not_create_task():
    manager = ContextSummarizationManager(
        SimpleNamespace(active_agent=SimpleNamespace(current_node=None))
    )

    await manager.start()

    assert manager._summarization_task is None


@pytest.mark.asyncio
async def test_compaction_keeps_the_user_turn_for_a_retained_assistant_reply():
    # A mid-conversation system instruction makes the fixed eight-message
    # suffix start at an assistant reply without its caller turn.
    messages = [{"role": "system", "content": "system"}]
    for turn in range(6):
        messages.extend(
            [
                {"role": "user", "content": f"caller {turn}"},
                {"role": "assistant", "content": f"reply {turn}"},
            ]
        )
        if turn == 2:
            messages.append({"role": "system", "content": "node instruction"})
    context = _Context(messages)
    requested_keep = []

    async def summarize(frame):
        requested_keep.append(frame.min_messages_to_keep)
        selection = LLMContextSummarizationUtil.get_messages_to_summarize(
            frame.context, frame.min_messages_to_keep
        )
        return "Earlier conversation summary", selection.last_summarized_index

    node = SimpleNamespace(id="node-1", name="test-node")
    engine = SimpleNamespace(
        context=context,
        active_agent=SimpleNamespace(
            current_node=node,
            inference_llm=SimpleNamespace(_generate_summary=summarize),
        ),
        _get_otel_context=lambda: None,
    )
    manager = ContextSummarizationManager(engine)

    await manager._summarize_context_in_background()

    assert requested_keep == [manager.config.min_messages_after_summary + 1]
    assert context.messages[0] == messages[0]
    assert context.messages[1]["content"] == manager.config.summary_message_template.format(
        summary="Earlier conversation summary"
    )
    retained = context.messages[2:]
    assert retained[0] == {"role": "user", "content": "caller 2"}
    assert retained[1] == {"role": "assistant", "content": "reply 2"}
    assert len(retained) == manager.config.min_messages_after_summary + 1


@pytest.mark.asyncio
async def test_compaction_does_not_expand_suffix_when_it_already_starts_with_user():
    messages = [{"role": "system", "content": "system"}]
    for turn in range(7):
        messages.extend(
            [
                {"role": "user", "content": f"caller {turn}"},
                {"role": "assistant", "content": f"reply {turn}"},
            ]
        )
    context = _Context(messages)
    requested_keep = []

    async def summarize(frame):
        requested_keep.append(frame.min_messages_to_keep)
        selection = LLMContextSummarizationUtil.get_messages_to_summarize(
            frame.context, frame.min_messages_to_keep
        )
        return "Earlier conversation summary", selection.last_summarized_index

    node = SimpleNamespace(id="node-1", name="test-node")
    engine = SimpleNamespace(
        context=context,
        active_agent=SimpleNamespace(
            current_node=node,
            inference_llm=SimpleNamespace(_generate_summary=summarize),
        ),
        _get_otel_context=lambda: None,
    )
    manager = ContextSummarizationManager(engine)

    await manager._summarize_context_in_background()

    assert requested_keep == [manager.config.min_messages_after_summary]
    retained = context.messages[2:]
    assert retained[0] == {"role": "user", "content": "caller 3"}
    assert len(retained) == manager.config.min_messages_after_summary
