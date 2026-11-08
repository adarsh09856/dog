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


@pytest.mark.asyncio
async def test_client_admin_reads_client_branding_before_legacy_branding(monkeypatch):
    monkeypatch.setattr(admin_settings, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        admin_settings.kodewaves_db_client,
        "get_settings_map",
        AsyncMock(
            return_value={
                "branding": {"company_name": "Old Brand"},
                "client_branding": {"company_name": "Customer Brand"},
            }
        ),
    )

    result = await admin_settings.get_all_platform_settings(_user=SimpleNamespace(id=1))

    assert result.company_name == "Customer Brand"


@pytest.mark.asyncio
async def test_client_admin_settings_save_writes_client_branding_namespace(monkeypatch):
    monkeypatch.setattr(admin_settings, "KODEWAVES_EDITION", "client")
    get_setting = AsyncMock(side_effect=lambda key: {
        "client_branding": {},
        "branding": {"company_name": "Legacy Customer Brand"},
    }.get(key, {}))
    save = AsyncMock()
    monkeypatch.setattr(admin_settings.kodewaves_db_client, "get_setting", get_setting)
    monkeypatch.setattr(admin_settings.kodewaves_db_client, "set_setting", save)
    monkeypatch.setattr(admin_settings.kodewaves_db_client, "record_audit_log", AsyncMock())
    monkeypatch.setattr(admin_settings.catalog_service, "notify_changed", AsyncMock())

    await admin_settings.update_platform_settings(
        {"company_name": "New Customer Brand"},
        SimpleNamespace(id=1, email="owner@example.com"),
    )

    save.assert_awaited_once()
    assert save.await_args.kwargs["key"] == "client_branding"
    assert save.await_args.kwargs["category"] == "client_branding"
    assert save.await_args.kwargs["value"]["company_name"] == "New Customer Brand"
    assert save.await_args.kwargs["value"]["tagline"] == "Voice agents for web and phone"


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
async def test_client_public_brand_read_falls_back_to_legacy_shared_branding(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    get_setting = AsyncMock(side_effect=[{}, {"company_name": "Legacy Customer Brand"}])
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", get_setting)

    result = await installation.get_client_branding()

    assert result.company_name == "Legacy Customer Brand"
    assert [call.args[0] for call in get_setting.await_args_list] == [
        "client_branding", "branding",
    ]


@pytest.mark.asyncio
async def test_brand_read_reports_database_failure_instead_of_default_brand(monkeypatch):
    from fastapi import HTTPException

    getter = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(installation.kodewaves_db_client, "get_setting", getter)
    with pytest.raises(HTTPException) as error:
        await installation.get_client_branding()
    assert error.value.status_code == 503
    assert getter.await_args.kwargs["raise_on_error"] is True
