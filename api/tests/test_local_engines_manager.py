import os
import re
import sys
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.admin.settings as admin_settings
from api.routes.admin.settings import router
from api.services.auth.depends import get_superuser

# Mock superuser dependency
async def override_get_superuser():
    class MockAdmin:
        id = 1
        email = "admin@kodewaves.in"
        role = "superadmin"
    return MockAdmin()

app = FastAPI()
app.include_router(router, prefix="/api/v1/admin")
app.dependency_overrides[get_superuser] = override_get_superuser
client = TestClient(app)


def test_docker_compose_local_profiles_and_limits():
    """Verify current local inference services are opt-in and resource-bounded."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    compose_files = [
        os.path.join(repo_root, "docker-compose.yaml"),
        os.path.join(repo_root, "docker-compose.aapanel.yaml"),
    ]
    for cpath in compose_files:
        if not os.path.exists(cpath):
            continue
        with open(cpath, "r", encoding="utf-8") as f:
            content = f.read()

        def service_block(name):
            match = re.search(
                rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [\w.-]+:\n|^volumes:\n|\Z)",
                content,
            )
            assert match is not None, f"{cpath} missing {name} service"
            return match.group(1)

        # Keep the default local LLM and streaming TTS services opt-in and bounded.
        ollama = service_block("ollama")
        assert 'profiles: ["local"]' in ollama or "profiles:\n      - local" in ollama
        assert "OLLAMA_NUM_PARALLEL=1" in ollama
        assert "OLLAMA_MAX_LOADED_MODELS" in ollama
        assert "memory: 4096M" in ollama

        indic_vits = service_block("indic-vits-tts")
        assert 'profiles: ["local"]' in indic_vits or "profiles:\n      - local" in indic_vits
        assert "memory: 1024M" in indic_vits

        if re.search(r"(?m)^  indic-stt:\n", content):
            assert "memory: 2048M" in service_block("indic-stt")


def test_piper_all_voices_endpoint():
    """Verify /piper/all-voices returns curated Indic and English voices."""
    resp = client.get("/api/v1/admin/settings/piper/all-voices")
    assert resp.status_code == 200
    voices = resp.json()
    assert len(voices) >= 8
    voice_ids = [v["id"] for v in voices]
    assert "hi_IN-priyamvada-medium" in voice_ids
    assert "hi_IN-pratham-medium" in voice_ids
    assert "en_US-lessac-medium" in voice_ids

    # Test filtering by language
    resp_hi = client.get("/api/v1/admin/settings/piper/all-voices?language=Hindi")
    assert resp_hi.status_code == 200
    hi_voices = resp_hi.json()
    assert all("hi" in v["language"].lower() or "hindi" in v["language_name"].lower() for v in hi_voices)


def test_indic_stt_models_endpoint(monkeypatch):
    """Verify the active local IndicConformer inventory is exposed to admins."""
    async def fake_get_setting(_key):
        return {"indic_stt_endpoint": "http://indic-stt:8000/v1"}

    async def fake_inventory(endpoint):
        return {
            "model": {"id": "indicconformer-ctc-int8"},
            "languages": ["en", "hi", "ta"],
            "endpoint": endpoint,
        }

    monkeypatch.setattr(admin_settings.kodewaves_db_client, "get_setting", fake_get_setting)
    monkeypatch.setattr(admin_settings, "_get_indic_stt_inventory", fake_inventory)
    resp = client.get("/api/v1/admin/settings/indic-stt/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "model": "indicconformer-ctc-int8",
        "languages": ["en", "hi", "ta"],
        "endpoint": "http://indic-stt:8000/v1",
        "status": "online",
    }


def test_deploy_script_profile_handling():
    """Verify deploy.sh checks ENABLE_LOCAL_AI_ENGINE and passes --profile local."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    deploy_sh = os.path.join(repo_root, "deploy.sh")
    with open(deploy_sh, "r", encoding="utf-8") as f:
        content = f.read()

    assert "ENABLE_LOCAL_AI_ENGINE" in content
    assert "--profile local" in content
    assert "pg_dump" in content
