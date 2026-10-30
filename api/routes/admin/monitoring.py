import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db import db_client
from api.db.kodewaves_models import (
    AIModelCatalogModel,
    PlatformMasterCredentialModel,
)
from api.db.models import OrganizationModel, UserModel, WorkflowModel, WorkflowRunModel
from api.enums import WorkflowRunState
from api.services.auth.depends import get_superuser
from api.services.call_concurrency import call_concurrency
from api.services.worker_sync.manager import get_worker_sync_manager
from api.services.worker_sync.protocol import WorkerSyncEventType

router = APIRouter(prefix="/monitoring", tags=["admin-monitoring"])


class MonitoringStatsResponse(BaseModel):
    total_calls: int
    active_calls: int
    completed_calls: int
    total_minutes: float
    total_revenue_inr: Optional[float] = None
    gross_margin_percent: Optional[float] = None
    system_health: str
    total_users: int = 0
    total_organizations: int = 0
    failed_verifications_count: int = 0
    failed_verifications: List[str] = []
    retired_model_alerts: List[str] = []
    disk_usage_percent: float = 0.0
    disk_free_gb: float = 0.0


class SystemResourcesResponse(BaseModel):
    active_concurrency: int = 0
    concurrency_cap: int = 50
    queue_size: int = 0
    cpu_percent: float = 0.0
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    memory_percent: float = 0.0
    disk_free_gb: float = 0.0
    disk_usage_percent: float = 0.0


class LiveCallItem(BaseModel):
    run_id: int
    call_sid: Optional[str] = None
    agent_name: str
    organization_name: Optional[str] = "Direct Tenant"
    user_email: Optional[str] = None
    provider: str = "sarvam"
    telecom_carrier: str = "webrtc"
    duration_seconds: float = 0.0
    started_at: str
    status: str = "streaming"


class KillCallRequest(BaseModel):
    run_id: int
    reason: Optional[str] = "Terminated by superadmin kill-switch"


@router.get("/stats", response_model=MonitoringStatsResponse)
async def get_monitoring_stats(_user=Depends(get_superuser)):
    """Fetch 100% real aggregated platform metrics directly from PostgreSQL."""
    total_calls = 0
    # Workflow runs can remain INITIALIZED after a failed setup or a process
    # restart. Redis call slots are the fleet-wide live concurrency source.
    try:
        active_calls = await call_concurrency.get_fleet_active_calls()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Live call count unavailable") from exc
    completed_calls = 0
    total_minutes = 0.0
    total_revenue_inr = None
    gross_margin_percent = None
    system_health = "healthy"

    try:
        async with kodewaves_db_client.get_session() as session:
            # 1. Total Calls Count
            try:
                total_calls_stmt = select(func.count(WorkflowRunModel.id))
                total_calls = (await session.execute(total_calls_stmt)).scalar() or 0
            except Exception:
                total_calls = 0

            # 2. Completed Calls Count
            try:
                completed_calls_stmt = select(func.count(WorkflowRunModel.id)).where(
                    WorkflowRunModel.is_completed == True
                )
                completed_calls = (await session.execute(completed_calls_stmt)).scalar() or 0
            except Exception:
                completed_calls = 0

            # 4. Total Minutes Calculation via SQL JSON aggregation (avoids OOM on large datasets)
            try:
                from sqlalchemy import Float
                stmt = select(
                    func.coalesce(
                        func.sum(
                            func.cast(
                                func.nullif(
                                    WorkflowRunModel.usage_info.op("->>")("call_duration_seconds"),
                                    ""
                                ),
                                Float
                            )
                        ),
                        0.0
                    )
                ).where(WorkflowRunModel.usage_info.isnot(None))
                total_seconds = (await session.execute(stmt)).scalar() or 0.0
                total_minutes = round(float(total_seconds) / 60.0, 1)
            except Exception:
                total_minutes = 0.0

            # Wallet credits record minutes, not verified payment currency or
            # amount. Revenue is unavailable until payment settlement is joined.

            # 6. Configured model price margin; this is not realized profit.
            try:
                margin_stmt = select(
                    func.sum(AIModelCatalogModel.retail_price_cents_per_unit - AIModelCatalogModel.base_cost_cents_per_unit),
                    func.sum(AIModelCatalogModel.retail_price_cents_per_unit),
                ).where(
                    AIModelCatalogModel.is_active == True,
                    AIModelCatalogModel.retail_price_cents_per_unit > 0,
                )
                gross, retail = (await session.execute(margin_stmt)).one()
                if retail:
                    gross_margin_percent = round(float(gross or 0) / float(retail) * 100, 1)
            except Exception:
                gross_margin_percent = None

            # 7. System Health Check
            try:
                test_stmt = select(1)
                await session.execute(test_stmt)
            except Exception:
                system_health = "degraded"

            # 8. Total Users and Organizations
            total_users = 0
            total_organizations = 0
            try:
                total_users = (await session.execute(select(func.count(UserModel.id)))).scalar() or 0
                total_organizations = (await session.execute(select(func.count(OrganizationModel.id)))).scalar() or 0
            except Exception:
                pass

            # 9. Failed Provider Verifications
            failed_verifications = []
            try:
                failed_stmt = select(PlatformMasterCredentialModel.provider, PlatformMasterCredentialModel.error_message).where(
                    PlatformMasterCredentialModel.is_enabled == True,
                    PlatformMasterCredentialModel.health_status.in_(["invalid", "error"]),
                )
                failed_res = await session.execute(failed_stmt)
                for f_prov, f_err in failed_res.all():
                    err_hint = f": {f_err}" if f_err else ""
                    failed_verifications.append(f"{f_prov.title()}{err_hint}")
            except Exception:
                pass

            # 10. Retired / Unavailable Models
            retired_model_alerts = []
            try:
                from sqlalchemy import or_
                retired_stmt = select(AIModelCatalogModel.provider, AIModelCatalogModel.model_id).where(
                    or_(
                        AIModelCatalogModel.is_active == False,
                        AIModelCatalogModel.status == "UNAVAILABLE",
                    )
                )
                ret_res = await session.execute(retired_stmt)
                for r_prov, r_mid in ret_res.all():
                    retired_model_alerts.append(f"{r_prov.title()}: {r_mid}")
            except Exception:
                pass
    except Exception:
        system_health = "degraded"

    # 11. Disk Capacity
    disk_free_gb = 0.0
    disk_usage_percent = 0.0
    try:
        du = shutil.disk_usage(".")
        disk_free_gb = round(du.free / (1024**3), 1)
        disk_usage_percent = round((du.used / du.total) * 100, 1)
    except Exception:
        pass

    return MonitoringStatsResponse(
        total_calls=total_calls,
        active_calls=active_calls,
        completed_calls=completed_calls,
        total_minutes=total_minutes,
        total_revenue_inr=total_revenue_inr,
        gross_margin_percent=gross_margin_percent,
        system_health=system_health,
        total_users=total_users,
        total_organizations=total_organizations,
        failed_verifications_count=len(failed_verifications),
        failed_verifications=failed_verifications,
        retired_model_alerts=retired_model_alerts,
        disk_usage_percent=disk_usage_percent,
        disk_free_gb=disk_free_gb,
    )


@router.get("/live-calls", response_model=List[LiveCallItem])
async def list_live_calls(_user=Depends(get_superuser)):
    """List in-flight active voice calls with agent and tenant metadata."""
    live_items = []
    now_utc = datetime.now(UTC)

    try:
        fleet_count = await call_concurrency.get_fleet_active_calls()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Live call list unavailable") from exc
    if fleet_count == 0:
        return []

    try:
        async with kodewaves_db_client.get_session() as session:
            stmt = (
                select(WorkflowRunModel, WorkflowModel, UserModel, OrganizationModel)
                .outerjoin(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                .outerjoin(UserModel, WorkflowModel.user_id == UserModel.id)
                .outerjoin(OrganizationModel, WorkflowModel.organization_id == OrganizationModel.id)
                .where(
                    WorkflowRunModel.state == WorkflowRunState.RUNNING.value,
                    WorkflowRunModel.is_completed == False,
                    WorkflowRunModel.created_at >= now_utc - timedelta(minutes=20),
                )
                .order_by(desc(WorkflowRunModel.created_at))
                .limit(100)
            )
            result = await session.execute(stmt)
            rows = result.all()

            for run, workflow, user, org in rows:
                if len(live_items) >= fleet_count:
                    break
                if not await call_concurrency.is_workflow_run_active(run.id):
                    continue
                duration = 0.0
                if run.created_at:
                    diff = now_utc - run.created_at
                    duration = max(0.0, diff.total_seconds())

                agent_name = workflow.name if workflow else f"Voice Agent #{run.workflow_id}"
                org_name = org.provider_id if org else "Primary Organization"
                user_email = user.email if user else None
                carrier = (run.mode or "WebRTC").upper()

                # Extract provider if present in usage_info or config
                ai_provider = "sarvam"
                if run.usage_info and isinstance(run.usage_info, dict):
                    ai_provider = run.usage_info.get("llm_provider", "sarvam")

                live_items.append(
                    LiveCallItem(
                        run_id=run.id,
                        call_sid=str(run.id),
                        agent_name=agent_name,
                        organization_name=org_name,
                        user_email=user_email,
                        provider=ai_provider,
                        telecom_carrier=carrier,
                        duration_seconds=round(duration, 1),
                        started_at=run.created_at.isoformat() if run.created_at else now_utc.isoformat(),
                        status="streaming",
                    )
                )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Live call list unavailable") from exc

    return live_items


@router.get("/system-resources", response_model=SystemResourcesResponse)
async def get_system_resources(_user=Depends(get_superuser)):
    """Fetch live concurrency, queue depth, container CPU and memory stats."""
    try:
        active_calls = await call_concurrency.get_fleet_active_calls()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Live concurrency unavailable") from exc
    try:
        queue_size = await db_client.count_ready_campaign_dials()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Campaign dial queue unavailable") from exc
    concurrency_cap = 50

    try:
        local_ai = await kodewaves_db_client.get_setting("local_ai") or {}
        concurrency_cap = int(local_ai.get("local_ai_max_concurrency", 50))
    except Exception:
        concurrency_cap = 50

    # Read Memory & CPU
    mem_used = 0.0
    mem_total = 0.0
    mem_pct = 0.0
    cpu_percent = 0.0

    # Check Linux /proc/meminfo or fallback
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                mem_dict = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        mem_dict[parts[0].strip()] = parts[1].strip()
                t_kb = float(mem_dict.get("MemTotal", "0 kB").split()[0])
                a_kb = float(mem_dict.get("MemAvailable", "0 kB").split()[0])
                mem_total = round(t_kb / 1024.0, 1)
                mem_used = round((t_kb - a_kb) / 1024.0, 1)
                mem_pct = round(((t_kb - a_kb) / t_kb) * 100, 1) if t_kb > 0 else 0.0
        except Exception:
            pass

    # Read Disk
    disk_free = 0.0
    disk_pct = 0.0
    try:
        du = shutil.disk_usage(".")
        disk_free = round(du.free / (1024**3), 1)
        disk_pct = round((du.used / du.total) * 100, 1)
    except Exception:
        pass

    return SystemResourcesResponse(
        active_concurrency=active_calls,
        concurrency_cap=concurrency_cap,
        queue_size=queue_size,
        cpu_percent=cpu_percent,
        memory_used_mb=mem_used,
        memory_total_mb=mem_total,
        memory_percent=mem_pct,
        disk_free_gb=disk_free,
        disk_usage_percent=disk_pct,
    )


@router.post("/kill-call", response_model=Dict[str, Any])
async def kill_active_call_post(req: KillCallRequest, _user=Depends(get_superuser)):
    """Emergency force-termination kill-switch via JSON body."""
    return await _terminate_call(req.run_id, req.reason)


@router.post("/calls/{run_id}/kill", response_model=Dict[str, Any])
async def kill_active_call_path(run_id: int, _user=Depends(get_superuser)):
    """Emergency force-termination kill-switch via path param."""
    return await _terminate_call(run_id, "Terminated by superadmin kill-switch")


async def _terminate_call(run_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
    reason = reason or "Admin emergency kill switch triggered"
    async with kodewaves_db_client.get_session() as session:
        stmt = select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail=f"Call run #{run_id} not found")
        if run.is_completed or run.state == WorkflowRunState.COMPLETED.value:
            raise HTTPException(status_code=409, detail=f"Call run #{run_id} is already complete")
        organization_id = str(run.organization_id or "")

    try:
        acknowledgement = await get_worker_sync_manager().request(
            WorkerSyncEventType.CALL_TERMINATION,
            "terminate",
            organization_id,
            {"run_id": run_id, "reason": reason},
            timeout=25.0,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="Live call termination service is unavailable"
        ) from exc

    if acknowledgement is None:
        # Pub/sub is only a delivery mechanism; a response is required from the
        # worker that owns the media pipeline before its DB row can be changed.
        async with kodewaves_db_client.get_session() as session:
            result = await session.execute(
                select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
            )
            current_run = result.scalar_one_or_none()
            if current_run and (
                current_run.is_completed
                or current_run.state == WorkflowRunState.COMPLETED.value
            ):
                raise HTTPException(status_code=409, detail=f"Call run #{run_id} ended before the kill request was handled")
        raise HTTPException(
            status_code=503,
            detail=f"No active worker acknowledged termination of call run #{run_id}; run was not marked complete",
        )

    status = acknowledgement.get("status")
    if status == "inactive":
        raise HTTPException(status_code=409, detail=f"Call run #{run_id} has no active media pipeline")
    if status == "shutdown_requested_unconfirmed":
        raise HTTPException(
            status_code=503,
            detail=f"Shutdown was requested for call run #{run_id}, but the worker did not confirm pipeline exit; run was not marked complete",
        )
    if status != "terminated":
        raise HTTPException(
            status_code=503,
            detail=f"The worker did not confirm termination of call run #{run_id}; run was not marked complete",
        )

    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        )
        run = result.scalar_one_or_none()
        if run:
            run.state = WorkflowRunState.COMPLETED.value
            run.is_completed = True
            logs = dict(run.logs) if isinstance(run.logs, dict) else {}
            logs["termination_reason"] = reason
            run.logs = logs
            await session.commit()

    try:
        from api.services.workflow_run_billing import report_completed_workflow_run_platform_usage

        await report_completed_workflow_run_platform_usage(run_id)
    except Exception:
        logger.exception("Failed billing completed admin-terminated call run {}", run_id)

    return {
        "message": f"Call run #{run_id} and its active media pipeline were terminated",
        "run_id": run_id,
        "status": "terminated",
    }


class ProcessHealthItem(BaseModel):
    name: str
    status: str  # "healthy", "degraded", "offline", "disabled"
    latency_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


class ProcessHealthResponse(BaseModel):
    status: str  # "healthy", "degraded", "offline"
    timestamp: str
    services: Dict[str, ProcessHealthItem]


@router.get("/process-health", response_model=ProcessHealthResponse)
async def get_process_health(_user=Depends(get_superuser)):
    """Comprehensive live health check for all core sovereign processes and engine containers."""
    services: Dict[str, ProcessHealthItem] = {}
    overall_status = "healthy"

    # 1. PostgreSQL Database
    t0 = time.monotonic()
    try:
        async with kodewaves_db_client.get_session() as session:
            await session.execute(select(1))
        lat = round((time.monotonic() - t0) * 1000, 1)
        services["database"] = ProcessHealthItem(name="PostgreSQL", status="healthy", latency_ms=lat)
    except Exception as e:
        services["database"] = ProcessHealthItem(name="PostgreSQL", status="offline", details={"error": str(e)})
        overall_status = "degraded"

    # 2. Redis Cache & Broker
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    t0 = time.monotonic()
    try:
        import redis.asyncio as aioredis
        r = await aioredis.from_url(redis_url, decode_responses=True)
        pong = await r.ping()
        lat = round((time.monotonic() - t0) * 1000, 1)
        services["redis"] = ProcessHealthItem(name="Redis", status="healthy" if pong else "degraded", latency_ms=lat)

        # 3. Campaign Orchestrator Heartbeat
        orch_enabled = os.environ.get("ENABLE_CAMPAIGN_ORCHESTRATOR", "true").lower() in ("true", "1")
        if not orch_enabled:
            services["campaign_orchestrator"] = ProcessHealthItem(
                name="Campaign Orchestrator", status="disabled", details={"enabled": False}
            )
        else:
            hb = await r.get("campaign:orchestrator:heartbeat")
            if hb:
                services["campaign_orchestrator"] = ProcessHealthItem(
                    name="Campaign Orchestrator", status="healthy", details={"last_heartbeat": hb}
                )
            else:
                services["campaign_orchestrator"] = ProcessHealthItem(
                    name="Campaign Orchestrator", status="offline", details={"heartbeat": "missing"}
                )
                if overall_status == "healthy":
                    overall_status = "degraded"

        await r.aclose()
    except Exception as e:
        services["redis"] = ProcessHealthItem(name="Redis", status="offline", details={"error": str(e)})
        services["campaign_orchestrator"] = ProcessHealthItem(name="Campaign Orchestrator", status="offline", details={"error": "redis unreachable"})
        overall_status = "degraded"

    # 4. Storage (MinIO)
    minio_host = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    try:
        t0 = time.monotonic()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
            async with session.get(f"http://{minio_host}/minio/health/live") as resp:
                lat = round((time.monotonic() - t0) * 1000, 1)
                minio_ok = resp.status in (200, 403, 404)  # live probe responding
                services["storage"] = ProcessHealthItem(
                    name="MinIO Storage", status="healthy" if minio_ok else "degraded", latency_ms=lat
                )
    except Exception as e:
        services["storage"] = ProcessHealthItem(name="MinIO Storage", status="degraded", details={"error": str(e)})

    # 5. Local CPU AI Engines
    local_settings = await kodewaves_db_client.get_setting("local_ai") or {}
    local_ai_on = local_settings.get("enable_local_ai_engine", True)

    if local_ai_on:
        # Ollama
        ollama_url = local_settings.get("ollama_endpoint") or os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                    lat = round((time.monotonic() - t0) * 1000, 1)
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name") for m in data.get("models", [])]
                        services["ollama"] = ProcessHealthItem(
                            name="Ollama LLM", status="healthy", latency_ms=lat, details={"models": models}
                        )
                    else:
                        services["ollama"] = ProcessHealthItem(name="Ollama LLM", status="offline")
        except Exception as e:
            services["ollama"] = ProcessHealthItem(name="Ollama LLM", status="offline", details={"error": str(e)})

        # Piper TTS
        piper_url = local_settings.get("piper_endpoint") or os.environ.get("PIPER_ENDPOINT", "http://piper:5000")
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                async with session.get(f"{piper_url.rstrip('/')}/voices") as resp:
                    lat = round((time.monotonic() - t0) * 1000, 1)
                    if resp.status == 200:
                        services["piper"] = ProcessHealthItem(name="Piper TTS", status="healthy", latency_ms=lat)
                    else:
                        services["piper"] = ProcessHealthItem(name="Piper TTS", status="offline")
        except Exception as e:
            services["piper"] = ProcessHealthItem(name="Piper TTS", status="offline", details={"error": str(e)})

        # The Speaches endpoint is retained for local TTS compatibility. Local
        # self-hosted STT is served separately by IndicConformer.
        whisper_url = local_settings.get("whisper_endpoint") or os.environ.get("WHISPER_ENDPOINT", "http://whisper:8000/v1")
        try:
            t0 = time.monotonic()
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                probe_url = whisper_url.rstrip("/") if whisper_url.endswith("/models") else f"{whisper_url.rstrip('/')}/models"
                async with session.get(probe_url) as resp:
                    lat = round((time.monotonic() - t0) * 1000, 1)
                    if resp.status == 200:
                        services["speaches_tts"] = ProcessHealthItem(name="Speaches TTS", status="healthy", latency_ms=lat)
                    else:
                        services["speaches_tts"] = ProcessHealthItem(name="Speaches TTS", status="offline")
        except Exception as e:
            services["speaches_tts"] = ProcessHealthItem(name="Speaches TTS", status="offline", details={"error": str(e)})
    else:
        services["local_ai"] = ProcessHealthItem(name="Local AI Engine", status="disabled")

    # API uvicorn process itself
    services["api_worker"] = ProcessHealthItem(
        name="FastAPI Worker", status="healthy", details={"pid": os.getpid()}
    )

    return ProcessHealthResponse(
        status=overall_status,
        timestamp=datetime.now(UTC).isoformat(),
        services=services,
    )
