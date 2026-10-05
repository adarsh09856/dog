"""
Tests for WP1: Truth Layer Catalog, Visibility Formula, and Dynamic Resolution.
"""

import pytest
from unittest.mock import AsyncMock, patch

from api.services.catalog.normalize import normalize_provider_name
from api.services.catalog.catalog_service import catalog_service


def test_normalize_provider_name():
    assert normalize_provider_name("gemini") == "google"
    assert normalize_provider_name("google_realtime") == "google"
    assert normalize_provider_name("openai_realtime") == "openai"
    assert normalize_provider_name("azure_realtime") == "azure"
    assert normalize_provider_name("azure_speech") == "azure"
    assert normalize_provider_name("bodhi") == "navana"
    assert normalize_provider_name("grok_realtime") == "grok"
    assert normalize_provider_name("xai") == "grok"
    assert normalize_provider_name("ultravox_realtime") == "ultravox"
    assert normalize_provider_name("openai") == "openai"
    assert normalize_provider_name("anthropic") == "anthropic"


@pytest.mark.asyncio
async def test_catalog_visibility_no_keys_empty_manifest():
    """Invariant: When no provider keys are configured and local AI is OFF, lists must be empty (no fake models)."""
    catalog_service.invalidate_cache()

    with patch("api.db.kodewaves_client.kodewaves_db_client.list_master_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("api.db.kodewaves_client.kodewaves_db_client.get_org_ai_policy", new_callable=AsyncMock) as mock_policy, \
         patch("api.db.kodewaves_client.kodewaves_db_client.get_setting", new_callable=AsyncMock) as mock_setting, \
         patch("api.db.kodewaves_client.kodewaves_db_client.list_models", new_callable=AsyncMock) as mock_models:

        mock_creds.return_value = []
        mock_policy.return_value = None
        mock_setting.return_value = {"enable_local_ai_engine": False}
        mock_models.return_value = []

        manifest = await catalog_service.get_available_catalog(organization_id=1, user_has_local_ai=False)

        assert manifest["active_providers"] == []
        assert manifest["cloud_llm_models"] == []
        assert manifest["cloud_stt_models"] == []
        assert manifest["cloud_tts_models"] == []
        assert manifest["cloud_s2s_models"] == []
        assert manifest["local_llm_models"] == []
        assert manifest["local_stt_models"] == []
        assert manifest["local_tts_models"] == []


@pytest.mark.asyncio
async def test_catalog_visibility_with_google_key():
    """Invariant: When Google key is active, Gemini models appear and are tagged has_master_key=True."""
    catalog_service.invalidate_cache()

    class FakeCred:
        provider = "google"
        is_enabled = True
        credentials_encrypted = "mock-enc"

    class FakeModel:
        def __init__(self, mid, name, prov, layer, rec=True, status="PASS"):
            self.model_identifier = mid
            self.display_name = name
            self.provider = prov
            self.layer = layer
            self.category = layer
            self.recommended = rec
            self.status = status
            self.supports_tools = True
            self.supports_streaming = True

    with patch("api.db.kodewaves_client.kodewaves_db_client.list_master_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("api.db.kodewaves_client.kodewaves_db_client.get_org_ai_policy", new_callable=AsyncMock) as mock_policy, \
         patch("api.db.kodewaves_client.kodewaves_db_client.get_setting", new_callable=AsyncMock) as mock_setting, \
         patch("api.db.kodewaves_client.kodewaves_db_client.list_models", new_callable=AsyncMock) as mock_models, \
         patch.object(catalog_service, "seed_curated_models_if_needed", new_callable=AsyncMock):

        mock_creds.return_value = [FakeCred()]
        mock_policy.return_value = None
        mock_setting.return_value = {"enable_local_ai_engine": False}
        mock_models.return_value = [
            FakeModel("gemini-3.5-flash", "Gemini 3.5 Flash", "google", "llm", rec=True),
            FakeModel("gemini-3.1-flash-tts-preview", "Gemini 3.1 TTS", "google", "tts", rec=True),
            FakeModel("failed-model", "Broken Model", "google", "llm", status="FAIL"),
            FakeModel("openai-model", "GPT-4o", "openai", "llm", rec=True),
        ]

        manifest = await catalog_service.get_available_catalog(organization_id=1, user_has_local_ai=False)

        assert "google" in manifest["active_providers"]
        # openai is NOT active, so GPT-4o must NOT be in cloud_llm_models
        llm_ids = [m["value"] for m in manifest["cloud_llm_models"]]
        assert "gemini-3.5-flash" in llm_ids
        assert "openai-model" not in llm_ids
        # Failed model must be filtered out
        assert "failed-model" not in llm_ids

        # Auto recommendation prepended when models exist
        assert llm_ids[0] == "auto"

        # Check TTS
        tts_ids = [m["value"] for m in manifest["cloud_tts_models"]]
        assert "gemini-3.1-flash-tts-preview" in tts_ids
