"""Workflow-run billing hooks.

Kodewaves does not rate or deduct credits locally. MPS owns credit accounting.
For hosted deployments, Kodewaves reports completed platform usage to MPS.
When a server-minted MPS correlation id exists, MPS uses model-service usage
as the canonical duration. Otherwise Kodewaves reports the completed run duration.
"""

from typing import Any

from loguru import logger

from api.constants import DEPLOYMENT_MODE
from api.db import db_client
from api.enums import WorkflowRunMode
from api.services.managed_model_services import get_mps_correlation_id
from api.services.mps_service_key_client import mps_service_key_client


def _workflow_run_organization_id(workflow_run) -> int | None:
    workflow = getattr(workflow_run, "workflow", None)
    return getattr(workflow, "organization_id", None)


def _duration_seconds_from_usage_info(workflow_run) -> float | None:
    usage_info: dict[str, Any] = getattr(workflow_run, "usage_info", None) or {}
    duration = usage_info.get("call_duration_seconds")
    try:
        if duration is not None:
            duration_seconds = float(duration)
            if duration_seconds > 0:
                return duration_seconds
    except (TypeError, ValueError):
        pass

    # Fallback to started_at and ended_at timestamps if available
    started_at = getattr(workflow_run, "started_at", None)
    ended_at = getattr(workflow_run, "ended_at", None)
    if started_at and ended_at:
        try:
            delta = (ended_at - started_at).total_seconds()
            if delta > 0:
                return delta
        except Exception:
            pass

    return None



def _is_usage_not_ready_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) != 409:
        return False
    return "usage_not_ready" in (getattr(response, "text", "") or "")


async def report_workflow_run_platform_usage(workflow_run) -> None:
    """Report platform usage for a completed workflow run and deduct minutes from local wallet."""
    if getattr(workflow_run, "mode", None) == WorkflowRunMode.TEXTCHAT.value:
        logger.info(
            "Skipping platform usage report for text chat workflow run {}",
            workflow_run.id,
        )
        return

    if not getattr(workflow_run, "is_completed", False):
        logger.warning(
            "Workflow run is not completed in report_workflow_run_platform_usage"
        )
        return

    organization_id = _workflow_run_organization_id(workflow_run)
    if organization_id is None:
        logger.warning(
            "Skipping platform usage report for workflow run {}: no organization_id",
            workflow_run.id,
        )
        return

    duration_seconds = _duration_seconds_from_usage_info(workflow_run)
    if duration_seconds is None:
        logger.warning(
            "Skipping platform usage report for workflow run {}: no billable duration",
            workflow_run.id,
        )
        return

    init_ctx = getattr(workflow_run, "initial_context", {}) or {}
    gath_ctx = getattr(workflow_run, "gathered_context", {}) or {}

    # Invariant (Part 8): Admin test calls are free
    if init_ctx.get("is_admin_test") or gath_ctx.get("is_admin_test"):
        logger.info(
            f"[KodewavesBilling] Run {workflow_run.id} is an admin test call — 0 minutes charged"
        )
        return

    # Invariant (Part 8): 100% Local sovereign calls are free
    usage_info = getattr(workflow_run, "usage_info", None) or {}
    res_info = usage_info.get("resolution_info") or init_ctx.get("resolution_info") or gath_ctx.get("resolution_info") or {}
    if (
        getattr(workflow_run, "mode", None) == "local"
        or init_ctx.get("is_local")
        or gath_ctx.get("is_local")
        or init_ctx.get("source") == "local"
        or res_info.get("overall_source") == "local"
    ):
        logger.info(
            f"[KodewavesBilling] Run {workflow_run.id} is a sovereign local call — 0 minutes charged"
        )
        return

    try:
        # Local Kodewaves Sovereign Wallet Deduction
        from api.db.kodewaves_client import kodewaves_db_client

        billable_secs = duration_seconds or 0.0
        if billable_secs > 0:
            base_minutes = max(1, int((billable_secs + 59) // 60))

            # Invariant (Part 8): S2S rate as an admin setting
            is_s2s = (
                getattr(workflow_run, "mode", None) == "s2s"
                or init_ctx.get("is_realtime")
                or init_ctx.get("mode") == "s2s"
            )
            multiplier = 1.0
            if is_s2s:
                pricing_settings = await kodewaves_db_client.get_setting("pricing") or {}
                try:
                    multiplier = float(pricing_settings.get("s2s_multiplier", 1.0) or 1.0)
                except (ValueError, TypeError):
                    multiplier = 1.0

            billable_minutes = max(1, int(round(base_minutes * multiplier)))
            reason = "s2s_call_usage" if is_s2s else "call_usage"

            await kodewaves_db_client.deduct_minutes(
                organization_id=organization_id,
                minutes=billable_minutes,
                reason=reason,
                reference_id=str(workflow_run.id),
            )
            logger.info(
                f"[KodewavesBilling] Deducted {billable_minutes} minute(s) (s2s={is_s2s}, mult={multiplier}) for run {workflow_run.id} from org {organization_id}"
            )
    except Exception as e:
        logger.error(
            f"[KodewavesBilling] Error updating local wallet for run {workflow_run.id}: {e}"
        )


async def report_completed_workflow_run_platform_usage(workflow_run_id: int) -> None:
    """Load a completed workflow run and report platform usage to MPS."""
    workflow_run = await db_client.get_workflow_run_by_id(workflow_run_id)
    if not workflow_run:
        logger.warning(
            "Skipping platform usage report: workflow run {} not found",
            workflow_run_id,
        )
        return

    await report_workflow_run_platform_usage(workflow_run)
