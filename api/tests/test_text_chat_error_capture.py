from types import SimpleNamespace as NS
from pipecat.frames.frames import ErrorFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from api.services.workflow.text_chat_runner import _TextChatCaptureProcessor, _ResponseWindowState


def test_rate_limit_is_a_visible_execution_event_without_vendor_blob():
    capture = _TextChatCaptureProcessor(_ResponseWindowState(), LLMContext(), NS())
    capture.record_pipeline_error(ErrorFrame(error="429 vendor quota debug", category="rate_limit"))
    assert capture.events[-1]["type"] == "execution_error"
    assert "provider quota" in capture.events[-1]["payload"]["message"]
    assert "vendor quota debug" not in capture.events[-1]["payload"]["message"]


def test_other_provider_errors_are_redacted_before_becoming_ui_events():
    capture = _TextChatCaptureProcessor(_ResponseWindowState(), LLMContext(), NS())
    capture.record_pipeline_error(ErrorFrame(error="Failed https://example.com?key=synthetic-secret"))
    message = capture.events[-1]["payload"]["message"]
    assert "synthetic-secret" not in message
    assert "REDACTED" in message
