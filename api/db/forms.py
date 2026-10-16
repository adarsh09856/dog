"""Workspace-scoped persistence for captured form answers."""

from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import ContactModel, FormModel, FormSubmissionModel
from api.db.models import WorkflowModel, WorkflowRunModel


async def get_form(organization_id, form_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(FormModel).where(
                FormModel.id == form_id,
                FormModel.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()


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
