"""The managed local STT Auto choice must survive API save and reload."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.models import UserModel
from api.routes import organization as organization_routes
from api.schemas.ai_model_configuration import (
    OrganizationAIModelConfigurationV2,
    compile_ai_model_configuration_v2,
)
from api.services.configuration import ai_model_configuration
from api.services.configuration.ai_model_configuration import ResolvedAIModelConfiguration


@pytest.mark.asyncio
async def test_local_stt_auto_selection_survives_v2_api_save_and_reload(monkeypatch):
    organization_id = 42
    user = UserModel(id=7, provider_id="auto-stt-test", selected_organization_id=organization_id)
    persisted: dict[str, object] = {}

    async def fake_upsert(org_id, key, value, last_validated_at=None):
        assert org_id == organization_id
        persisted["value"] = value
        persisted["key"] = key
        return SimpleNamespace(value=value, last_validated_at=last_validated_at)

    async def fake_get(org_id, key):
        assert org_id == organization_id
        if "value" not in persisted:
            return None
        return SimpleNamespace(value=persisted["value"], last_validated_at=None)

    monkeypatch.setattr(ai_model_configuration.db_client, "upsert_configuration", fake_upsert)
    monkeypatch.setattr(ai_model_configuration.db_client, "get_configuration", fake_get)
    monkeypatch.setattr(
        organization_routes,
        "get_organization_ai_model_configuration_v2",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        organization_routes.kodewaves_db_client,
        "get_setting",
        AsyncMock(return_value={"indic_stt_endpoint": "http://indic-stt:8000/v1"}),
    )
    monkeypatch.setattr(
        organization_routes.kodewaves_db_client,
        "set_setting",
        AsyncMock(),
    )

    async def fake_stt_inventory(_endpoint):
        return {
            "indicconformer-ctc-int8": {
                "id": "indicconformer-ctc-int8",
                "task": "automatic-speech-recognition",
                "installed": True,
                "supports_auto_detect": True,
                "languages": ["hi-IN", "en-IN", "ta-IN"],
                "auto_detect_languages": ["hi", "en", "ta"],
            }
        }

    monkeypatch.setattr(
        "api.services.catalog.local_inventory.get_local_stt_models",
        fake_stt_inventory,
    )

    async def fake_resolve(*, organization_id):
        stored = await ai_model_configuration.get_organization_ai_model_configuration_v2(organization_id)
        assert stored is not None
        return ResolvedAIModelConfiguration(
            effective=compile_ai_model_configuration_v2(stored),
            source="organization_v2",
            organization_configuration=stored,
        )

    monkeypatch.setattr(organization_routes, "get_resolved_ai_model_configuration", fake_resolve)

    request = OrganizationAIModelConfigurationV2.model_validate(
        {
            "version": 2,
            "mode": "kodewaves",
            "kodewaves": {
                "api_key": "sovereign-local-cpu",
                "language": "multi",
                "llm_engine_type": "local_cpu",
                "stt_engine_type": "local_cpu",
                "tts_engine_type": "local_cpu",
                "stt_model": "indicconformer-ctc-int8",
            },
        }
    )

    saved_response = await organization_routes.save_model_configuration_v2(request, user)
    assert persisted["value"]["kodewaves"]["language"] == "multi"
    assert saved_response.configuration["kodewaves"]["language"] == "multi"
    assert saved_response.effective_configuration["stt"]["language"] == "multi"

    reloaded_response = await organization_routes.get_model_configuration_v2(user)
    assert reloaded_response.configuration["kodewaves"]["language"] == "multi"
    assert reloaded_response.effective_configuration["stt"]["language"] == "multi"
