"""Process-local handles for terminating live workflow call pipelines."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ActiveCallRuntime:
    runner: asyncio.Task | None
    org_id: str = ""
    engine: Any = None
    engine_ready: asyncio.Event = field(default_factory=asyncio.Event)
    termination_task: asyncio.Task | None = None
    shutdown_requested: bool = False


_runtimes: dict[int, ActiveCallRuntime] = {}


def register_active_runtime(run_id: int, org_id: str | int | None = None) -> None:
    """Register a call before async setup so a kill request cannot miss it."""
    current = _runtimes.get(run_id)
    if current is None:
        _runtimes[run_id] = ActiveCallRuntime(
            runner=asyncio.current_task(), org_id=str(org_id or "")
        )


def bind_active_engine(run_id: int, engine: Any) -> None:
    runtime = _runtimes.get(run_id)
    if runtime is None:
        return
    runtime.engine = engine
    runtime.engine_ready.set()


def unregister_active_runtime(run_id: int) -> None:
    runtime = _runtimes.pop(run_id, None)
    if runtime:
        runtime.engine_ready.set()


async def terminate_active_runtime(
    run_id: int, reason: str, *, timeout: float = 20.0
) -> dict[str, Any] | None:
    """End an owned live call and wait until its runner and transport finish.

    ``None`` means this worker does not own the requested call. Concurrent kill
    requests share one termination task, making the operation idempotent.
    """
    runtime = _runtimes.get(run_id)
    if runtime is None:
        return None
    if runtime.termination_task is None:
        runtime.termination_task = asyncio.create_task(
            _terminate_runtime(runtime, run_id, reason, timeout),
            name=f"admin-kill-call-{run_id}",
        )
    termination_task = runtime.termination_task
    try:
        result = await asyncio.shield(termination_task)
    except asyncio.TimeoutError:
        result = {"status": "timeout", "run_id": run_id}
    if result.get("status") != "terminated" and runtime.termination_task is termination_task:
        # A failed/timed-out attempt must not poison a later retry. Keep the
        # in-flight task intact while concurrent duplicate requests await it.
        if termination_task.done():
            runtime.termination_task = None
    return result


async def _terminate_runtime(
    runtime: ActiveCallRuntime, run_id: int, reason: str, timeout: float
) -> dict[str, Any]:
    try:
        async with asyncio.timeout(timeout):
            await runtime.engine_ready.wait()
            engine = runtime.engine
            runner = runtime.runner
            if engine is None or runner is None:
                return {"status": "inactive", "run_id": run_id}
            if runner.done():
                return {"status": "inactive", "run_id": run_id}

            await engine.end_call_with_reason(reason, abort_immediately=True)
            runtime.shutdown_requested = True
            if runner is not asyncio.current_task():
                await asyncio.shield(runner)
            return {"status": "terminated", "run_id": run_id}
    except TimeoutError:
        return {
            "status": (
                "shutdown_requested_unconfirmed"
                if runtime.shutdown_requested
                else "timeout"
            ),
            "run_id": run_id,
        }


async def handle_worker_termination(event: Any) -> dict[str, Any] | None:
    """Worker-sync handler; only the process owning this run acknowledges it."""
    if event.action != "terminate":
        return None
    payload = event.payload or {}
    try:
        run_id = int(payload["run_id"])
    except (KeyError, TypeError, ValueError):
        return None
    runtime = _runtimes.get(run_id)
    if runtime is None or (event.org_id and runtime.org_id != event.org_id):
        return {"status": "inactive", "run_id": run_id}
    return await terminate_active_runtime(
        run_id,
        str(payload.get("reason") or "Admin emergency kill switch triggered"),
    )
