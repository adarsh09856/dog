from uuid import uuid4

import pytest

from api.db import db_client
from api.db.kodewaves_models import WebsiteWidgetModel
from api.db.models import OrganizationModel, UserModel
from api.routes import public_embed, widgets
from api.schemas.branding import PlatformBranding


@pytest.fixture
async def widget_owner(db_session, async_session):
    suffix = uuid4().hex
    org = OrganizationModel(provider_id=f"widget-org-{suffix}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"widget-user-{suffix}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = await db_session.create_workflow(
        name="Widget acceptance agent", user_id=user.id, organization_id=org.id,
        workflow_definition={"nodes": [{"id": "start", "type": "startCall", "data": {"name": "Start", "prompt": "Help the caller."}, "position": {"x": 0, "y": 0}}], "edges": []},
    )
    return user, workflow


@pytest.mark.asyncio
async def test_widget_token_settings_domains_and_disable_delete(widget_owner, test_client_factory):
    user, workflow = widget_owner
    result = await widgets.create_widget(widgets.WidgetCreateRequest(
        workflow_id=workflow.id, name="Customer help", primary_color="#123456",
        welcome_message="Talk with support", allowed_domains=["example.test"], position="bottom-left",
    ), user=user)
    item = await widgets.get_widget(result["id"], user=user)
    assert "/embed/kodewaves-widget.js?token=emb_" in item.embed_code
    assert "loader.js" not in item.embed_code
    _, token = await widgets.widget_db.get_widget(user.selected_organization_id, result["id"])
    token_value = token.token
    assert await db_client.get_embed_tokens_by_workflow(workflow.id, user.selected_organization_id) == []
    async with test_client_factory(user) as client:
        response = await client.get(f"/api/v1/public/embed/config/{token_value}", headers={"Origin": "https://example.test"})
        assert response.status_code == 200
        assert response.json()["workflow_id"] == workflow.id
        assert response.json()["button_color"] == "#123456"
        assert response.json()["branding"]["company_name"]
        assert response.json()["settings"]["useInstallationBranding"] is False
        assert response.json()["position"] == "bottom-left"
        assert response.json()["settings"]["buttonText"] == "Talk with support"
        denied = await client.get(f"/api/v1/public/embed/config/{token_value}", headers={"Origin": "https://foreign.test"})
        assert denied.status_code == 403

        await widgets.update_widget(item.id, widgets.WidgetCreateRequest(name="Updated name", is_active=False), user=user)
        reloaded = await widgets.get_widget(item.id, user=user)
        assert reloaded.name == "Updated name"
        assert reloaded.primary_color == "#123456"
        assert reloaded.allowed_domains == ["example.test"]
        assert reloaded.position == "bottom-left"
        assert reloaded.is_active is False
        response = await client.get(f"/api/v1/public/embed/config/{token_value}", headers={"Origin": "https://example.test"})
        assert response.status_code == 403
        await widgets.update_widget(item.id, widgets.WidgetCreateRequest(is_active=True), user=user)
        response = await client.get(f"/api/v1/public/embed/config/{token_value}", headers={"Origin": "https://example.test"})
        assert response.status_code == 200
        await widgets.delete_widget(item.id, user=user)
        response = await client.get(f"/api/v1/public/embed/config/{token_value}", headers={"Origin": "https://example.test"})
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_widget_can_follow_installation_brand_color_without_losing_explicit_overrides(
    widget_owner, test_client_factory, monkeypatch
):
    user, workflow = widget_owner
    current_color = {"value": "#123456"}

    async def current_installation_color():
        return current_color["value"]

    async def current_installation_branding():
        return PlatformBranding(primary_color=current_color["value"])

    monkeypatch.setattr(widgets, "_installation_brand_color", current_installation_color)
    monkeypatch.setattr(public_embed, "_installation_branding", current_installation_branding)
    created = await widgets.create_widget(
        widgets.WidgetCreateRequest(workflow_id=workflow.id, name="Inherited color"),
        user=user,
    )
    item = await widgets.get_widget(created["id"], user=user)
    assert item.use_installation_branding is True
    assert item.primary_color == "#123456"
    _, token = await widgets.widget_db.get_widget(user.selected_organization_id, created["id"])

    async with test_client_factory(user) as client:
        headers = {"Origin": "https://example.test"}
        first = await client.get(f"/api/v1/public/embed/config/{token.token}", headers=headers)
        assert first.status_code == 200
        assert first.json()["button_color"] == "#123456"
        assert first.json()["branding"]["company_name"]
        assert first.json()["settings"]["buttonColor"] == "#123456"

        current_color["value"] = "#abcdef"
        refreshed = await client.get(f"/api/v1/public/embed/config/{token.token}", headers=headers)
        assert refreshed.status_code == 200
        assert refreshed.json()["button_color"] == "#abcdef"

    explicit = await widgets.create_widget(
        widgets.WidgetCreateRequest(
            workflow_id=workflow.id, name="Explicit color", primary_color="#fedcba"
        ),
        user=user,
    )
    await widgets.update_widget(
        explicit["id"], widgets.WidgetCreateRequest(name="Renamed explicit"), user=user
    )
    updated_explicit = await widgets.get_widget(explicit["id"], user=user)
    assert updated_explicit.primary_color == "#fedcba"
    assert updated_explicit.use_installation_branding is False
    _, explicit_token = await widgets.widget_db.get_widget(
        user.selected_organization_id, explicit["id"]
    )
    async def branding_lookup_fails():
        raise RuntimeError("branding settings unavailable")

    monkeypatch.setattr(public_embed, "_installation_branding", branding_lookup_fails)
    async with test_client_factory(user) as client:
        response = await client.get(
            f"/api/v1/public/embed/config/{explicit_token.token}",
            headers={"Origin": "https://example.test"},
        )
    assert response.status_code == 200
    assert response.json()["button_color"] == "#fedcba"
    assert response.json()["settings"]["useInstallationBranding"] is False

@pytest.mark.asyncio
async def test_existing_widget_provisions_token_without_resetting_settings(widget_owner, async_session):
    user, workflow = widget_owner
    widget = WebsiteWidgetModel(
        organization_id=user.selected_organization_id, workflow_id=workflow.id,
        widget_name="Existing widget", primary_color="#abcdef", position="bottom-left",
        allowed_domains=["existing.test"], is_active=False,
    )
    async_session.add(widget)
    await async_session.flush()
    before = await widgets.get_widget(str(widget.id), user=user)
    assert before.embed_code == ""
    updated = await widgets.update_widget(str(widget.id), widgets.WidgetCreateRequest(), user=user)
    after = await widgets.get_widget(str(widget.id), user=user)
    assert updated["embed_code"]
    assert after.primary_color == "#abcdef"
    assert after.position == "bottom-left"
    assert after.allowed_domains == ["existing.test"]
    assert after.is_active is False


@pytest.mark.asyncio
async def test_widget_does_not_replace_agent_embed_token(widget_owner):
    user, workflow = widget_owner
    direct = await db_client.create_embed_token(
        workflow.id, user.selected_organization_id, user.id,
        settings={"buttonText": "Independent agent embed"}, allowed_domains=["agent.test"],
    )
    await widgets.create_widget(widgets.WidgetCreateRequest(workflow_id=workflow.id, name="Separate widget"), user=user)
    tokens = await db_client.get_embed_tokens_by_workflow(workflow.id, user.selected_organization_id)
    assert [token.id for token in tokens] == [direct.id]
    assert tokens[0].settings == {"buttonText": "Independent agent embed"}
    assert tokens[0].allowed_domains == ["agent.test"]
