from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.kodewaves_client import kodewaves_db_client
from api.services.workflow_run_billing import build_runtime_billing_context, report_workflow_run_platform_usage


def runtime(llm="local", stt="local", tts="local"):
    return {"resolution_info": {
        "llm": {"source": llm}, "stt": {"source": stt}, "tts": {"source": tts},
    }}


def call(context):
    return SimpleNamespace(
        id=990001, mode="webrtc", is_completed=True,
        initial_context={"is_local": True, "is_admin_test": True, "mode": "s2s", "resolution_info": {"overall_source": "local"}},
        gathered_context={"is_local": True},
        workflow=SimpleNamespace(organization_id=99),
        usage_info={"call_duration_seconds": 60.1, "runtime_billing_context": context},
    )


@pytest.mark.asyncio
async def test_local_and_byok_model_usage_does_not_drain_platform_wallet(monkeypatch):
    deduct = AsyncMock()
    monkeypatch.setattr(kodewaves_db_client, "deduct_minutes", deduct)
    context = build_runtime_billing_context([runtime(tts="user_key")])
    await report_workflow_run_platform_usage(call(context))
    deduct.assert_not_awaited()


@pytest.mark.asyncio
async def test_cloud_handoff_is_billed_despite_caller_free_flags(monkeypatch):
    deduct = AsyncMock()
    monkeypatch.setattr(kodewaves_db_client, "deduct_minutes", deduct)
    context = build_runtime_billing_context([runtime(), runtime(llm="master_key")])
    await report_workflow_run_platform_usage(call(context))
    deduct.assert_awaited_once_with(organization_id=99, minutes=2, reason="call_usage", reference_id="990001")


@pytest.mark.asyncio
async def test_missing_runtime_attribution_cannot_be_spoofed_as_free(monkeypatch):
    deduct = AsyncMock()
    monkeypatch.setattr(kodewaves_db_client, "deduct_minutes", deduct)
    await report_workflow_run_platform_usage(call({}))
    deduct.assert_awaited_once()


def test_unused_child_recognition_does_not_make_local_call_billable():
    context = build_runtime_billing_context([runtime(), runtime(stt="master_key")])
    assert context["sources"] == ["local"]


def test_realtime_excludes_unused_speech_layers():
    context = build_runtime_billing_context([{
        "is_realtime": True, "resolution_info": {
            "llm": {"source": "user_key"}, "realtime": {"source": "master_key"},
        },
    }])
    assert context == {"version": 1, "sources": ["master_key", "user_key"], "is_realtime": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("source,allowed", [("local", True), ("master_key", False)])
async def test_zero_wallet_uses_resolved_source_instead_of_any_local_layer(monkeypatch, source, allowed):
    from api.services import quota_service

    workflow = SimpleNamespace(id=1, user_id=7, organization_id=99, workflow_configurations={})
    monkeypatch.setattr(quota_service.db_client, "get_workflow", AsyncMock(return_value=workflow))
    monkeypatch.setattr(quota_service.db_client, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7)))
    config = SimpleNamespace(
        llm=SimpleNamespace(provider="openai", api_key="sovereign-local-cpu"),
        resolution_info={"overall_source": source},
    )
    monkeypatch.setattr(quota_service, "get_effective_ai_model_configuration_for_workflow", AsyncMock(return_value=config))
    monkeypatch.setattr(kodewaves_db_client, "get_or_create_wallet", AsyncMock(return_value=SimpleNamespace(credit_balance_minutes=0, bonus_minutes=0)))
    result = await quota_service.authorize_workflow_run_start(workflow_id=1, organization_id=99)
    assert result.has_quota is allowed


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["local", "user_key", "master_key"])
async def test_frozen_wallet_blocks_new_runs_even_with_credit(monkeypatch, source):
    from api.services import quota_service

    workflow = SimpleNamespace(id=1, user_id=7, organization_id=99, workflow_configurations={})
    monkeypatch.setattr(quota_service.db_client, "get_workflow", AsyncMock(return_value=workflow))
    monkeypatch.setattr(quota_service.db_client, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7)))
    monkeypatch.setattr(
        quota_service, "get_effective_ai_model_configuration_for_workflow",
        AsyncMock(return_value=SimpleNamespace(resolution_info={"overall_source": source})),
    )
    monkeypatch.setattr(
        kodewaves_db_client, "get_or_create_wallet",
        AsyncMock(return_value=SimpleNamespace(is_frozen=True, credit_balance_minutes=100, bonus_minutes=10)),
    )
    result = await quota_service.authorize_workflow_run_start(workflow_id=1, organization_id=99)
    assert result.has_quota is False
    assert result.error_code == "wallet_frozen"
