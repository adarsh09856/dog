from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import organization
from api.schemas.ai_model_configuration import OrganizationAIModelConfigurationV2


@pytest.mark.asyncio
async def test_saved_invalid_model_configuration_still_loads_for_repair(monkeypatch):
    saved = OrganizationAIModelConfigurationV2.model_validate({
        "mode": "kodewaves",
        "kodewaves": {
            "llm_model": "qwen3.5:2b",
            "llm_engine_type": "local_cpu",
            "stt_model": "indicconformer-ctc-int8",
            "stt_engine_type": "local_cpu",
            "tts_model": "indus-pocket-tts",
            "tts_engine_type": "local_cpu",
            "voice": "Inaya",
            "language": "multi",
        },
    })
    monkeypatch.setattr(
        organization,
        "get_resolved_ai_model_configuration",
        AsyncMock(side_effect=HTTPException(status_code=400, detail="Choose an explicit STT language")),
    )
    get_saved = AsyncMock(return_value=saved)
    monkeypatch.setattr(organization, "get_organization_ai_model_configuration_v2", get_saved)

    response = await organization._model_configuration_v2_response(
        user=SimpleNamespace(selected_organization_id=7),
    )

    get_saved.assert_awaited_once_with(7)
    assert response.configuration["kodewaves"]["stt_model"] == "indicconformer-ctc-int8"
    assert response.resolution_error == "Choose an explicit STT language"
    assert response.source == "organization_v2"
