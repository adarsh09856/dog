import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from loguru import logger
from pydantic import BaseModel

from api.routes.agent_stream import router as agent_stream_router
from api.routes.auth import router as auth_router
from api.routes.campaign import router as campaign_router
from api.routes.credentials import router as credentials_router
from api.routes.folder import router as folder_router
from api.routes.knowledge_base import router as knowledge_base_router
from api.routes.node_types import router as node_types_router
from api.routes.organization import router as organization_router
from api.routes.organization_usage import router as organization_usage_router
from api.routes.public_agent import router as public_agent_router
from api.routes.public_download import router as public_download_router
from api.routes.public_embed import router as public_embed_router
from api.routes.public_embed_chat import router as public_embed_chat_router
from api.routes.reports import router as reports_router
from api.routes.s3_signed_url import router as s3_router
from api.routes.service_keys import router as service_keys_router
from api.routes.admin import admin_router
from api.routes.catalog import router as catalog_router
from api.routes.appointments import router as appointments_router
from api.routes.billing_sovereign import router as billing_sovereign_router
from api.routes.crm import router as crm_router
from api.routes.forms import router as forms_router
from api.routes.payments import router as payments_router
from api.routes.prompt_templates import router as prompt_templates_router
from api.routes.widgets import router as widgets_router
from api.routes.superuser import router as superuser_router
from api.routes.telephony import router as telephony_router
from api.routes.tool import router as tool_router
from api.routes.tts_cache import router as tts_cache_router
from api.routes.turn_credentials import router as turn_credentials_router
from api.routes.user import router as user_router
from api.routes.webrtc_signaling import router as webrtc_signaling_router
from api.routes.workflow import router as workflow_router
from api.routes.workflow_embed import router as workflow_embed_router
from api.routes.workflow_recording import router as workflow_recording_router
from api.routes.workflow_text_chat import router as workflow_text_chat_router
from api.services.integrations import all_routers

router = APIRouter(
    tags=["main"],
    responses={404: {"description": "Not found"}},
)

router.include_router(admin_router)
router.include_router(catalog_router)
router.include_router(crm_router)
router.include_router(appointments_router)
router.include_router(forms_router)
router.include_router(widgets_router)
router.include_router(prompt_templates_router)
router.include_router(billing_sovereign_router)
router.include_router(payments_router)
router.include_router(telephony_router)
router.include_router(superuser_router)
router.include_router(workflow_router)
router.include_router(workflow_text_chat_router)
router.include_router(user_router)
router.include_router(campaign_router)
router.include_router(credentials_router)
router.include_router(tool_router)
router.include_router(organization_router)
router.include_router(s3_router)
router.include_router(service_keys_router)
router.include_router(organization_usage_router)
router.include_router(reports_router)
router.include_router(webrtc_signaling_router)
router.include_router(turn_credentials_router)
router.include_router(public_embed_router)
router.include_router(public_embed_chat_router)
router.include_router(public_agent_router)
router.include_router(public_download_router)
router.include_router(workflow_embed_router)
router.include_router(knowledge_base_router)
router.include_router(workflow_recording_router)
router.include_router(tts_cache_router)
router.include_router(folder_router)
router.include_router(auth_router)
router.include_router(node_types_router)
router.include_router(agent_stream_router)

for _integration_router in all_routers():
    router.include_router(_integration_router)


@router.get("/")
def read_root():
    return {"status": "ok", "platform": "kodewaves"}


class HealthResponse(BaseModel):
    status: str
    version: str
    backend_api_endpoint: str
    tunnel_url: str | None = None
    deployment_mode: str
    auth_provider: str
    turn_enabled: bool
    force_turn_relay: bool
    signup_enabled: bool
    stack_project_id: str | None = None
    stack_publishable_client_key: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from api.constants import (
        APP_VERSION,
        AUTH_PROVIDER,
        BACKEND_API_ENDPOINT,
        DEPLOYMENT_MODE,
        ENABLE_COTURN,
        ENABLE_SIGNUP,
        FORCE_TURN_RELAY,
        STACK_AUTH_PROJECT_ID,
        STACK_PUBLISHABLE_CLIENT_KEY,
    )
    from api.utils.common import get_backend_endpoints, is_local_or_private_url

    backend_endpoint, _ = await get_backend_endpoints()
    tunnel_url = (
        backend_endpoint
        if is_local_or_private_url(BACKEND_API_ENDPOINT)
        and not is_local_or_private_url(backend_endpoint)
        else None
    )
    is_stack = AUTH_PROVIDER == "stack"
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        backend_api_endpoint=BACKEND_API_ENDPOINT,
        tunnel_url=tunnel_url,
        deployment_mode=DEPLOYMENT_MODE,
        auth_provider=AUTH_PROVIDER,
        turn_enabled=ENABLE_COTURN,
        force_turn_relay=FORCE_TURN_RELAY,
        signup_enabled=ENABLE_SIGNUP,
        stack_project_id=STACK_AUTH_PROJECT_ID if is_stack else None,
        stack_publishable_client_key=(
            STACK_PUBLISHABLE_CLIENT_KEY if is_stack else None
        ),
    )


class ActiveCallsResponse(BaseModel):
    active_calls: int
    loop_lag_p95_ms: float = 0.0
    loop_lag_max_ms: float = 0.0


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
    from api.constants import DOGRAH_DEVOPS_SECRET, KODEWAVES_DEVOPS_SECRET
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
    from api.constants import DOGRAH_DEVOPS_SECRET, KODEWAVES_DEVOPS_SECRET
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
    from api.constants import DOGRAH_DEVOPS_SECRET, KODEWAVES_DEVOPS_SECRET
    from api.services.observability.metrics import get_runtime

    runtime = get_runtime()
    if runtime is None:
        raise HTTPException(status_code=404, detail="Metrics are disabled")
    secret = KODEWAVES_DEVOPS_SECRET or DOGRAH_DEVOPS_SECRET
    provided = x_kodewaves_devops_secret or x_dograh_devops_secret
    _verify_devops_secret(secret, provided)
    from prometheus_client import CONTENT_TYPE_LATEST

    return Response(
        content=runtime.render(),
        headers={"Content-Type": CONTENT_TYPE_LATEST, "Cache-Control": "no-store"},
    )
