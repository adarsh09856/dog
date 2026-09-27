from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.models import WorkflowRunModel
from api.enums import WorkflowRunState
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/monitoring", tags=["admin-monitoring"])


class LiveCallItem(BaseModel):
    run_id: int
    workflow_id: int
    state: str
    created_at: str
    duration_seconds: float = 0.0


@router.get("/live-calls", response_model=List[LiveCallItem])
async def list_live_calls(_user=Depends(get_superuser)):
    """List currently active / in-progress calls across all tenants."""
    async with kodewaves_db_client.get_session() as session:
        # Active calls are in INITIALIZING, RUNNING, or STREAMING state
        active_states = [WorkflowRunState.INITIALIZING.value, WorkflowRunState.RUNNING.value, WorkflowRunState.STREAMING.value]
        stmt = (
            select(WorkflowRunModel)
            .where(WorkflowRunModel.state.in_(active_states))
            .order_by(desc(WorkflowRunModel.created_at))
            .limit(100)
        )
        result = await session.execute(stmt)
        runs = result.scalars().all()

        return [
            LiveCallItem(
                run_id=r.id,
                workflow_id=r.workflow_id,
                state=r.state,
                created_at=r.created_at.isoformat() if r.created_at else "",
                duration_seconds=float((r.usage_info or {}).get("call_duration_seconds", 0.0)),
            )
            for r in runs
        ]


@router.post("/calls/{run_id}/kill", response_model=Dict[str, Any])
async def kill_active_call(run_id: int, _user=Depends(get_superuser)):
    """Emergency force-termination kill-switch for an active call."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="Call run not found")

        run.state = WorkflowRunState.FAILED.value
        run.is_completed = True
        await session.commit()

        # Trigger post-call billing
        from api.services.workflow_run_billing import report_completed_workflow_run_platform_usage
        await report_completed_workflow_run_platform_usage(run_id)

        return {"message": f"Successfully terminated call {run_id}", "status": "terminated"}
