from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.schemas.ai_model_configuration import (
    EffectiveAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
)
from api.services.configuration.ai_model_configuration import (
    WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY,
    _decrypt_model_configuration_secrets,
    compile_ai_model_configuration_v2,
    get_effective_ai_model_configuration_for_workflow,
    migrate_workflow_model_configurations_to_v2,
)
from api.services.configuration.masking import mask_workflow_configurations
from api.services.configuration.model_configuration_secrets import (
    decrypt_workflow_model_configuration_secrets,
    encrypt_workflow_model_configuration_secrets,
)


def _byok_config() -> OrganizationAIModelConfigurationV2:
    return OrganizationAIModelConfigurationV2.model_validate(
        {
            "mode": "byok",
            "byok": {
                "mode": "pipeline",
                "pipeline": {
                    "llm": {"provider": "openai", "api_key": "org-llm-secret-1234", "model": "gpt-4.1"},
                    "tts": {"provider": "elevenlabs", "api_key": "org-tts-secret-5678", "model": "eleven_flash_v2_5", "voice": "Rachel"},
                    "stt": {"provider": "deepgram", "api_key": "org-stt-secret-9012", "model": "nova-3-general"},
                },
            },
        }
    )


def test_workflow_model_blocks_encrypt_and_mask_both_override_formats():
    v2 = _byok_config().model_dump(mode="json", exclude_none=True)
    legacy = {
        "llm": {"provider": "openai", "api_key": "legacy-llm-secret"},
        "tts": {"provider": "elevenlabs", "api_key": "legacy-tts-secret"},
        "stt": {"provider": "deepgram", "api_key": "legacy-stt-secret"},
    }
    source = {
        "model_configuration_v2_override": v2,
        "model_overrides": legacy,
        "unrelated_secret": "must-not-be-transformed",
    }

    encrypted = encrypt_workflow_model_configuration_secrets(source)
    assert "org-llm-secret-1234" not in str(encrypted)
    assert "legacy-llm-secret" not in str(encrypted)
    assert encrypted["unrelated_secret"] == "must-not-be-transformed"
    assert encrypted["model_overrides"]["llm"]["api_key"].startswith("fernet:v1:")

    masked = mask_workflow_configurations(encrypted)
    assert masked["model_configuration_v2_override"]["byok"]["pipeline"]["llm"]["api_key"].endswith("1234")
    assert masked["model_overrides"]["llm"]["api_key"].endswith("cret")
    assert "org-llm-secret-1234" not in str(masked)

    restored = decrypt_workflow_model_configuration_secrets(encrypted)
    assert restored["model_configuration_v2_override"] == v2
    assert restored["model_overrides"] == legacy


def test_invalid_ciphertext_fails_closed_instead_of_being_reencrypted():
    with pytest.raises(ValueError, match="cannot be decrypted"):
        encrypt_workflow_model_configuration_secrets(
            {
                "model_overrides": {
                    "llm": {"provider": "openai", "api_key": "fernet:v1:not-valid"}
                }
            }
        )


@pytest.mark.asyncio
async def test_workflow_runtime_decrypts_v2_override_before_compile():
    config = _byok_config().model_dump(mode="json", exclude_none=True)
    workflow_configurations = encrypt_workflow_model_configuration_secrets(
        {WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY: config}
    )

    effective = await get_effective_ai_model_configuration_for_workflow(
        organization_id=None,
        workflow_configurations=workflow_configurations,
    )

    assert effective.llm.api_key == "org-llm-secret-1234"
    assert effective.tts.api_key == "org-tts-secret-5678"
    assert effective.stt.api_key == "org-stt-secret-9012"


@pytest.mark.asyncio
async def test_workflow_legacy_override_backfill_encrypts_persisted_v2(monkeypatch):
    from api.services.configuration import ai_model_configuration

    base = EffectiveAIModelConfiguration(
        llm={"provider": "openai", "api_key": "base-llm", "model": "gpt-4.1"},
        tts={"provider": "elevenlabs", "api_key": "base-tts", "model": "eleven_flash_v2_5", "voice": "Rachel"},
        stt={"provider": "deepgram", "api_key": "base-stt", "model": "nova-3-general"},
    )
    workflow = SimpleNamespace(
        id=8,
        workflow_configurations=encrypt_workflow_model_configuration_secrets({
            "model_overrides": {"llm": {"api_key": "workflow-llm-secret"}}
        }),
        definitions=[],
    )
    bulk_update = AsyncMock()
    monkeypatch.setattr(
        ai_model_configuration.db_client,
        "list_workflows_for_model_configuration_migration",
        AsyncMock(return_value=[workflow]),
    )
    monkeypatch.setattr(
        ai_model_configuration.db_client,
        "bulk_update_workflow_model_configurations",
        bulk_update,
    )

    result = await migrate_workflow_model_configurations_to_v2(
        organization_id=42,
        fallback_user_config=base,
    )

    assert result.workflow_count == 1
    stored = bulk_update.await_args.kwargs["workflow_updates"][0][1]
    assert "workflow-llm-secret" not in str(stored)
    stored_override = stored[WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY]
    assert stored_override["byok"]["pipeline"]["llm"]["api_key"].startswith("fernet:v1:")
    assert _decrypt_model_configuration_secrets(stored_override)["byok"]["pipeline"]["llm"]["api_key"] == "workflow-llm-secret"


@pytest.mark.asyncio
async def test_existing_org_plaintext_keys_are_encrypted_on_read(monkeypatch):
    from datetime import UTC, datetime

    from api.services.configuration import ai_model_configuration

    config = _byok_config()
    plaintext = config.model_dump(mode="json", exclude_none=True)
    validated_at = datetime.now(UTC)
    saved = []

    async def get_configuration(_organization_id, _key):
        return SimpleNamespace(value=plaintext, last_validated_at=validated_at)

    async def upsert_configuration(organization_id, key, value, last_validated_at=None):
        saved.append((organization_id, key, value, last_validated_at))
        return SimpleNamespace(value=value, last_validated_at=last_validated_at)

    monkeypatch.setattr(ai_model_configuration.db_client, "get_configuration", get_configuration)
    monkeypatch.setattr(ai_model_configuration.db_client, "upsert_configuration", upsert_configuration)

    loaded = await ai_model_configuration.get_organization_ai_model_configuration_v2(42)

    assert loaded.byok.pipeline.llm.api_key == "org-llm-secret-1234"
    assert len(saved) == 1
    assert saved[0][:2] == (42, "MODEL_CONFIGURATION_V2")
    assert "org-llm-secret-1234" not in str(saved[0][2])
    assert saved[0][2]["byok"]["pipeline"]["llm"]["api_key"].startswith("fernet:v1:")
    assert saved[0][3] == validated_at


@pytest.mark.asyncio
async def test_migration_backfills_plaintext_keys_in_existing_v2_workflows(monkeypatch):
    from api.services.configuration import ai_model_configuration

    v2_override = _byok_config().model_dump(mode="json", exclude_none=True)
    workflow = SimpleNamespace(
        id=8,
        workflow_configurations={WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY: v2_override},
        definitions=[
            SimpleNamespace(
                id=80,
                workflow_configurations={WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY: v2_override},
            )
        ],
    )
    bulk_update = AsyncMock()
    monkeypatch.setattr(
        ai_model_configuration.db_client,
        "list_workflows_for_model_configuration_migration",
        AsyncMock(return_value=[workflow]),
    )
    monkeypatch.setattr(ai_model_configuration.db_client, "bulk_update_workflow_model_configurations", bulk_update)

    await migrate_workflow_model_configurations_to_v2(
        organization_id=42,
        fallback_user_config=EffectiveAIModelConfiguration(),
    )

    workflow_updates = bulk_update.await_args.kwargs["workflow_updates"]
    definition_updates = bulk_update.await_args.kwargs["definition_updates"]
    assert "org-llm-secret-1234" not in str(workflow_updates)
    assert "org-tts-secret-5678" not in str(definition_updates)
    assert workflow_updates[0][1][WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY]["byok"]["pipeline"]["llm"]["api_key"].startswith("fernet:v1:")
    assert definition_updates[0][1][WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY]["byok"]["pipeline"]["tts"]["api_key"].startswith("fernet:v1:")


@pytest.mark.parametrize("legacy_override", [False, True])
@pytest.mark.asyncio
async def test_workflow_update_encrypts_before_org_scoped_save_and_masks_response(
    monkeypatch, legacy_override
):
    from api.routes import workflow as workflow_routes

    config = _byok_config()
    raw_override = config.model_dump(mode="json", exclude_none=True)
    saved = {}
    draft = SimpleNamespace(
        id=12,
        version_number=2,
        status="draft",
        workflow_json={},
        workflow_configurations=None,
        template_context_variables=None,
        published_at=None,
        created_at=None,
    )
    stored_workflow = SimpleNamespace(
        id=4,
        name="Test agent",
        status="draft",
        created_at=None,
        current_definition_id=12,
        template_context_variables={},
        call_disposition_codes=[],
        released_definition=SimpleNamespace(workflow_configurations={}),
    )
    user = SimpleNamespace(id=9, provider_id="tenant-user", selected_organization_id=42)

    async def get_draft(_workflow_id):
        if saved:
            draft.workflow_configurations = saved["workflow_configurations"]
            return draft
        return None

    async def update(**kwargs):
        assert kwargs["organization_id"] == 42
        saved.update(kwargs)
        stored_workflow.name = kwargs["name"] or stored_workflow.name
        return stored_workflow

    class Valid:
        async def validate(self, *_args, **_kwargs):
            return {"status": [{"model": "all", "message": "ok"}]}

    monkeypatch.setattr(workflow_routes.db_client, "get_workflow", AsyncMock(return_value=stored_workflow))
    monkeypatch.setattr(workflow_routes.db_client, "get_draft_version", AsyncMock(side_effect=get_draft))
    monkeypatch.setattr(workflow_routes.db_client, "update_workflow", AsyncMock(side_effect=update))
    monkeypatch.setattr(
        workflow_routes,
        "get_resolved_ai_model_configuration",
        AsyncMock(return_value=SimpleNamespace(
            organization_configuration=config,
            effective=compile_ai_model_configuration_v2(config),
            source="organization_v2",
        )),
    )
    monkeypatch.setattr(workflow_routes, "apply_external_pbx_mapping_policy", AsyncMock(side_effect=lambda value, **_kwargs: value))
    monkeypatch.setattr(workflow_routes, "UserConfigurationValidator", Valid)

    if legacy_override:
        request_configs = {
            "model_overrides": {
                "llm": {
                    "provider": "openai",
                    "api_key": "workflow-llm-secret",
                    "model": "gpt-4.1",
                }
            }
        }
    else:
        request_configs = {WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY: raw_override}
    request = workflow_routes.UpdateWorkflowRequest(workflow_configurations=request_configs)
    response = await workflow_routes.update_workflow(4, request, user)

    persisted = saved["workflow_configurations"][WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY]
    serialized = str(saved["workflow_configurations"])
    assert "org-llm-secret-1234" not in serialized
    assert "org-tts-secret-5678" not in serialized
    assert "org-stt-secret-9012" not in serialized
    assert "workflow-llm-secret" not in serialized
    assert persisted["byok"]["pipeline"]["llm"]["api_key"].startswith("fernet:v1:")
    expected_suffix = "cret" if legacy_override else "1234"
    assert response["workflow_configurations"][WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY]["byok"]["pipeline"]["llm"]["api_key"].endswith(expected_suffix)


@pytest.mark.asyncio
async def test_duplicate_workflow_reencrypts_legacy_plaintext_model_keys(monkeypatch):
    from api.services.workflow import duplicate as duplicate_service

    source = SimpleNamespace(
        id=3,
        name="Source",
        released_definition=SimpleNamespace(
            workflow_json={},
            template_context_variables={},
            workflow_configurations={
                "model_overrides": {
                    "llm": {"provider": "openai", "api_key": "old-plaintext-key"}
                }
            },
        ),
    )
    created = SimpleNamespace(id=4)
    get_workflow = AsyncMock(side_effect=[source, created])
    update_workflow = AsyncMock(return_value=created)
    monkeypatch.setattr(duplicate_service.db_client, "get_workflow", get_workflow)
    monkeypatch.setattr(duplicate_service.db_client, "get_draft_version", AsyncMock(return_value=None))
    monkeypatch.setattr(duplicate_service.db_client, "create_workflow", AsyncMock(return_value=created))
    monkeypatch.setattr(duplicate_service.db_client, "update_workflow", update_workflow)

    await duplicate_service.duplicate_workflow(3, organization_id=42, user_id=9)

    saved = update_workflow.await_args.kwargs["workflow_configurations"]
    assert "old-plaintext-key" not in str(saved)
    assert saved["model_overrides"]["llm"]["api_key"].startswith("fernet:v1:")

