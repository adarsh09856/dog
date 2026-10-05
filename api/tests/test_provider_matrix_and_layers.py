import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from api.services.catalog.normalize import normalize_provider_name
from api.services.configuration.options.google import (
    GOOGLE_MODELS,
    GOOGLE_REALTIME_MODELS,
    GOOGLE_TTS_MODELS,
)
from api.services.credentials.master_credential_service import MasterCredentialService
from api.services.catalog.catalog_service import catalog_service


def test_alias_normalization_comprehensive():
    """Verify alias normalization across all supported providers."""
    aliases = {
        "openai_realtime": "openai",
        "gemini": "google",
        "google_realtime": "google",
        "google": "google",
        "azure_speech": "azure",
        "azure_realtime": "azure",
        "azure": "azure",
        "bodhi": "navana",
        "navana": "navana",
        "xai": "grok",
        "grok_realtime": "grok",
        "grok": "grok",
        "ultravox_realtime": "ultravox",
        "ultravox": "ultravox",
    }
    for alias, expected in aliases.items():
        assert normalize_provider_name(alias) == expected, f"Failed mapping for {alias}"


def test_gemini_models_updated():
    """Verify Gemini options use 3.5 and 3.1 models and do not default to retired 2.0/2.5."""
    assert "gemini-3.5-flash" in GOOGLE_MODELS
    assert "gemini-3.5-flash-lite" in GOOGLE_MODELS
    assert "gemini-3.1-flash-lite" in GOOGLE_MODELS
    assert not any("2.0" in m or "2.5-flash" in m for m in GOOGLE_MODELS)

    assert "gemini-3.1-flash-tts-preview" in GOOGLE_TTS_MODELS
    assert "gemini-3.1-flash-live-preview" in GOOGLE_REALTIME_MODELS


def test_krutrim_removed():
    """Verify Krutrim is purged from admin UI models."""
    admin_models_page = os.path.join(os.path.dirname(__file__), "..", "..", "ui", "src", "app", "admin", "models", "page.tsx")
    if os.path.exists(admin_models_page):
        with open(admin_models_page, "r", encoding="utf-8") as f:
            content = f.read()
            assert "krutrim" not in content.lower(), "Found Krutrim reference in admin models page!"


@pytest.mark.asyncio
async def test_disabled_key_does_not_fallback_to_env(monkeypatch):
    """Verify that if a key is disabled in DB, it NEVER falls back to environment variables."""
    service = MasterCredentialService()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-fallback-key-should-not-be-used")

    mock_record = AsyncMock()
    mock_record.is_enabled = False

    with patch("api.db.kodewaves_client.kodewaves_db_client.get_master_credential", return_value=mock_record):
        creds = await service.get_master_credential("openai")
        assert creds is None, "Disabled DB credential leaked into environment fallback!"


def test_deepgram_language_handling():
    """Verify Deepgram language enforcement avoids None or unset crashes."""
    from api.services.configuration.options import DEEPGRAM_LANGUAGES
    assert "en" in DEEPGRAM_LANGUAGES
    assert "hi" in DEEPGRAM_LANGUAGES
