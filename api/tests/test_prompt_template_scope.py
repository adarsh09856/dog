from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.db.kodewaves_models import PromptTemplateModel
from api.db.models import OrganizationModel
from api.routes import prompt_templates as routes


@pytest.fixture
async def template_users(db_session, async_session):
    organizations = [OrganizationModel(provider_id=f"template-org-{uuid4()}") for _ in range(2)]
    async_session.add_all(organizations)
    await async_session.flush()
    return [SimpleNamespace(selected_organization_id=org.id, is_superuser=False) for org in organizations]


def request(title):
    return routes.PromptTemplateCreateRequest(
        title=title, category="Support", description="Private service details",
        system_prompt="Help with the configured service.", first_message="How can I help?", is_featured=True,
    )


@pytest.mark.asyncio
async def test_custom_templates_are_private_for_list_update_and_delete(template_users):
    owner, foreign = template_users
    created = await routes.create_template(request("Private template"), _user=owner)
    assert [item.id for item in await routes.list_templates(_user=owner)] == [created["id"]]
    assert await routes.list_templates(_user=foreign) == []
    for identifier in (created["id"], "Private template"):
        with pytest.raises(HTTPException) as error:
            await routes.update_template(identifier, routes.PromptTemplateUpdateRequest(title="Stolen"), _user=foreign)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            await routes.delete_template(identifier, _user=foreign)
        assert error.value.status_code == 404
    await routes.update_template(created["id"], routes.PromptTemplateUpdateRequest(title="Updated"), _user=owner)
    items = await routes.list_templates(_user=owner)
    assert items[0].title == "Updated"
    assert items[0].is_featured is False
    await routes.delete_template(created["id"], _user=owner)
    assert await routes.list_templates(_user=owner) == []


@pytest.mark.asyncio
async def test_system_templates_shared_but_only_platform_admin_can_change(template_users, async_session):
    owner, other = template_users
    template = PromptTemplateModel(title="Shared default", category="Support", description="Default", system_prompt="Help", first_message="Hello", is_system_template=True)
    legacy = PromptTemplateModel(title="Unowned legacy custom", category="Support", description="Private", system_prompt="Private", first_message="Hello", is_system_template=False)
    async_session.add_all([template, legacy])
    await async_session.flush()
    for user in (owner, other):
        assert [item.title for item in await routes.list_templates(_user=user)] == ["Shared default"]
        with pytest.raises(HTTPException) as error:
            await routes.delete_template(str(template.id), _user=user)
        assert error.value.status_code == 403
    admin = SimpleNamespace(selected_organization_id=owner.selected_organization_id, is_superuser=True)
    assert len(await routes.list_templates(_user=admin)) == 2
    await routes.update_template(str(template.id), routes.PromptTemplateUpdateRequest(title="Updated shared default"), _user=admin)
    assert (await routes.list_templates(_user=other))[0].title == "Updated shared default"
    assert await routes.list_templates(category="Missing category", _user=other) == []
    assert len(await routes.list_templates(_user=admin)) == 2


@pytest.mark.asyncio
async def test_seed_does_not_confuse_private_template_with_shared_default(template_users):
    from scripts.seed_platform import seed_prompt_templates

    owner, other = template_users
    await routes.create_template(request("Property Inquiry Handler"), _user=owner)
    await seed_prompt_templates()
    shared = await routes.list_templates(_user=other)
    assert any(item.title == "Property Inquiry Handler" and item.is_featured for item in shared)
    await seed_prompt_templates()
    repeated = await routes.list_templates(_user=other)
    assert len(repeated) == len(shared)
