from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest


def _staged_state():
    return {
        "booking_confirmation_slot": "2035-10-20T10:00",
        "booking_time_question_date": "2035-10-20",
        "prior_booking_request": "Book an appointment October 20",
        "active_booking_request": "legacy booking anchor",
        "recent_caller_statements": ["Book an appointment October 20", "October 20"],
        "caller_name": "Asha",
        "caller_phone": "+15550100000",
        "caller_phone_digits": "5550100000",
        "caller_phone_confirmation_pending": True,
    }


def _booking_arguments():
    return {
        "customer_name": "Asha",
        "customer_phone": "+15550100000",
        "start_time": "2035-10-20T10:00:00+05:30",
        "confirmed_by_caller": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,should_clear",
    [
        ({"booked": True, "appointment_id": "saved-1", "start_time": "2035-10-20T10:00:00+05:30"}, True),
        ({"booked": False, "status": "conflict", "error": "unavailable"}, False),
    ],
)
async def test_pipecat_booking_handler_cleans_only_after_persisted_success(
    monkeypatch, result, should_clear
):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
    from api.services.workflow.tools import booking

    state = _staged_state()
    messages = [
        {"role": "assistant", "content": "October 20 at 10 AM. Should I book the appointment?"},
        {"role": "user", "id": "confirm", "content": "Yes"},
    ]
    engine = NS(
        active_agent=NS(user_config=None),
        _get_organization_id=AsyncMock(return_value=7),
        context=NS(get_messages=lambda: messages),
        _contact_conversation_state=state,
        _call_context_vars={},
        _is_realtime=True,
    )
    execute = AsyncMock(return_value=result)
    monkeypatch.setattr(booking, "execute_booking", execute)
    callback = AsyncMock()

    await CustomToolManager(engine)._create_booking_handler()(NS(
        arguments=_booking_arguments(), result_callback=callback
    ))

    assert callback.await_count == 1
    staged_keys = {
        "booking_confirmation_slot", "booking_time_question_date",
        "prior_booking_request", "active_booking_request", "recent_caller_statements",
    }
    if should_clear:
        assert not staged_keys.intersection(state)
        assert state["_completed_booking_turn_boundary"]["identities"][0] == {
            "kind": "id", "value": "confirm"
        }
    else:
        assert all(key in state for key in staged_keys)
        assert "_completed_booking_turn_boundary" not in state
    assert state["caller_name"] == "Asha"
    assert state["caller_phone"] == "+15550100000"
    assert state["caller_phone_digits"] == "5550100000"
    assert state["caller_phone_confirmation_pending"] is True


class _FakeContext:
    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self.tools = NS(standard_tools=[NS(name="book_appointment")])

    def set_messages(self, messages):
        self._messages = list(messages)

    def get_messages(self):
        return self._messages

    def add_message(self, message):
        self._messages.append(message)


class _FakeTask:
    def __init__(self):
        self.queue_frame = AsyncMock()

    def event_handler(self, _event):
        return lambda function: function

    def has_finished(self):
        return True


class _FakeGraph:
    start_node_id = "start"
    nodes = {}

    def __init__(self, *_args, **_kwargs):
        pass

    def uses_variable_extraction(self):
        return False


class _FakeEngine:
    def __init__(self, **kwargs):
        self.context = kwargs["context"]
        self.workflow = kwargs["workflow"]
        self.active_agent = NS(user_config=None, current_node=NS(id="node"))
        self.call_monitor = NS(activate=lambda: None)
        self._contact_conversation_state = {}
        self._gathered_context = {}

    async def initialize(self):
        pass

    async def set_node(self, *_args, **_kwargs):
        pass

    async def queue_node_opening(self, **_kwargs):
        return NS(action="none")

    def set_audio_config(self, _config):
        pass

    def set_transport_output(self, _output):
        pass

    def set_fetch_recording_audio(self, _fetcher):
        pass

    async def close_mcp_sessions(self):
        pass

    async def cleanup(self):
        pass

    async def get_gathered_context(self):
        return self._gathered_context

    def is_call_disposed(self):
        return False


class _FakeCapture:
    def __init__(self, response_window, context, engine):
        self.events = []
        self.activity_count = 0
        self.completed_llm_text = []

    def _append_event(self, event_type, payload):
        self.events.append({"type": event_type, "payload": payload})


class _FakeAggregator:
    def __init__(self, *_args, **_kwargs):
        pass

    def assistant(self):
        return NS(event_handler=lambda _event: lambda function: function)


class _FakeMetrics:
    def get_all_usage_metrics_serialized(self):
        return {}


class _FakePipeline:
    def __init__(self, *_args, **_kwargs):
        pass


class _FakeLLM:
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,should_clear",
    [
        ({"booked": True, "appointment_id": "saved-1", "start_time": "2035-10-20T10:00:00+05:30"}, True),
        ({"booked": False, "status": "conflict", "error": "unavailable"}, False),
    ],
)
async def test_text_chat_execution_cleans_only_after_persisted_success(
    monkeypatch, result, should_clear
):
    from api.services.configuration import ai_model_configuration
    from api.services.workflow import contact_context, text_chat_runner as runner
    from api.services.workflow.tools import booking

    state = _staged_state()
    context_messages = [
        {"role": "assistant", "content": "October 20 at 10 AM. Should I book the appointment?"},
    ]
    workflow = NS(
        organization_id=7,
        workflow_configurations={},
        name="test-workflow",
    )
    definition = NS(workflow_configurations={}, workflow_json={"nodes": [], "edges": []})
    run = NS(
        workflow_id=11,
        definition=definition,
        workflow=NS(organization_id=7, user=NS()),
        initial_context={},
        name="test-run",
    )
    monkeypatch.setattr(runner.db_client, "get_workflow_run_with_context", AsyncMock(return_value=(run, None)))
    monkeypatch.setattr(runner.db_client, "get_workflow", AsyncMock(return_value=workflow))
    monkeypatch.setattr(runner.db_client, "update_workflow_run", AsyncMock())
    monkeypatch.setattr(runner.db_client, "has_active_recordings", AsyncMock(return_value=False))
    monkeypatch.setattr(
        ai_model_configuration,
        "get_effective_ai_model_configuration_for_workflow",
        AsyncMock(return_value=NS(llm=NS(provider="ollama", model="test"), embeddings=None)),
    )
    monkeypatch.setattr(
        "api.services.managed_model_services.ensure_mps_correlation_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(runner, "WorkflowGraph", _FakeGraph)
    monkeypatch.setattr(runner, "PipecatEngine", _FakeEngine)
    monkeypatch.setattr(runner, "LLMContext", _FakeContext)
    monkeypatch.setattr(runner, "_deserialize_text_chat_checkpoint_messages", lambda messages: list(messages))
    monkeypatch.setattr(runner, "_serialize_text_chat_checkpoint_messages", lambda messages: list(messages))
    monkeypatch.setattr(runner, "LLMContextAggregatorPair", _FakeAggregator)
    monkeypatch.setattr(runner, "LLMAssistantAggregatorParams", lambda: None)
    monkeypatch.setattr(runner, "Pipeline", _FakePipeline)
    monkeypatch.setattr(runner, "PipelineMetricsAggregator", _FakeMetrics)
    monkeypatch.setattr(runner, "_TextChatCaptureProcessor", _FakeCapture)
    monkeypatch.setattr(runner, "create_llm_service", lambda *_args, **_kwargs: _FakeLLM())
    monkeypatch.setattr(runner, "create_pipeline_task", lambda *_args, **_kwargs: _FakeTask())
    monkeypatch.setattr(runner, "run_pipeline_worker", AsyncMock())
    monkeypatch.setattr(runner, "wait_for_pipeline_worker_started", AsyncMock())
    monkeypatch.setattr(runner, "create_audio_config", lambda *_args, **_kwargs: NS(pipeline_sample_rate=16000))
    monkeypatch.setattr(runner, "create_recording_audio_fetcher", lambda **_kwargs: None)
    monkeypatch.setattr(runner, "build_remote_parent_context", lambda *_args: None)
    monkeypatch.setattr(runner, "guard_booking_reply", lambda reply, _events, **_kwargs: reply)
    monkeypatch.setattr(runner, "get_trace_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runner, "set_current_org_id", lambda _org_id: None)
    monkeypatch.setattr(contact_context, "booking_contact_question", lambda *_args: None)
    monkeypatch.setattr(contact_context, "caller_name_followup_reply", lambda *_args: None)
    monkeypatch.setattr(contact_context, "caller_phone_fragment_reply", lambda *_args: None)
    monkeypatch.setattr(contact_context, "remember_explicit_caller_name", lambda *_args: None)
    monkeypatch.setattr(
        contact_context,
        "confirmed_staged_booking_arguments",
        lambda *_args: _booking_arguments(),
    )
    monkeypatch.setattr(booking, "execute_booking", AsyncMock(return_value=result))

    checkpoint = {
        "messages": context_messages,
        "current_node_id": "node",
        "gathered_context": {},
        "contact_conversation_state": state,
        "tool_state": {},
    }
    session_data = {
        "turns": [{
            "id": "turn-1",
            "status": "pending",
            "user_message": {"text": "Yes"},
        }]
    }
    output = await runner.execute_text_chat_pending_turn(
        workflow_run_id=21,
        workflow_id=11,
        session_data=session_data,
        checkpoint=checkpoint,
    )

    result_state = output.checkpoint["contact_conversation_state"]
    staged_keys = {
        "booking_confirmation_slot", "booking_time_question_date",
        "prior_booking_request", "active_booking_request", "recent_caller_statements",
    }
    if should_clear:
        assert not staged_keys.intersection(result_state)
        assert result_state["_completed_booking_turn_boundary"]["identities"][0] == {
            "kind": "context", "assistant": context_messages[0]["content"], "text": "Yes"
        }
    else:
        assert all(key in result_state for key in staged_keys)
        assert "_completed_booking_turn_boundary" not in result_state
    assert result_state["caller_name"] == "Asha"
    assert result_state["caller_phone"] == "+15550100000"
    assert result_state["caller_phone_digits"] == "5550100000"
    assert result_state["caller_phone_confirmation_pending"] is True
