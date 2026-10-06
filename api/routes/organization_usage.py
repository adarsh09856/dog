import asyncio
import json
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from api.constants import DEPLOYMENT_MODE, UI_APP_URL
from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.call_concurrency import call_concurrency
from api.services.mps_service_key_client import mps_service_key_client
from api.services.reports import generate_usage_runs_report_csv
from api.utils.artifacts import artifact_url
from api.utils.recording_artifacts import has_recording_track

router = APIRouter(prefix="/organizations")


class OrganizationConcurrentCallsResponse(BaseModel):
    organization_id: int
    active_calls: int = Field(
        ge=0,
        description=(
            "Occupied concurrent call slots across all workers, including "
            "dialing/ringing reservations. Excludes expired slots."
        ),
    )


@router.get(
    "/concurrent-calls",
    response_model=OrganizationConcurrentCallsResponse,
    responses={
        401: {"description": "Missing or invalid credentials"},
        503: {"description": "The current call count is unavailable"},
    },
)
async def get_organization_concurrent_calls(
    response: Response,
    user: Annotated[UserModel, Depends(get_user_with_selected_organization)],
) -> OrganizationConcurrentCallsResponse:
    """Get your organization's current concurrent call count across all workers.

    Authenticate with X-API-Key; the key determines the organization. Session
    authentication also works for the user's selected organization. Counts
    occupied call slots, including dialing/ringing calls before media starts,
    using the concurrency limiter's stale-slot expiry. This is a snapshot,
    not a reservation of capacity for a future call.
    """
    organization_id = user.selected_organization_id
    try:
        async with asyncio.timeout(5):
            active_calls = await call_concurrency.get_org_active_calls(organization_id)
    except (RedisError, OSError):
        logger.exception(
            "Organization call count unavailable for org {}", organization_id
        )
        raise HTTPException(
            status_code=503,
            detail="Concurrent call count unavailable",
            headers={"Cache-Control": "no-store"},
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return OrganizationConcurrentCallsResponse(
        organization_id=organization_id, active_calls=active_calls
    )


class CurrentUsageResponse(BaseModel):
    period_start: str
    period_end: str
    used_kodewaves_tokens: float = 0
    used_dograh_tokens: float = 0
    total_duration_seconds: int
    used_amount_usd: Optional[float] = None
    currency: Optional[str] = None
    price_per_second_usd: Optional[float] = None


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class WorkflowRunUsageResponse(BaseModel):
    id: int
    workflow_id: int
    workflow_name: Optional[str]
    name: str
    created_at: str
    kodewaves_token_usage: float = 0
    dograh_token_usage: float = 0
    call_duration_seconds: int
    recording_url: Optional[str] = None
    transcript_url: Optional[str] = None
    user_recording_url: Optional[str] = None
    bot_recording_url: Optional[str] = None
    recording_public_url: Optional[str] = None
    transcript_public_url: Optional[str] = None
    user_recording_public_url: Optional[str] = None
    bot_recording_public_url: Optional[str] = None
    public_access_token: Optional[str] = None
    phone_number: Optional[str] = Field(
        default=None,
        deprecated=True,
        description="Deprecated. Use caller_number and called_number instead.",
    )
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    call_type: Optional[str] = None
    mode: Optional[str] = None
    disposition: Optional[str] = None
    initial_context: Optional[Dict[str, Any]] = None
    gathered_context: Optional[Dict[str, Any]] = None
    # New USD field
    charge_usd: Optional[float] = None


class UsageHistoryResponse(BaseModel):
    runs: List[WorkflowRunUsageResponse]
    total_kodewaves_tokens: float = 0
    total_dograh_tokens: float = 0
    total_duration_seconds: int
    total_count: int
    page: int
    limit: int
    total_pages: int


class DailyUsageItem(BaseModel):
    date: str
    minutes: float
    cost_usd: Optional[float] = None
    kodewaves_tokens: float = 0
    dograh_tokens: float = 0
    call_count: int


class DailyUsageBreakdownResponse(BaseModel):
    breakdown: List[DailyUsageItem]
    total_minutes: float
    total_cost_usd: Optional[float] = None
    total_kodewaves_tokens: float = 0
    total_dograh_tokens: float = 0
    currency: Optional[str] = None


@router.get("/usage/current-period", response_model=CurrentUsageResponse)
async def get_current_period_usage(user: UserModel = Depends(get_user)):
    """Get current reporting-period usage for the user's organization."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    try:
        usage = await db_client.get_current_usage(user.selected_organization_id)
        return usage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


FILTERS_DESCRIPTION = """\
JSON-encoded array of filter objects. Each object has the shape:

```json
{ "attribute": "<name>", "type": "<type>", "value": <value> }
```

Supported `attribute` / `type` / `value` combinations:

| attribute       | type          | value shape                                  | matches                                              |
|-----------------|---------------|----------------------------------------------|------------------------------------------------------|
| `runId`         | `number`      | `{ "value": 12345 }`                         | exact run id                                         |
| `workflowId`    | `number`      | `{ "value": 42 }`                            | exact agent (workflow) id                            |
| `campaignId`    | `number`      | `{ "value": 7 }`                             | exact campaign id                                    |
| `callerNumber`  | `text`        | `{ "value": "415555" }`                      | substring match on `initial_context.caller_number`   |
| `calledNumber`  | `text`        | `{ "value": "9911848" }`                     | substring match on `initial_context.called_number`   |
| `dispositionCode` | `multiSelect` | `{ "codes": ["XFER", "DNC"] }`             | any of the codes in `gathered_context.mapped_call_disposition` |
| `duration`      | `numberRange` | `{ "min": 60, "max": 300 }`                  | call duration (seconds), inclusive bounds            |
| `callDirection` | `radio`       | `{ "status": "inbound" }`                    | `inbound` or `outbound`; any other value matches all |
| `callChannel`   | `radio`       | `{ "status": "telephony" }`                  | `telephony`, `web`, or `chat` — the group of run modes for that channel |

Unknown attributes and unsupported `type` values are silently ignored.

Date filtering on this endpoint is done via the dedicated `start_date` / `end_date` query params, not via a `dateRange` filter object.
"""


@router.get("/usage/runs", response_model=UsageHistoryResponse)
async def get_usage_history(
    start_date: Optional[str] = Query(
        None,
        description="ISO 8601 date-time string (UTC). Lower bound (inclusive) on `created_at`.",
        examples=["2026-04-01T00:00:00Z"],
    ),
    end_date: Optional[str] = Query(
        None,
        description="ISO 8601 date-time string (UTC). Upper bound (inclusive) on `created_at`.",
        examples=["2026-05-01T00:00:00Z"],
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    filters: Optional[str] = Query(
        None,
        description=FILTERS_DESCRIPTION,
        examples=[
            '[{"attribute":"callerNumber","type":"text","value":{"value":"415555"}}]',
            '[{"attribute":"campaignId","type":"number","value":{"value":7}},'
            '{"attribute":"duration","type":"numberRange","value":{"min":60,"max":300}}]',
            '[{"attribute":"dispositionCode","type":"multiSelect","value":{"codes":["XFER","DNC"]}}]',
        ],
    ),
    sort_by: Optional[str] = Query(
        None,
        description="Field to sort by ('duration'). Defaults to `created_at`.",
        examples=["duration"],
    ),
    sort_order: str = Query(
        "desc",
        description="Sort order ('asc' or 'desc').",
        pattern="^(asc|desc)$",
    ),
    user: UserModel = Depends(get_user),
):
    """Get paginated workflow runs with usage for the organization."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    # Parse dates if provided
    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    # Parse filters if provided
    parsed_filters = None
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid filters format")

    try:
        offset = (page - 1) * limit
        (
            runs,
            total_count,
            total_tokens,
            total_duration,
        ) = await db_client.get_usage_history(
            user.selected_organization_id,
            start_date=start_dt,
            end_date=end_dt,
            limit=limit,
            offset=offset,
            filters=parsed_filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        total_pages = (total_count + limit - 1) // limit

        for run in runs:
            public_access_token = run.get("public_access_token")
            run["transcript_public_url"] = artifact_url(
                public_access_token, "transcript"
            )
            run["recording_public_url"] = artifact_url(public_access_token, "recording")
            run["user_recording_public_url"] = (
                artifact_url(public_access_token, "user_recording")
                if has_recording_track(run.get("extra"), "user")
                else None
            )
            run["bot_recording_public_url"] = (
                artifact_url(public_access_token, "bot_recording")
                if has_recording_track(run.get("extra"), "bot")
                else None
            )
            run.pop("extra", None)

        return {
            "runs": runs,
            "total_kodewaves_tokens": total_tokens,
            "total_dograh_tokens": total_tokens,
            "total_duration_seconds": total_duration,
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/runs/report")
async def download_usage_runs_report(
    start_date: Optional[str] = Query(
        None,
        description="ISO 8601 date-time string (UTC). Lower bound (inclusive) on `created_at`.",
    ),
    end_date: Optional[str] = Query(
        None,
        description="ISO 8601 date-time string (UTC). Upper bound (inclusive) on `created_at`.",
    ),
    filters: Optional[str] = Query(
        None,
        description=FILTERS_DESCRIPTION,
    ),
    user: UserModel = Depends(get_user),
) -> StreamingResponse:
    """Download a CSV of runs matching the same filters as `/usage/runs`."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    start_dt = datetime.fromisoformat(start_date) if start_date else None
    end_dt = datetime.fromisoformat(end_date) if end_date else None

    parsed_filters = None
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid filters format")

    output, filename = await generate_usage_runs_report_csv(
        user.selected_organization_id,
        start_date=start_dt,
        end_date=end_dt,
        filters=parsed_filters,
    )

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/usage/daily-breakdown", response_model=DailyUsageBreakdownResponse)
async def get_daily_usage_breakdown(
    days: int = Query(7, ge=1, le=30, description="Number of days to include"),
    user: UserModel = Depends(get_user),
):
    """Get daily usage breakdown for the last N days. Only available for organizations with pricing."""
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="No organization selected")

    try:
        # Get organization to check if it has pricing
        org = await db_client.get_organization_by_id(user.selected_organization_id)
        if not org or org.price_per_second_usd is None:
            raise HTTPException(
                status_code=400,
                detail="Daily breakdown is only available for organizations with pricing configured",
            )

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days - 1)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get daily breakdown
        breakdown = await db_client.get_daily_usage_breakdown(
            user.selected_organization_id,
            start_date,
            end_date,
            org.price_per_second_usd,
        )

        return breakdown
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
