from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.db.kodewaves_client import kodewaves_db_client
from api.services import saas_entitlements
from api.services.gen_ai.embedding import factory


@pytest.mark.asyncio
@pytest.mark.parametrize("policy_allowed,plan_allowed", [(False, True), (True, False)])
@pytest.mark.parametrize("key", ["synthetic-user-key", "default"])
async def test_external_embedding_key_is_denied_before_constructing_provider(
    monkeypatch, policy_allowed, plan_allowed, key,
):
    monkeypatch.setattr(kodewaves_db_client, "get_setting", AsyncMock(return_value={"allow_user_byok": policy_allowed}))
    plan_check = AsyncMock(return_value=plan_allowed)
    monkeypatch.setattr(saas_entitlements, "is_saas_feature_allowed", plan_check)
    constructor = Mock()
    monkeypatch.setattr(factory, "OpenAIEmbeddingService", constructor)

    with pytest.raises(HTTPException) as error:
        await factory.build_embedding_service(
            db_client=None, organization_id=42, provider="openai",
            api_key=key, model="text-embedding-3-small",
        )

    assert error.value.status_code == 403
    constructor.assert_not_called()
    if policy_allowed:
        plan_check.assert_awaited_once_with(42, "byok")


@pytest.mark.asyncio
async def test_external_embedding_key_is_allowed_for_entitled_workspace(monkeypatch):
    monkeypatch.setattr(kodewaves_db_client, "get_setting", AsyncMock(return_value={"allow_user_byok": True}))
    monkeypatch.setattr(saas_entitlements, "is_saas_feature_allowed", AsyncMock(return_value=True))
    service = object()
    constructor = Mock(return_value=service)
    monkeypatch.setattr(factory, "OpenAIEmbeddingService", constructor)

    result = await factory.build_embedding_service(
        db_client=None, organization_id=42, provider="openai",
        api_key="synthetic-user-key", model="text-embedding-3-small",
    )

    assert result is service
    constructor.assert_called_once()


@pytest.mark.asyncio
async def test_managed_embedding_service_key_is_not_treated_as_byok(monkeypatch):
    policy = AsyncMock(side_effect=AssertionError("managed embeddings do not use BYOK policy"))
    monkeypatch.setattr(kodewaves_db_client, "get_setting", policy)
    service = object()
    monkeypatch.setattr(factory, "KodewavesEmbeddingService", Mock(return_value=service))

    result = await factory.build_embedding_service(
        db_client=None, organization_id=42, provider="kodewaves",
        api_key="synthetic-managed-key", model="kodewaves_embedding_v1",
    )

    assert result is service
    policy.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_embedding_key_requires_workspace(monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(factory, "OpenAIEmbeddingService", constructor)
    with pytest.raises(HTTPException) as error:
        await factory.build_embedding_service(
            db_client=None, organization_id=None, provider="openai",
            api_key="synthetic-user-key", model="text-embedding-3-small",
        )
    assert error.value.status_code == 403
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_external_embedding_key_fails_closed_when_policy_lookup_fails(monkeypatch):
    policy = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(kodewaves_db_client, "get_setting", policy)
    constructor = Mock()
    monkeypatch.setattr(factory, "OpenAIEmbeddingService", constructor)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await factory.build_embedding_service(
            db_client=None, organization_id=42, provider="openai",
            api_key="synthetic-user-key", model="text-embedding-3-small",
        )

    policy.assert_awaited_once_with("byok_policy", raise_on_error=True)
    constructor.assert_not_called()


@pytest.mark.asyncio
async def test_manual_search_preserves_entitlement_denial(monkeypatch):
    from api.routes import knowledge_base
    from api.services import gen_ai
    from api.services.configuration import ai_model_configuration

    embeddings = SimpleNamespace(
        provider="openai", api_key="synthetic-user-key", model="text-embedding-3-small",
        endpoint=None, base_url=None, api_version=None,
    )
    monkeypatch.setattr(
        ai_model_configuration, "get_resolved_ai_model_configuration",
        AsyncMock(return_value=SimpleNamespace(effective=SimpleNamespace(embeddings=embeddings))),
    )
    builder = AsyncMock(side_effect=HTTPException(status_code=403, detail="BYOK disabled"))
    monkeypatch.setattr(gen_ai, "build_embedding_service", builder)

    with pytest.raises(HTTPException) as error:
        await knowledge_base.search_chunks(SimpleNamespace(), SimpleNamespace(selected_organization_id=42))

    assert error.value.status_code == 403
    assert builder.await_args.kwargs["organization_id"] == 42


@pytest.mark.asyncio
async def test_denied_ingestion_does_not_send_document_for_conversion(monkeypatch):
    from pathlib import Path
    from api.services.configuration import ai_model_configuration
    from api.tasks import knowledge_base_processing as task

    document = SimpleNamespace(id=7, organization_id=42, custom_metadata={"s3_key": "docs/file.pdf"})
    monkeypatch.setattr(task, "require_client_worker_features", AsyncMock())
    monkeypatch.setattr(task.db_client, "get_document_by_id", AsyncMock(return_value=document))
    monkeypatch.setattr(task.db_client, "get_document_by_hash", AsyncMock(return_value=None))
    monkeypatch.setattr(task.db_client, "update_document_status", AsyncMock())
    monkeypatch.setattr(task.db_client, "update_document_metadata", AsyncMock())
    monkeypatch.setattr(task.db_client, "compute_file_hash", Mock(return_value="test-hash"))
    monkeypatch.setattr(task.db_client, "get_mime_type", Mock(return_value="application/pdf"))

    async def download(_key, path):
        Path(path).write_bytes(b"test content")
        return True

    monkeypatch.setattr(task.storage_fs, "adownload_file", download)
    embeddings = SimpleNamespace(
        provider="openai", api_key="synthetic-user-key", model="text-embedding-3-small",
        endpoint=None, base_url=None, api_version=None,
    )
    monkeypatch.setattr(
        ai_model_configuration, "get_resolved_ai_model_configuration",
        AsyncMock(return_value=SimpleNamespace(effective=SimpleNamespace(embeddings=embeddings))),
    )
    builder = AsyncMock(side_effect=HTTPException(status_code=403, detail="BYOK disabled"))
    monkeypatch.setattr(task, "build_embedding_service", builder)
    conversion = AsyncMock()
    monkeypatch.setattr(task.mps_service_key_client, "process_document", conversion)

    with pytest.raises(HTTPException) as error:
        await task.process_knowledge_base_document(None, 7, "docs/file.pdf", 42, "user-1")

    assert error.value.status_code == 403
    assert builder.await_args.kwargs["organization_id"] == 42
    conversion.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_retrieval_supplies_workspace_to_embedding_policy(monkeypatch):
    from api.services.workflow.tools import knowledge_base

    service = SimpleNamespace(search_similar_chunks=AsyncMock(return_value=[]))
    builder = AsyncMock(return_value=service)
    monkeypatch.setattr(knowledge_base, "build_embedding_service", builder)

    result = await knowledge_base._perform_retrieval(
        query="opening hours", organization_id=42, document_uuids=None, limit=3,
        embeddings_api_key="synthetic-user-key", embeddings_provider="openai",
    )

    assert result["total_results"] == 0
    assert builder.await_args.kwargs["organization_id"] == 42
