from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.db.kodewaves_models import ContactModel
from api.routes import forms
from api.services.forms import validate_answers
from api.tests.test_workflow_text_chat import _create_user_and_workflow


@pytest.fixture
async def form_workspaces(db_session, async_session):
    definition = {"nodes": [{"id": "start", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Start", "prompt": "Help the caller."}}], "edges": []}
    rows = []
    for _ in range(2):
        user, workflow = await _create_user_and_workflow(db_session, async_session, workflow_definition=definition, suffix=uuid4().hex)
        run = await db_session.create_workflow_run(name="Form validation test", workflow_id=workflow.id, mode="textchat", user_id=user.id, organization_id=user.selected_organization_id)
        contact = ContactModel(organization_id=user.selected_organization_id, first_name="Customer", phone="+919000000001")
        async_session.add(contact)
        await async_session.flush()
        rows.append((user, run, contact))
    return rows


@pytest.mark.asyncio
async def test_submissions_scope_links_and_reject_disabled_or_missing_answers(form_workspaces):
    (owner, call, contact), (_, foreign_call, foreign_contact) = form_workspaces
    created = await forms.create_form(forms.FormCreateRequest(title="Intake", fields=[{"name": "name", "label": "Customer name", "type": "text", "required": True}]), user=owner)
    form_id = created["id"]
    for payload, status in [
        ({"data": {}}, 400),
        ({"data": {"name": "Customer"}, "contact_id": "invalid"}, 400),
        ({"data": {"name": "Customer"}, "contact_id": str(foreign_contact.id)}, 404),
        ({"data": {"name": "Customer"}, "call_id": foreign_call.id}, 404),
    ]:
        with pytest.raises(HTTPException) as error:
            await forms.submit_form(form_id, forms.SubmitFormRequest(**payload), user=owner)
        assert error.value.status_code == status
    assert await forms.list_submissions(form_id, user=owner) == []
    await forms.submit_form(form_id, forms.SubmitFormRequest(data={"name": "Customer"}, call_id=call.id, contact_id=str(contact.id)), user=owner)
    saved = await forms.list_submissions(form_id, user=owner)
    assert len(saved) == 1 and saved[0].data == {"name": "Customer"}
    await forms.update_form(form_id, forms.FormCreateRequest(is_active=False), user=owner)
    await forms.update_form(form_id, forms.FormCreateRequest(title="Renamed intake"), user=owner)
    assert (await forms.get_form(form_id, user=owner)).is_active is False
    with pytest.raises(HTTPException) as error:
        await forms.submit_form(form_id, forms.SubmitFormRequest(data={"name": "Customer"}), user=owner)
    assert error.value.status_code == 400
    assert len(await forms.list_submissions(form_id, user=owner)) == 1


def test_answer_validation_preserves_indian_text_and_numeric_values():
    fields = [{"name": "name", "type": "text", "required": True}, {"name": "amount", "type": "number", "required": True}]
    assert validate_answers(fields, {"name": "  अदिति  ", "amount": "१२३"}) == {"name": "अदिति", "amount": 123}
    assert validate_answers(fields, {"name": "Aditi", "amount": 12345678901234567890})["amount"] == 12345678901234567890
    for value in ("not a number", True, float("nan")):
        with pytest.raises(ValueError, match="must be a number"):
            validate_answers(fields, {"name": "Aditi", "amount": value})
    with pytest.raises(ValueError, match="required"):
        validate_answers(fields, {"name": "  ", "amount": 1})
    with pytest.raises(ValueError, match="unique"):
        forms.FormCreateRequest(fields=[{"name": "same"}, {"name": "same"}])
