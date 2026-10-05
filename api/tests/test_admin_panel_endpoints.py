import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.admin.monitoring import router as monitoring_router
from api.routes.admin.settings import router as settings_router
from api.services.auth.depends import get_superuser


async def mock_superuser():
    class MockAdmin:
        id = 1
        email = "admin@kodewaves.com"
        is_superuser = True
        is_active = True
    return MockAdmin()


app = FastAPI()
app.include_router(monitoring_router, prefix="/api/v1/admin")
app.include_router(settings_router, prefix="/api/v1/admin")
app.dependency_overrides[get_superuser] = mock_superuser


def test_admin_monitoring_stats_and_system_resources():
    client = TestClient(app)

    # 1. Test /monitoring/stats
    response = client.get("/api/v1/admin/monitoring/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_calls" in data
    assert "active_calls" in data
    assert "total_minutes" in data
    assert "gross_margin_percent" in data
    assert "total_users" in data
    assert "total_organizations" in data
    assert "failed_verifications" in data
    assert "retired_model_alerts" in data
    assert "disk_usage_percent" in data
    assert "disk_free_gb" in data
    assert data["disk_free_gb"] > 0

    # 2. Test /monitoring/system-resources
    res_response = client.get("/api/v1/admin/monitoring/system-resources")
    assert res_response.status_code == 200
    res_data = res_response.json()
    assert "active_concurrency" in res_data
    assert "concurrency_cap" in res_data
    assert "queue_size" in res_data
    assert "disk_free_gb" in res_data
    assert "disk_usage_percent" in res_data


def test_admin_settings_masking_and_preservation():
    client = TestClient(app)

    # 1. Fetch settings
    response = client.get("/api/v1/admin/settings")
    assert response.status_code == 200
    settings = response.json()
    assert "company_name" in settings

    # 2. Saving settings with masked secrets preserves original
    with patch("api.routes.admin.settings.kodewaves_db_client.set_setting", new=AsyncMock(return_value=True)), \
         patch("api.routes.admin.settings.kodewaves_db_client.get_setting", new=AsyncMock(return_value={
             "smtp_password": "real_unmasked_smtp_password",
             "razorpay_key_secret": "real_unmasked_razorpay_secret"
         })), \
         patch("api.routes.admin.settings.kodewaves_db_client.record_audit_log", new=AsyncMock()):

        save_payload = {
            "company_name": "Kodewaves Sovereign Test",
            "allow_user_byok": False,
            "smtp_host": "smtp.example.com",
            "smtp_password": "••••••••",
            "razorpay_key_id": "rzp_test_123",
            "razorpay_key_secret": "••••••••secret",
        }
        save_resp = client.post("/api/v1/admin/settings", json=save_payload)
        assert save_resp.status_code == 200
