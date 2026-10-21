from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.enums import CallType
from api.routes.workflow import router
from api.services.auth.depends import get_user
from api.services.configuration.registry import ServiceProviders


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=1,
        provider_id="provider-1",
        selected_organization_id=11,
    )
    return app


@pytest.mark.asyncio
async def test_generated_booking_graph_attaches_existing_calendar_tool():
    from api.routes import workflow

    definition = {
        "nodes": [
            {"id": "start", "type": "startCall", "data": {"prompt": "Hello"}},
            {"id": "details", "type": "agentNode", "data": {"prompt": "Ask for a time"}},
            {"id": "end", "type": "endCall", "data": {"prompt": "Goodbye"}},
        ],
        "edges": [{"source": "details", "target": "end", "data": {"condition": "Done"}}],
    }
    existing = SimpleNamespace(tool_uuid="booking-1", name="Book Appointment")
    with patch.object(
        workflow.db_client, "get_tools_for_organization", AsyncMock(return_value=[existing])
    ) as lookup:
        result = await workflow._attach_generated_booking_tool(
            definition, SimpleNamespace(selected_organization_id=11), "Appointment booking assistant"
        )
    lookup.assert_awaited_once()
    assert result["nodes"][1]["data"]["tool_uuids"] == ["booking-1"]
    assert "call book_appointment" in result["nodes"][1]["data"]["prompt"]
    assert "booked=true" in result["edges"][0]["data"]["condition"]
    assert result["nodes"][0]["data"]["tool_uuids"] == ["booking-1"]


@pytest.mark.asyncio
async def test_generated_booking_graph_creates_calendar_tool_when_missing():
    from api.routes import workflow

    definition = {"nodes": [{"id": "details", "type": "agentNode", "data": {"prompt": "Ask for a time"}}], "edges": []}
    created = SimpleNamespace(tool_uuid="new-booking", name="Book Appointment")
    user = SimpleNamespace(id=5, provider_id="provider-5", selected_organization_id=11)
    with (
        patch.object(workflow.db_client, "get_tools_for_organization", AsyncMock(return_value=[])),
        patch("api.services.tool_management.create_tool_for_user", AsyncMock(return_value=created)) as create,
    ):
        result = await workflow._attach_generated_booking_tool(definition, user, "Book an appointment")
    assert create.await_args.args[0].definition.type == "book_appointment"
    assert create.await_args.kwargs["source"] == "workflow_generator"
    assert result["nodes"][0]["data"]["tool_uuids"] == ["new-booking"]


def test_generated_voice_workflow_uses_selected_model_and_rejects_repetitive_output():
    from api.services.workflow import generation

    config = SimpleNamespace(
        llm=SimpleNamespace(
            provider=ServiceProviders.OPENAI,
            api_key="local-key",
            model="qwen2.5:1.5b",
        ),
        tts=SimpleNamespace(provider="speaches", voice="hi_IN-pratham-medium", language=None),
        stt=SimpleNamespace(language="multi"),
    )

    class FakeLLM:
        async def run_inference(self, context, **kwargs):
            return (
                '{"greeting":{"prompt":"Greet the caller in Hindi",'
                '"completion_condition":"The caller states the appointment need"},'
                '"steps":[{"name":"Appointment details",'
                '"prompt":"नमस्ते, कृपया अपनी पसंद की तारीख और समय बताइए।",'
                '"completion_condition":"The caller provides and confirms a date and time"}],'
                '"closing":{"prompt":"धन्यवाद, आपका दिन शुभ हो।"}}'
            )

        async def cleanup(self):
            pass

    with (
        patch.object(generation, "get_effective_ai_model_configuration_for_workflow", AsyncMock(return_value=config)),
        patch.object(generation, "create_llm_service", return_value=FakeLLM()),
        patch.object(generation, "resolve_agent_speech_language", return_value=None),
    ):
        result, provider, model = __import__("asyncio").run(
            generation.generate_voice_workflow(11, "Appointment Agent", "Confirm a date and time")
        )

    assert provider == ServiceProviders.OPENAI
    assert model == "qwen2.5:1.5b"
    assert [node["type"] for node in result["nodes"]] == ["startCall", "agentNode", "endCall"]


def test_generated_voice_workflow_recovers_from_repetitive_local_model_output():
    from api.services.workflow import generation

    config = SimpleNamespace(
        llm=SimpleNamespace(provider=ServiceProviders.OPENAI, api_key="local-key", model="qwen2.5:1.5b"),
        tts=SimpleNamespace(provider="speaches", voice="hi_IN-pratham-medium", language=None),
        stt=SimpleNamespace(language="multi"),
    )

    class BadLLM:
        async def run_inference(self, context, **kwargs):
            return (
                '{"greeting":{"prompt":"नमस्ते कृपया बताएं","completion_condition":"Caller replies"},'
                '"steps":[{"prompt":"आपकी जरूरत की जरूरत की जरूरत की जरूरत की जरूरत है",'
                '"completion_condition":"Caller confirms"}],"closing":{"prompt":"धन्यवाद"}}'
            )

        async def cleanup(self):
            pass

    with (
        patch.object(generation, "get_effective_ai_model_configuration_for_workflow", AsyncMock(return_value=config)),
        patch.object(generation, "create_llm_service", return_value=BadLLM()),
        patch.object(generation, "resolve_agent_speech_language", return_value="hi"),
    ):
        result, _, _ = __import__("asyncio").run(
            generation.generate_voice_workflow(11, "Appointment Agent", "Confirm a date and time")
        )
    assert [node["type"] for node in result["nodes"]] == ["startCall", "endCall"]
    assert "Confirm a date and time" in result["nodes"][0]["data"]["prompt"]
    assert len(result["edges"]) == 1
    assert result["edges"][0]["data"]["label"] == "finish_assistance"


def test_create_workflow_rejects_invalid_trigger_path_before_db_write():
    app = _make_test_app()
    client = TestClient(app)

    with patch("api.routes.workflow.db_client") as mock_db:
        response = client.post(
            "/workflow/create/definition",
            json={
                "name": "Support Agent",
                "workflow_definition": {
                    "nodes": [
                        {
                            "id": "trigger-1",
                            "type": "trigger",
                            "data": {"trigger_path": "support/west"},
                        }
                    ],
                    "edges": [],
                },
            },
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["is_valid"] is False
    assert detail["errors"][0]["field"] == "data.trigger_path"
    assert "single URL path segment" in detail["errors"][0]["message"]
    assert mock_db.mock_calls == []


def test_create_workflow_rejects_duplicate_api_triggers_before_db_write():
    app = _make_test_app()
    client = TestClient(app)

    with patch("api.routes.workflow.db_client") as mock_db:
        response = client.post(
            "/workflow/create/definition",
            json={
                "name": "Support Agent",
                "workflow_definition": {
                    "nodes": [
                        {
                            "id": "trigger-1",
                            "type": "trigger",
                            "data": {"trigger_path": "support_west"},
                        },
                        {
                            "id": "trigger-2",
                            "type": "trigger",
                            "data": {"trigger_path": "support_east"},
                        },
                    ],
                    "edges": [],
                },
            },
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["is_valid"] is False
    assert detail["errors"][0]["kind"] == "workflow"
    assert "at most one API Trigger" in detail["errors"][0]["message"]
    assert mock_db.mock_calls == []


def test_update_workflow_rejects_duplicate_transition_tools_before_db_write():
    app = _make_test_app()
    client = TestClient(app)

    with patch("api.routes.workflow.db_client") as mock_db:
        response = client.put(
            "/workflow/33",
            json={
                "workflow_definition": {
                    "nodes": [],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source": "agent-1",
                            "target": "end-1",
                            "data": {
                                "label": "Go to sales",
                                "condition": "Caller wants sales.",
                            },
                        },
                        {
                            "id": "edge-2",
                            "source": "agent-1",
                            "target": "end-2",
                            "data": {
                                "label": "go-to-sales",
                                "condition": "Caller asks for sales.",
                            },
                        },
                    ],
                }
            },
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["is_valid"] is False
    assert {error["id"] for error in detail["errors"]} == {"edge-1", "edge-2"}
    assert all(error["kind"] == "edge" for error in detail["errors"])
    assert all(error["field"] == "data.label" for error in detail["errors"])
    assert all(
        'Transition tool name "go_to_sales" is duplicated' in error["message"]
        for error in detail["errors"]
    )
    assert mock_db.mock_calls == []


def test_update_workflow_rejects_transition_custom_tool_collision_before_db_write():
    app = _make_test_app()
    client = TestClient(app)
    tool = SimpleNamespace(
        tool_uuid="tool-uuid-1",
        name="Transfer Callback",
        category="transfer_call",
    )

    with (
        patch("api.routes.workflow.db_client") as mock_db,
        patch(
            "api.services.workflow.tool_name_validation.db_client.get_tools_by_uuids",
            AsyncMock(return_value=[tool]),
        ) as get_tools_mock,
    ):
        response = client.put(
            "/workflow/33",
            json={
                "workflow_definition": {
                    "nodes": [
                        {
                            "id": "agent-1",
                            "type": "agentNode",
                            "data": {
                                "name": "Agent",
                                "tool_uuids": ["tool-uuid-1"],
                            },
                        }
                    ],
                    "edges": [
                        {
                            "id": "edge-1",
                            "source": "agent-1",
                            "target": "end-1",
                            "data": {
                                "label": "transfer callback",
                                "condition": "Caller requested a callback.",
                            },
                        }
                    ],
                }
            },
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["is_valid"] is False
    assert detail["errors"] == [
        {
            "kind": "edge",
            "id": "edge-1",
            "field": "data.label",
            "message": (
                'Transition tool name "transfer_callback" conflicts with custom '
                'tool "Transfer Callback" attached to this node. Use a unique '
                "edge label or rename the custom tool."
            ),
        }
    ]
    get_tools_mock.assert_awaited_once_with(["tool-uuid-1"], 11)
    assert mock_db.mock_calls == []


def test_create_workflow_run_uses_draft_and_template_context():
    app = _make_test_app()
    client = TestClient(app)

    workflow = SimpleNamespace(
        id=33,
        released_definition=SimpleNamespace(
            id=77,
            template_context_variables={"name": "published"},
        ),
        current_definition=None,
        template_context_variables={"name": "workflow"},
    )
    draft = SimpleNamespace(
        id=88,
        template_context_variables={"name": "draft", "draft_only": "kept"},
    )
    run = SimpleNamespace(
        id=501,
        workflow_id=workflow.id,
        name="WR-test",
        mode="smallwebrtc",
        created_at=datetime.now(UTC),
        definition_id=draft.id,
        initial_context={"name": "draft", "draft_only": "kept"},
        gathered_context={},
    )

    with patch("api.routes.workflow.db_client") as mock_db:
        mock_db.get_workflow = AsyncMock(return_value=workflow)
        mock_db.get_draft_version = AsyncMock(return_value=draft)
        mock_db.create_workflow_run = AsyncMock(return_value=run)

        response = client.post(
            f"/workflow/{workflow.id}/runs",
            json={"name": "WR-test", "mode": "smallwebrtc"},
        )

    assert response.status_code == 200
    mock_db.get_draft_version.assert_awaited_once_with(workflow.id)
    create_kwargs = mock_db.create_workflow_run.await_args.kwargs
    assert create_kwargs["definition_id"] == draft.id
    assert create_kwargs["initial_context"] == {
        "name": "draft",
        "draft_only": "kept",
        "direction": "inbound",
    }
    assert create_kwargs["call_type"] == CallType.INBOUND


def test_create_workflow_webrtc_run_can_simulate_outbound_from_template_context():
    app = _make_test_app()
    client = TestClient(app)

    workflow = SimpleNamespace(id=33, current_definition=None)
    draft = SimpleNamespace(
        id=88,
        template_context_variables={"direction": " OUTBOUND "},
    )
    run = SimpleNamespace(
        id=501,
        workflow_id=workflow.id,
        name="WR-test",
        mode="smallwebrtc",
        created_at=datetime.now(UTC),
        definition_id=draft.id,
        initial_context={"direction": "outbound"},
        gathered_context={},
    )

    with patch("api.routes.workflow.db_client") as mock_db:
        mock_db.get_workflow = AsyncMock(return_value=workflow)
        mock_db.get_draft_version = AsyncMock(return_value=draft)
        mock_db.create_workflow_run = AsyncMock(return_value=run)

        response = client.post(
            f"/workflow/{workflow.id}/runs",
            json={"name": "WR-test", "mode": "smallwebrtc"},
        )

    assert response.status_code == 200
    create_kwargs = mock_db.create_workflow_run.await_args.kwargs
    assert create_kwargs["call_type"] == CallType.OUTBOUND
    assert create_kwargs["initial_context"]["direction"] == "outbound"
