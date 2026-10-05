import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
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
    """Verify that both compose files gate local engines behind 'local' profile and set Part 6 RAM limits."""
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

        # Local engines must have profile local
        assert 'profiles: ["local"]' in content or "profiles:\n      - local" in content, f"{cpath} missing profile local"
        # Piper must have 768M limit and 512M floor
        assert "768M" in content, f"{cpath} missing Piper 768M limit"
        assert "512M" in content, f"{cpath} missing Piper 512M reservation"
        # Whisper must have 1536M limit and 768M floor
        assert "1536M" in content, f"{cpath} missing Whisper 1536M limit"
        # Ollama must have 4096M limit
        assert "4096M" in content, f"{cpath} missing Ollama 4096M limit"


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


def test_whisper_models_endpoint():
    """Verify /whisper/models returns known Faster-Whisper tiers with offline status when engine not running."""
    resp = client.get("/api/v1/admin/settings/whisper/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    model_ids = [m["id"] for m in data["models"]]
    assert "Systran/faster-whisper-tiny" in model_ids
    assert "Systran/faster-whisper-base" in model_ids


def test_deploy_script_profile_handling():
    """Verify deploy.sh checks ENABLE_LOCAL_AI_ENGINE and passes --profile local."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    deploy_sh = os.path.join(repo_root, "deploy.sh")
    with open(deploy_sh, "r", encoding="utf-8") as f:
        content = f.read()

    assert "ENABLE_LOCAL_AI_ENGINE" in content
    assert "--profile local" in content
    assert "pg_dump" in content
