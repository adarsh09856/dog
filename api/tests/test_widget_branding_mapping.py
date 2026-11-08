"""Unit tests for preserving explicit widget branding while inheriting defaults."""

from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from api.routes import public_embed
from api.routes.public_embed import (
    _installation_brand_color as public_embed_brand_color,
    _installation_branding,
)
from api.routes.widgets import (
    WidgetCreateRequest,
    _installation_brand_color as widget_brand_color,
    _widget_values,
)
from api.schemas.branding import PlatformBranding


def test_new_widget_without_color_inherits_installation_branding():
    request = WidgetCreateRequest(workflow_id=12, name="Inherited")

    values = _widget_values(request, creating=True)

    assert values["use_installation_branding"] is True
    assert values["primary_color"] is None


def test_new_widget_with_color_keeps_explicit_override():
    request = WidgetCreateRequest(
        workflow_id=12, name="Custom", primary_color="#123456"
    )

    values = _widget_values(request, creating=True)

    assert values["use_installation_branding"] is False
    assert values["primary_color"] == "#123456"


def test_partial_widget_update_does_not_rewrite_color_or_inheritance_mode():
    request = WidgetCreateRequest(name="Renamed")

    values = _widget_values(request, creating=False)

    assert "primary_color" not in values
    assert "use_installation_branding" not in values


def test_explicit_null_color_update_preserves_the_persisted_color():
    request = WidgetCreateRequest.model_validate({"primary_color": None})

    values = _widget_values(request, creating=False)

    assert "primary_color" not in values


def test_explicit_update_can_switch_to_installation_branding():
    request = WidgetCreateRequest(use_installation_branding=True)

    values = _widget_values(request, creating=False)

    assert values == {"use_installation_branding": True}


@pytest.mark.parametrize(
    "resolver",
    [widget_brand_color, public_embed_brand_color],
)
@pytest.mark.parametrize("color", ["#12zz56", "#12345", "#1234567"])
async def test_invalid_persisted_installation_color_uses_safe_default(
    monkeypatch, resolver, color
):
    async def get_setting(_key):
        return {"primary_color": color}

    monkeypatch.setattr(
        "api.routes.widgets.kodewaves_db_client.get_setting", get_setting
    )

    assert await resolver() == "#426b57"


async def test_public_embed_resolves_site_path_logo_on_the_installation_domain(monkeypatch):
    async def get_setting(_key):
        return {"company_name": "Acme", "logo_url": "/assets/acme.svg"}

    monkeypatch.setattr(
        "api.routes.public_embed.kodewaves_db_client.get_setting", get_setting
    )
    monkeypatch.setattr("api.routes.public_embed.UI_APP_URL", "https://app.acme.example")

    branding = await _installation_branding()

    assert branding.logo_url == "https://app.acme.example/assets/acme.svg"


@pytest.mark.parametrize(
    ("settings", "expected_color"),
    [
        ({"buttonColor": "#123456", "useInstallationBranding": True}, "#426b57"),
        ({"buttonColor": "#123456", "useInstallationBranding": False}, "#123456"),
        ({}, "#426b57"),
    ],
)
async def test_embed_config_applies_installation_branding_and_keeps_explicit_override(
    monkeypatch, settings, expected_color
):
    token = SimpleNamespace(
        workflow_id=12,
        organization_id=34,
        is_active=True,
        allowed_domains=["https://embed.example"],
        settings=settings,
    )

    async def get_token(_token):
        return token

    async def allow_feature(_organization_id, _feature):
        return None

    async def installation_branding():
        return PlatformBranding(company_name="Acme", primary_color="#426b57")

    monkeypatch.setattr(public_embed.db_client, "get_embed_token_by_token", get_token)
    monkeypatch.setattr(public_embed, "enforce_saas_feature", allow_feature)
    monkeypatch.setattr(public_embed, "validate_embed_origin", lambda *_: True)
    monkeypatch.setattr(public_embed, "_installation_branding", installation_branding)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/public/embed/config/token",
            "headers": [(b"origin", b"https://embed.example")],
            "scheme": "https",
            "server": ("api.example", 443),
            "client": ("127.0.0.1", 1234),
        }
    )
    response = Response()

    result = await public_embed.get_embed_config("token", request, response)

    assert result.button_color == expected_color
    assert result.branding.company_name == "Acme"
    assert response.headers["access-control-allow-origin"] == "https://embed.example"
