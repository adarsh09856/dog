"""Workspace-scoped persistence for captured form answers."""

import uuid
from sqlalchemy import desc, func, select

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


async def get_public_form(form_id, token_hash=None):
    """Resolve an explicitly published public form without exposing its tenant."""
    try:
        form_id = uuid.UUID(str(form_id))
    except (ValueError, TypeError, AttributeError):
        return None
    filters = [
        FormModel.id == form_id,
        FormModel.is_active.is_(True),
        FormModel.public_submission_enabled.is_(True),
    ]
    if token_hash is not None:
        filters.append(FormModel.public_token_hash == token_hash)
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(FormModel).where(*filters))
        return result.scalar_one_or_none()


async def create_public_submission(
    form_id, token_hash, data, *, expected_fields, expected_origins
):
    """Atomically recheck publication/token/schema and store a public submission."""
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(FormModel)
            .where(FormModel.id == form_id)
            .with_for_update()
        )
        form = result.scalar_one_or_none()
        if (
            form is None
            or not form.is_active
            or not form.public_submission_enabled
            or form.public_token_hash != token_hash
        ):
            raise LookupError("Form not found")
        if (form.public_allowed_origins or []) != (expected_origins or []):
            raise LookupError("Form not found")
        if (form.fields_schema or []) != (expected_fields or []):
            raise ValueError("Form schema changed")
        submission = FormSubmissionModel(
            form_id=form.id,
            organization_id=form.organization_id,
            submitted_data=data,
        )
        session.add(submission)
        await session.commit()
        return submission

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


async def list_submissions(organization_id, form_id, *, limit=50, offset=0):
    """Return one form-submission page and a count, scoped to its workspace."""
    async with kodewaves_db_client.get_session() as session:
        filters = (
            FormSubmissionModel.organization_id == organization_id,
            FormSubmissionModel.form_id == form_id,
        )
        result = await session.execute(
            select(FormSubmissionModel)
            .where(*filters)
            .order_by(desc(FormSubmissionModel.created_at), desc(FormSubmissionModel.id))
            .limit(limit)
            .offset(offset)
        )
        total = await session.scalar(
            select(func.count(FormSubmissionModel.id)).where(*filters)
        )
        return list(result.scalars().all()), int(total or 0)


async def get_public_access_settings(organization_id, form_id):
    """Read public form settings for a form owned by the selected organization."""
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(FormModel).where(
                FormModel.id == form_id,
                FormModel.organization_id == organization_id,
            )
        )
        form = result.scalar_one_or_none()
    if form is None:
        return None
    return {
        "enabled": form.public_submission_enabled,
        "token_configured": bool(form.public_token_hash),
        "allowed_origins": form.public_allowed_origins or [],
    }


async def set_public_access_settings(
    organization_id,
    form_id,
    *,
    enabled,
    allowed_origins,
    rotate_token,
    candidate_token_hash,
):
    """Update public form settings under an organization-scoped row lock."""
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
            return None
        if enabled and not form.is_active:
            raise ValueError("Activate the form before publishing")

        token_created = enabled and (rotate_token or not form.public_token_hash)
        if token_created:
            form.public_token_hash = candidate_token_hash
        elif not enabled:
            # Disable revokes the old bearer token, so a later publish cannot
            # silently re-enable a credential that may already be leaked.
            form.public_token_hash = None
        form.public_submission_enabled = enabled
        form.public_allowed_origins = allowed_origins
        await session.commit()
        return {
            "enabled": form.public_submission_enabled,
            "token_configured": bool(form.public_token_hash),
            "allowed_origins": form.public_allowed_origins or [],
            "token_created": bool(token_created),
        }
