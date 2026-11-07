"""Persist terminal telephony calls to the contact timeline when matched."""

from typing import Any

from loguru import logger

from api.db import db_client


async def record_terminal_call_history(
    *,
    workflow_run_id: int,
    organization_id: int | None,
    initial_context: dict[str, Any] | None,
    call_type: str | None,
    direction: str | None = None,
    caller_number: str | None = None,
    called_number: str | None = None,
    outcome: str = "completed",
) -> bool:
    """Match a call to its customer number and record it once, if present."""
    if organization_id is None:
        return False

    context = initial_context or {}
    direction = str(direction or context.get("direction") or call_type or "outbound").lower()
    caller = caller_number or context.get("caller_number")
    called = called_number or context.get("called_number")
    if direction == "inbound":
        contact_phone = caller
    else:
        contact_phone = called

    if not contact_phone:
        return False

    direction_label = "Inbound" if direction == "inbound" else "Outbound"
    summary = f"{direction_label} call {outcome.replace('_', ' ')}"
    try:
        return await db_client.record_crm_call_activity(
            organization_id=organization_id,
            contact_phone=str(contact_phone),
            workflow_run_id=workflow_run_id,
            summary=summary,
        )
    except Exception:
        logger.exception("Could not record CRM call history for workflow run {}", workflow_run_id)
        return False
