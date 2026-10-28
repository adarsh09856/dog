from uuid import uuid4

import pytest

from api.db import db_client
from api.db.kodewaves_models import WebsiteWidgetModel
from api.db.models import OrganizationModel, UserModel
from api.routes import widgets


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
