import asyncio
import time
from dataclasses import dataclass

from fastapi import HTTPException
from loguru import logger

from api.constants import DEFAULT_ORG_CONCURRENCY_LIMIT, KODEWAVES_EDITION
from api.db import db_client
from api.enums import OrganizationConfigurationKey, PostHogEvent
from api.services.call_concurrency.rate_limiter import rate_limiter
from api.services.installation_license import (
    InstallationLicenseError,
    load_license,
    require_feature,
    require_limit,
    validate_installation_license,
)
from api.services.owner_installation_status import require_current_owner_status
from api.services.posthog_client import capture_event
from api.services.saas_entitlements import enforce_saas_feature, get_org_saas_limit


def _licensed_call_limit(source: str) -> int | None:
    """Load signed client entitlements for every new call admission."""
    if KODEWAVES_EDITION != "client":
        return None
    license_data = load_license()
    validate_installation_license(license_data)
    require_feature(license_data, "voice")
    if source.startswith("campaign:"):
        require_feature(license_data, "campaigns")
        require_feature(license_data, "telephony")
    elif source.startswith(("inbound:", "inbound_legacy:", "telephony_", "agent_stream:")) or source in {
        "ari_inbound",
        "public_agent",
    }:
        require_feature(license_data, "telephony")
    elif source == "public_embed":
        require_feature(license_data, "widgets")
    return require_limit(license_data, "max_concurrent_calls")


async def authorize_call_entitlement(
    source: str, *, organization_id: int | None = None
) -> int | None:
    """Recheck a client's call grant and owner status immediately before dialing."""
    if organization_id is not None:
        feature = (
            "campaigns" if source.startswith("campaign:")
            else "widgets" if source == "public_embed"
            else None
        )
        if feature:
            try:
                await enforce_saas_feature(organization_id, feature)
            except HTTPException as exc:
                raise CallConcurrencyLimitError(
                    organization_id=organization_id, source=source,
                    wait_time=0.0, max_concurrent=0,
                ) from exc
    try:
        client_max = _licensed_call_limit(source)
        if client_max is not None:
            await require_current_owner_status(load_license())
    except InstallationLicenseError as exc:
        logger.warning("Client installation license denied new call: {}", exc)
        raise
    return client_max


@dataclass(frozen=True)
class CallConcurrencySlot:
    organization_id: int
    slot_id: str
    max_concurrent: int
    source: str
    scope_key: str | None = None


class CallConcurrencyLimitError(Exception):
    """Raised when an org has no available concurrent call slots."""

    def __init__(
        self,
        *,
        organization_id: int,
        source: str,
        wait_time: float,
        max_concurrent: int,
    ):
        self.organization_id = organization_id
        self.source = source
        self.wait_time = wait_time
        self.max_concurrent = max_concurrent
        super().__init__(
            f"Concurrent call limit reached for org {organization_id} "
            f"(source={source}, limit={max_concurrent}, waited={wait_time:.1f}s)"
        )


class WorkflowRunSlotAlreadyBoundError(Exception):
    """Raised when a workflow run already owns a concurrent call slot."""

    def __init__(self, workflow_run_id: int):
        self.workflow_run_id = workflow_run_id
        super().__init__(
            f"Workflow run {workflow_run_id} already has an active call slot"
        )


class CallConcurrencyService:
    def __init__(self):
        self.default_concurrent_limit = int(DEFAULT_ORG_CONCURRENCY_LIMIT)

    async def get_org_concurrent_limit(
        self, organization_id: int, *, include_saas_plan: bool = True
    ) -> int:
        """Get the concurrent call limit for an organization."""
        limits: list[int] = []
        if include_saas_plan and KODEWAVES_EDITION != "client":
            # Plan lookup is an entitlement check. Do not silently fall back to a
            # larger platform default if the entitlement store is unavailable.
            limit = await get_org_saas_limit(organization_id, "max_concurrent_calls")
            if limit is not None:
                limits.append(limit)

        try:
            config = await db_client.get_configuration(
                organization_id,
                OrganizationConfigurationKey.CONCURRENT_CALL_LIMIT.value,
            )
            if config and config.value:
                value = config.value.get("value")
                if value is not None:
                    limits.append(max(0, int(value)))
        except Exception as e:
            logger.warning(
                f"Error getting concurrent limit for org {organization_id}: {e}"
            )

        if not limits:
            try:
                from api.db.kodewaves_client import kodewaves_db_client

                conc_setting = await kodewaves_db_client.get_setting("concurrency") or {}
                value = conc_setting.get("default_org_concurrency_limit")
                if value is not None:
                    limits.append(max(0, int(value)))
            except Exception:
                pass
            if not limits:
                limits.append(self.default_concurrent_limit)
        return min(limits)

    async def get_fleet_active_calls(self) -> int:
        """Total active calls across every org — the fleet-wide autoscaling
        signal scraped by /health/autoscale-metric. Thin passthrough so routes
        stay behind this facade; the Redis projection lives with the key schema
        in rate_limiter. Redis errors propagate (they must not read as an idle
        fleet — see get_fleet_concurrent_count)."""
        return await rate_limiter.get_fleet_concurrent_count()

    async def is_workflow_run_active(self, workflow_run_id: int) -> bool:
        """Whether a run still has a live fleet slot for admin monitoring."""
        return await rate_limiter.is_workflow_run_active(workflow_run_id)

    async def get_org_active_calls(self, organization_id: int) -> int:
        """Occupied org slots across workers, with storage failures propagated.

        Includes reservations made before a voice pipeline starts. Uses the
        same stale-slot expiry as concurrency enforcement.
        """
        return await rate_limiter.get_concurrent_count(
            organization_id, raise_on_error=True
        )

    async def acquire_org_slot(
        self,
        organization_id: int,
        *,
        source: str,
        timeout: float = 0,
        scope_key: str | None = None,
        scope_max_concurrent: int | None = None,
        retry_interval: float = 1,
    ) -> CallConcurrencySlot:
        """Acquire a slot in the org-wide concurrency counter.

        ``scope_key``/``scope_max_concurrent`` additionally bound a secondary
        counter (e.g. ``campaign:<id>``) so a source can cap its own
        concurrency without measuring — or being starved by — unrelated calls
        in the same org.
        """
        try:
            client_max = await authorize_call_entitlement(
                source, organization_id=organization_id
            )
        except InstallationLicenseError as exc:
            raise CallConcurrencyLimitError(
                organization_id=organization_id,
                source=source,
                wait_time=0.0,
                max_concurrent=0,
            ) from exc
        # Enforce fleet-wide platform limit
        try:
            from api.db.kodewaves_client import kodewaves_db_client
            conc_setting = await kodewaves_db_client.get_setting("concurrency")
            fleet_max = int(conc_setting.get("max_concurrent_calls", 50)) if conc_setting else 50
        except Exception:
            fleet_max = 50
        if client_max is not None:
            fleet_max = min(fleet_max, client_max)

        try:
            fleet_count = await self.get_fleet_active_calls()
            if fleet_count >= fleet_max:
                logger.warning(
                    f"Platform fleet-wide concurrent call limit reached: active={fleet_count}/{fleet_max}"
                )
                raise CallConcurrencyLimitError(
                    organization_id=organization_id,
                    source=source,
                    wait_time=0.0,
                    max_concurrent=fleet_max,
                )
        except CallConcurrencyLimitError:
            raise
        except Exception as e:
            if client_max is not None:
                logger.warning("Client installation fleet admission is unavailable: {}", e)
                raise CallConcurrencyLimitError(
                    organization_id=organization_id,
                    source=source,
                    wait_time=0.0,
                    max_concurrent=fleet_max,
                ) from e
            logger.debug(f"Fleet active count check skipped: {e}")

        # Enforce local AI concurrency limit if local source
        if source == "local" and scope_key is None:
            scope_key = "local_engine"
            try:
                from api.db.kodewaves_client import kodewaves_db_client
                local_setting = await kodewaves_db_client.get_setting("local_ai") or {}
                scope_max_concurrent = int(local_setting.get("local_ai_max_concurrency", 2))
            except Exception:
                scope_max_concurrent = 2

        max_concurrent = await self.get_org_concurrent_limit(
            organization_id, include_saas_plan=client_max is None
        )
        if client_max is not None:
            max_concurrent = min(max_concurrent, client_max)
        if scope_max_concurrent is not None:
            scope_max_concurrent = int(scope_max_concurrent)

        wait_start = time.time()
        while True:
            admission_kwargs = {
                "scope_key": scope_key,
                "scope_max_concurrent": scope_max_concurrent,
            }
            if client_max is not None:
                admission_kwargs["fleet_max_concurrent"] = fleet_max
            acquisition = await rate_limiter.try_acquire_concurrent_slot_details(
                organization_id,
                max_concurrent,
                **admission_kwargs,
            )
            if acquisition:
                logger.info(
                    f"Acquired concurrent call slot for org {organization_id}: "
                    f"source={source}, active_calls="
                    f"{acquisition.active_count}/{max_concurrent}, "
                    f"slot_id={acquisition.slot_id}"
                )
                return CallConcurrencySlot(
                    organization_id=organization_id,
                    slot_id=acquisition.slot_id,
                    max_concurrent=max_concurrent,
                    source=source,
                    scope_key=scope_key,
                )

            wait_time = time.time() - wait_start
            if wait_time >= timeout:
                current_count = await rate_limiter.get_concurrent_count(organization_id)
                scope_note = (
                    f", scope={scope_key} (limit={scope_max_concurrent})"
                    if scope_key
                    else ""
                )
                logger.warning(
                    f"Concurrent call limit reached for org {organization_id}: "
                    f"source={source}, active_calls={current_count}/{max_concurrent}"
                    f"{scope_note}, waited={wait_time:.1f}s"
                )
                properties = {
                    "event_source": "kodewaves",
                    "organization_id": organization_id,
                    "source": source,
                    "max_concurrent": max_concurrent,
                    "active_calls": current_count,
                    "waited_seconds": round(wait_time, 1),
                }
                if scope_key:
                    properties["scope_key"] = scope_key
                    properties["scope_max_concurrent"] = scope_max_concurrent
                await self._notify_limit_reached(organization_id, properties)
                raise CallConcurrencyLimitError(
                    organization_id=organization_id,
                    source=source,
                    wait_time=wait_time,
                    max_concurrent=max_concurrent,
                )

            logger.debug(
                f"Waiting for concurrent call slot for org {organization_id}, "
                f"source={source}, waited {wait_time:.1f}s"
            )
            await asyncio.sleep(min(retry_interval, max(0, timeout - wait_time)))

    async def _notify_limit_reached(
        self, organization_id: int, properties: dict
    ) -> None:
        """Fan the usage event out to every org member's provider_id, matching
        how MPS emits org-scoped billing events (billing_posthog_service.py)
        into the shared PostHog project. Never raises.

        NOTE: intentionally NOT attaching ``$groups`` (organization) to this
        event. PostHog evaluates a $groups event at both person and group
        scope, which double-triggers person-scoped workflows enrolled on the
        event. The org is still available as the ``organization_id`` property.
        """
        try:
            members = await db_client.get_organization_users(organization_id)
            if not members:
                logger.debug(
                    f"No users found for org {organization_id}; skipping "
                    "concurrent-call-limit PostHog event"
                )
                return
            for member in members:
                capture_event(
                    distinct_id=str(member.provider_id),
                    event=PostHogEvent.USAGE_CONCURRENT_CALL_LIMIT_REACHED,
                    properties=properties,
                )
        except Exception:
            logger.exception(
                "Failed to send concurrent-call-limit PostHog event for org "
                f"{organization_id}"
            )

    async def bind_workflow_run(
        self, slot: CallConcurrencySlot, workflow_run_id: int
    ) -> None:
        stored = await rate_limiter.store_workflow_slot_mapping_if_absent(
            workflow_run_id,
            slot.organization_id,
            slot.slot_id,
            scope_key=slot.scope_key,
        )
        if stored:
            return

        await self.release_slot(slot)
        raise WorkflowRunSlotAlreadyBoundError(workflow_run_id)

    async def register_active_call(
        self,
        organization_id: int,
        workflow_run_id: int,
        *,
        source: str,
        timeout: float = 0,
        scope_key: str | None = None,
        scope_max_concurrent: int | None = None,
        retry_interval: float = 1,
    ) -> CallConcurrencySlot:
        slot = await self.acquire_org_slot(
            organization_id,
            source=source,
            timeout=timeout,
            scope_key=scope_key,
            scope_max_concurrent=scope_max_concurrent,
            retry_interval=retry_interval,
        )
        await self.bind_workflow_run(slot, workflow_run_id)
        return slot

    async def unregister_active_call(self, workflow_run_id: int) -> bool:
        """Release the run's slot without ever raising.

        Callers invoke this from ``finally`` blocks during pipeline/socket
        teardown; a cleanup failure must not mask the original exception.
        The slot mapping survives a failed release, so a later cleanup path
        (status callback, StasisEnd) or the Redis stale timeout recovers it.
        """
        try:
            return await self.release_workflow_run_slot(workflow_run_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                f"Failed to release concurrent call slot for workflow run "
                f"{workflow_run_id}: {e}"
            )
            return False

    async def release_slot(self, slot: CallConcurrencySlot | None) -> bool:
        if slot is None:
            return False
        released = await rate_limiter.release_concurrent_slot(
            slot.organization_id, slot.slot_id, scope_key=slot.scope_key
        )
        return bool(released)

    async def release_workflow_run_slot(self, workflow_run_id: int) -> bool:
        """Release the org/campaign slot held by a workflow run."""
        mapping = await rate_limiter.get_workflow_slot_mapping(workflow_run_id)
        if not mapping:
            return False

        org_id, slot_id, scope_key = mapping
        released = await rate_limiter.release_concurrent_slot(
            org_id, slot_id, scope_key=scope_key
        )
        if released is None:
            # Redis error while releasing — keep the mapping so a later
            # cleanup path can retry instead of orphaning a live slot until
            # the stale timeout.
            logger.warning(
                f"Failed to release concurrent slot for workflow run "
                f"{workflow_run_id}; keeping mapping for retry"
            )
            return False
        await rate_limiter.delete_workflow_slot_mapping(workflow_run_id)
        if released:
            logger.info(f"Released concurrent slot for workflow run {workflow_run_id}")
        else:
            logger.debug(
                f"Concurrent slot mapping for workflow run {workflow_run_id} "
                "had no live slot; deleted stale mapping"
            )
        return released


call_concurrency = CallConcurrencyService()
