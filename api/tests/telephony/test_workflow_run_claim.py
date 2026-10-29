"""The telephony media socket must claim each initialized run exactly once."""

import uuid

import pytest

from api.enums import WorkflowRunState
from api.tests.integrations._run_pipeline_helpers import create_workflow_run_rows
from api.tests.integrations.test_run_pipeline import WORKFLOW_DEFINITION


@pytest.mark.asyncio
async def test_initialized_workflow_run_has_one_org_scoped_claim(
    db_session, async_session
):
    workflow_run, _, workflow = await create_workflow_run_rows(
        db_session,
        async_session,
        workflow_definition=WORKFLOW_DEFINITION,
        name_prefix="Telephony Run Claim",
        provider_id_suffix=f"claim-{uuid.uuid4().hex}",
    )

    assert await db_session.claim_initialized_workflow_run(
        workflow_run.id, workflow.id, workflow.organization_id
    ) is True
    assert await db_session.claim_initialized_workflow_run(
        workflow_run.id, workflow.id, workflow.organization_id
    ) is False
    assert await db_session.claim_initialized_workflow_run(
        workflow_run.id, workflow.id + 1, workflow.organization_id
    ) is False
    assert await db_session.claim_initialized_workflow_run(
        workflow_run.id, workflow.id, workflow.organization_id + 1
    ) is False

    refreshed = await db_session.get_workflow_run(
        workflow_run.id, organization_id=workflow.organization_id
    )
    assert refreshed.state == WorkflowRunState.RUNNING.value
