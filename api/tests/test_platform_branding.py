from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes import installation
from api.schemas.branding import PlatformBranding


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
