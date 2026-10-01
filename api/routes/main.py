from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel

from api.constants import ENVIRONMENT
from api.routes import (
    agent_auth,
    ai_model_configurations,
    analytics,
    appointments,
    auth,
    billing,
    billing_sovereign,
    campaign,
    client_credentials,
    credentials,
    crm,
    custom_events,
    document,
    folders,
    forms,
    inbound_telephony,
    knowledge_base,
    mcp,
    messages,
    organization,
    organization_usage,
    outbound_telephony,
    payments,
    prompt_templates,
    public_agent,
    public_embed,
    recordings,
    reports,
    service_keys,
    sip_inbound,
    speech,
    superuser,
    telephony,
    tool,
    transcription,
    user,
    webrtc_signaling,
    widgets,
    workflow,
    workflow_embed,
    workflow_evals,
    workflow_run,
)
from api.routes.admin import (
    audit_logs as admin_audit_logs,
    credit_packages as admin_credit_packages,
    master_keys as admin_master_keys,
    models as admin_models,
    moderation as admin_moderation,
    monitoring as admin_monitoring,
    plans as admin_plans,
    settings as admin_settings,
    users as admin_users,
)

router = APIRouter()

router.include_router(agent_auth.router, prefix="/api/v1/auth/agent")
router.include_router(auth.router, prefix="/api/v1/auth")
router.include_router(billing_sovereign.router, prefix="/api/v1/billing/sovereign")
router.include_router(payments.router, prefix="/api/v1/payments")
router.include_router(client_credentials.router, prefix="/api/v1/client-credentials")
router.include_router(custom_events.router, prefix="/api/v1/custom-events")
router.include_router(document.router, prefix="/api/v1/documents")
router.include_router(folders.router, prefix="/api/v1/folders")
router.include_router(forms.router, prefix="/api/v1/forms")
router.include_router(inbound_telephony.router, prefix="/api/v1/telephony")
router.include_router(knowledge_base.router, prefix="/api/v1/knowledge-bases")
router.include_router(messages.router, prefix="/api/v1/messages")
router.include_router(organization.router, prefix="/api/v1/organizations")
router.include_router(organization_usage.router, prefix="/api/v1/organization-usage")
router.include_router(outbound_telephony.router, prefix="/api/v1/telephony")
router.include_router(public_agent.router, prefix="/api/v1/agents")
router.include_router(public_embed.router, prefix="/api/v1/embed")
router.include_router(recordings.router, prefix="/api/v1/workflow/recordings")
router.include_router(service_keys.router, prefix="/api/v1/service-keys")
router.include_router(sip_inbound.router, prefix="/api/v1/telephony")
router.include_router(speech.router, prefix="/api/v1/speech")
router.include_router(telephony.router, prefix="/api/v1/telephony")
router.include_router(transcription.router, prefix="/api/v1/speech")
router.include_router(user.router, prefix="/api/v1/user")
router.include_router(webrtc_signaling.router, prefix="/api/v1/webrtc")
router.include_router(widgets.router, prefix="/api/v1/widgets")
router.include_router(workflow_embed.router, prefix="/api/v1/workflow/embed")
router.include_router(workflow_evals.router, prefix="/api/v1/workflow")
router.include_router(workflow_run.router, prefix="/api/v1/workflow")
router.include_router(workflow.router, prefix="/api/v1/workflow")
router.include_router(analytics.router, prefix="/api/v1/analytics")
router.include_router(crm.router, prefix="/api/v1/crm")
router.include_router(reports.router, prefix="/api/v1/reports")
router.include_router(prompt_templates.router, prefix="/api/v1/prompt-templates")
router.include_router(appointments.router, prefix="/api/v1/appointments")
router.include_router(campaign.router, prefix="/api/v1/campaign")
router.include_router(ai_model_configurations.router, prefix="/api/v1/model-configurations")
router.include_router(superuser.router, prefix="/api/v1/superuser")
router.include_router(credentials.router, prefix="/api/v1/credentials")
router.include_router(tool.router, prefix="/api/v1/tools")
router.include_router(mcp.router, prefix="/api/v1/mcp")

# Sovereign SaaS Admin Routes
router.include_router(admin_users.router, prefix="/api/v1/admin/users")
router.include_router(admin_plans.router, prefix="/api/v1/admin/plans")
router.include_router(admin_credit_packages.router, prefix="/api/v1/admin/credit-packages")
router.include_router(admin_models.router, prefix="/api/v1/admin/models")
router.include_router(admin_moderation.router, prefix="/api/v1/admin/moderation")
router.include_router(admin_monitoring.router, prefix="/api/v1/admin/monitoring")
router.include_router(admin_settings.router, prefix="/api/v1/admin/settings")
router.include_router(admin_audit_logs.router, prefix="/api/v1/admin/audit-logs")
router.include_router(admin_master_keys.router, prefix="/api/v1/admin/master-keys")

if ENVIRONMENT == "development":
    from api.routes import dev
    router.include_router(dev.router, prefix="/api/v1/dev")

if ENVIRONMENT != "production":
    from api.routes import local_eval
    router.include_router(local_eval.router, prefix="/api/v1/local-eval")

from api.services.integrations.registry import get_integration_provider
_noveum_provider = get_integration_provider("noveum")
if _noveum_provider and _noveum_provider.router:
    router.include_router(_noveum_provider.router, prefix="/api/v1/integrations/noveum")


@router.get("/")
def read_root():
    return {"status": "ok", "platform": "kodewaves"}


class ActiveCallsResponse(BaseModel):
    active_calls: int
    loop_lag_p95_ms: float
    loop_lag_max_ms: float


class AutoscaleMetricResponse(BaseModel):
    value: int


KODEWAVES_DEVOPS_SECRET_HEADER = "X-Kodewaves-Devops-Secret"
DOGRAH_DEVOPS_SECRET_HEADER = "X-Dograh-Devops-Secret"


def _verify_devops_secret(
    configured_secret: str | None,
    provided_secret: str | None,
) -> None:
    if not configured_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Devops secret is not configured",
        )
    if not provided_secret or not secrets.compare_digest(
        provided_secret,
        configured_secret,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


@router.get("/health/active-calls", response_model=ActiveCallsResponse)
async def active_calls(
    x_kodewaves_devops_secret: Annotated[
        str | None,
        Header(alias=KODEWAVES_DEVOPS_SECRET_HEADER),
    ] = None,
    x_dograh_devops_secret: Annotated[
        str | None,
        Header(alias=DOGRAH_DEVOPS_SECRET_HEADER),
    ] = None,
) -> ActiveCallsResponse:
    from api.constants import KODEWAVES_DEVOPS_SECRET, DOGRAH_DEVOPS_SECRET
    from api.services.observability import loop_lag
    from api.services.observability.active_calls import active_call_count

    secret = KODEWAVES_DEVOPS_SECRET or DOGRAH_DEVOPS_SECRET
    provided = x_kodewaves_devops_secret or x_dograh_devops_secret
    _verify_devops_secret(secret, provided)
    lag = loop_lag.stats()
    return ActiveCallsResponse(
        active_calls=active_call_count(),
        loop_lag_p95_ms=lag["p95_ms"],
        loop_lag_max_ms=lag["max_ms"],
    )


@router.get("/health/autoscale-metric", response_model=AutoscaleMetricResponse)
async def autoscale_metric(
    buffer: int = 0,
    x_kodewaves_devops_secret: Annotated[
        str | None,
        Header(alias=KODEWAVES_DEVOPS_SECRET_HEADER),
    ] = None,
    x_dograh_devops_secret: Annotated[
        str | None,
        Header(alias=DOGRAH_DEVOPS_SECRET_HEADER),
    ] = None,
) -> AutoscaleMetricResponse:
    from api.constants import KODEWAVES_DEVOPS_SECRET, DOGRAH_DEVOPS_SECRET
    from api.services.call_concurrency import call_concurrency

    secret = KODEWAVES_DEVOPS_SECRET or DOGRAH_DEVOPS_SECRET
    provided = x_kodewaves_devops_secret or x_dograh_devops_secret
    _verify_devops_secret(secret, provided)
    try:
        calls = await call_concurrency.get_fleet_active_calls()
    except Exception as e:
        logger.error(f"Fleet active-call count unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fleet call count unavailable",
        )
    return AutoscaleMetricResponse(value=calls + max(0, buffer))


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(
    x_kodewaves_devops_secret: Annotated[
        str | None,
        Header(alias=KODEWAVES_DEVOPS_SECRET_HEADER),
    ] = None,
    x_dograh_devops_secret: Annotated[
        str | None,
        Header(alias=DOGRAH_DEVOPS_SECRET_HEADER),
    ] = None,
) -> Response:
    from api.constants import KODEWAVES_DEVOPS_SECRET, DOGRAH_DEVOPS_SECRET
    from api.services.observability.metrics import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=404, detail="Metrics are disabled")
    secret = KODEWAVES_DEVOPS_SECRET or DOGRAH_DEVOPS_SECRET
    provided = x_kodewaves_devops_secret or x_dograh_devops_secret
    _verify_devops_secret(secret, provided)
    return Response(
        content=runtime.render(),
        media_type="text/plain; version=0.0.4",
    )
