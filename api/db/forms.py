"""Workspace-scoped persistence for captured form answers."""

import uuid

from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import ContactModel, FormModel, FormSubmissionModel
from api.db.models import WorkflowModel, WorkflowRunModel


async def get_form(organization_id, form_id):
    try:
        form_id = uuid.UUID(str(form_id))
    except (ValueError, TypeError, AttributeError):
        form_id = str(form_id)
    async with kodewaves_db_client.get_session() as session:
        identifier_column = FormModel.id if isinstance(form_id, uuid.UUID) else FormModel.slug
        result = await session.execute(
            select(FormModel).where(
                identifier_column == form_id,
                FormModel.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()


async def get_contact_for_prefill(organization_id, contact_id):
    """Read reusable form values only from a contact in this workspace."""
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(ContactModel).where(
            ContactModel.id == contact_id,
            ContactModel.organization_id == organization_id,
        ))
        contact = result.scalar_one_or_none()
        if contact is None:
            return None
        full_name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
        values = dict(contact.custom_fields or {})
        values.update({
            "first_name": contact.first_name, "last_name": contact.last_name,
            "name": full_name, "full_name": full_name, "customer_name": full_name,
            "phone": contact.phone, "phone_number": contact.phone,
            "customer_phone": contact.phone, "email": contact.email,
            "customer_email": contact.email, "company": contact.company,
        })
        return {key: value for key, value in values.items() if value is not None and value != ""}


async def create_submission(
    organization_id,
    form_id,
    data,
    *,
    contact_id=None,
    call_id=None,
    expected_fields=None,
):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(FormModel)
            .where(
                FormModel.id == form_id,
                FormModel.organization_id == organization_id,
            )
            .with_for_update()
        )
        form = result.scalar_one_or_none()
        if form is None:
            raise LookupError("Form not found")
        if not form.is_active:
            raise ValueError("This form is disabled")
        if (form.fields_schema or []) != (expected_fields or []):
            raise ValueError("The form fields changed. Reload the form and retry")
        if contact_id is not None:
            result = await session.execute(
                select(ContactModel.id).where(
                    ContactModel.id == contact_id,
                    ContactModel.organization_id == organization_id,
                )
            )
            if result.scalar_one_or_none() is None:
                raise LookupError("Contact not found")
        if call_id is not None:
            result = await session.execute(
                select(WorkflowRunModel.id)
                .join(
                    WorkflowModel,
                    WorkflowRunModel.workflow_id == WorkflowModel.id,
                )
                .where(
                    WorkflowRunModel.id == call_id,
                    WorkflowModel.organization_id == organization_id,
                )
            )
            if result.scalar_one_or_none() is None:
                raise LookupError("Call not found")
        submission = FormSubmissionModel(
            form_id=form_id,
            organization_id=organization_id,
            submitted_data=data,
            contact_id=contact_id,
            call_id=call_id,
        )
        session.add(submission)
        await session.commit()
        await session.refresh(submission)
        return submission
