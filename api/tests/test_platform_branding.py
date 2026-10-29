from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import installation
from api.routes.admin import settings as admin_settings
from api.schemas.branding import PlatformBranding


def test_legacy_seed_branding_uses_current_kodewaves_assets():
    branding = PlatformBranding.model_validate(
        {
            "platform_name": "Kodewaves Sovereign Platform",
            "company_name": "Kodewaves Inc.",
            "logo_url": "/logo.png",
            "favicon_url": "/favicon.ico",
            "primary_color": "#0284c7",
            "support_email": "support@kodewaves.in",
        }
    )

    assert branding.company_name == "Kodewaves"
    assert branding.logo_url == ""
    assert branding.favicon_url == "/kodewaves-mark.svg"
    assert branding.primary_color == "#426b57"


def test_defaults_match_the_shared_kodewaves_theme():
    branding = PlatformBranding()

    assert branding.company_name == "Kodewaves"
    assert branding.primary_color == "#426b57"
    assert branding.favicon_url == "/kodewaves-mark.svg"


@pytest.mark.asyncio
async def test_admin_settings_read_normalizes_only_the_legacy_platform_seed(monkeypatch):
    get_settings = AsyncMock(
        return_value={
            "branding": {
                "platform_name": "Kodewaves Sovereign Platform",
                "company_name": "Kodewaves Inc.",
                "logo_url": "/logo.png",
                "favicon_url": "/favicon.ico",
                "primary_color": "#0284c7",
                "support_email": "support@kodewaves.in",
            }
        }
    )
    monkeypatch.setattr(admin_settings.kodewaves_db_client, "get_settings_map", get_settings)

    result = await admin_settings.get_all_platform_settings(_user=SimpleNamespace(id=1))

    assert result.company_name == "Kodewaves"
    assert result.logo_url == ""
    assert result.favicon_url == "/kodewaves-mark.svg"
    assert result.primary_color == "#426b57"


def test_custom_brand_assets_are_preserved():
    branding = PlatformBranding.model_validate(
        {"logo_url": "https://brand.example/logo.svg", "favicon_url": "/customer-icon.svg"}
    )

    assert branding.logo_url == "https://brand.example/logo.svg"
    assert branding.favicon_url == "/customer-icon.svg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("edition", "setting_key"),
    [("saas", "branding"), ("client", "client_branding")],
)
async def test_brand_update_stays_in_edition_specific_setting_namespace(
    monkeypatch, edition, setting_key
):
    save = AsyncMock()
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", edition)
    monkeypatch.setattr(installation.kodewaves_db_client, "set_setting", save)
    branding = PlatformBranding(
        company_name="Acme Voice",
        tagline="Talk to every customer",
        logo_url="/brand.svg",
        primary_color="#2d587a",
    )

    result = await installation.update_client_branding(
        branding, _user=SimpleNamespace(is_superuser=True)
    )

    assert result == branding
    save.assert_awaited_once_with(
        setting_key, branding.model_dump(), category=setting_key
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("edition", "setting_key"),
    [("saas", "branding"), ("client", "client_branding")],
)
async def test_public_brand_read_uses_matching_edition_namespace(
    monkeypatch, edition, setting_key
):
    get_setting = AsyncMock(return_value={"company_name": "Acme Voice"})
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", edition)
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", get_setting)

    result = await installation.get_client_branding()

    assert result.company_name == "Acme Voice"
    get_setting.assert_awaited_once_with(setting_key, raise_on_error=True)


@pytest.mark.asyncio
async def test_brand_read_reports_database_failure_instead_of_default_brand(monkeypatch):
    from fastapi import HTTPException

    getter = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", getter)
    with pytest.raises(HTTPException) as error:
        await installation.get_client_branding()
    assert error.value.status_code == 503
    assert getter.await_args.kwargs["raise_on_error"] is True
