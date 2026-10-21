from types import SimpleNamespace

import pytest

from api.tests import test_call_recording_upload_flag as completion_helpers
from api.services.pipecat import event_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize("child_source,expected", [(None, ["local"]), ("master_key", ["local", "master_key"])])
async def test_call_completion_persists_runtime_sources(monkeypatch, child_source, expected):
    original_namespace = SimpleNamespace

    def namespace(**kwargs):
        if "get_gathered_context" in kwargs and "cleanup" in kwargs:
            visits = [{"runtime_configuration": {"resolution_info": {
                layer: {"source": "local"} for layer in ("llm", "stt", "tts")
            }}}]
            if child_source:
                visits.append({"runtime_configuration": {"resolution_info": {
                    "llm": {"source": child_source}, "tts": {"source": "local"},
                }}})
            kwargs["agent_visits"] = visits
        return original_namespace(**kwargs)

    monkeypatch.setattr(completion_helpers, "SimpleNamespace", namespace)
    await completion_helpers._run_pipeline_finished(
        monkeypatch, recording_upload_enabled=False,
        gathered_context={"is_local": True, "is_admin_test": True},
    )
    writes = event_handlers.db_client.update_workflow_run.await_args_list
    usage_writes = [write.kwargs["usage_info"] for write in writes if "usage_info" in write.kwargs]
    assert len(usage_writes) == 1
    assert usage_writes[0]["runtime_billing_context"]["sources"] == expected
