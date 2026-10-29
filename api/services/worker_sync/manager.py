"""Worker sync manager for cross-worker state propagation.

Each FastAPI worker both publishes and listens on a single Redis pub/sub
channel.  When shared state changes (e.g. Langfuse credentials), the worker
that handled the mutation broadcasts a lightweight event.  Every worker
(including the sender) receives it and runs the registered handler, which
re-reads authoritative state from the DB.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Awaitable, Callable, Dict

import redis.asyncio as aioredis
from loguru import logger

from api.enums import RedisChannel
from api.services.worker_sync.protocol import WorkerSyncEvent

SyncHandler = Callable[[WorkerSyncEvent], Awaitable[Any]]


class WorkerSyncManager:
    """Propagates state changes across FastAPI workers via Redis pub/sub."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._handlers: Dict[str, SyncHandler] = {}
        self._worker_id = str(uuid.uuid4())
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._listener_task: asyncio.Task | None = None
        self._handler_tasks: set[asyncio.Task] = set()

    def register(self, event_type: str, handler: SyncHandler):
        """Register a handler for an event type. Call before start()."""
        self._handlers[event_type] = handler
        logger.info(f"Worker sync handler registered: {event_type}")

    async def broadcast(
        self,
        event_type: str,
        action: str,
        org_id: str = "",
        payload: dict[str, Any] | None = None,
    ):
        """Publish an event to all workers (including self)."""
        if not self._redis:
            logger.warning("WorkerSyncManager not started, skipping broadcast")
            return
        event = WorkerSyncEvent(
            event_type=event_type, action=action, org_id=org_id, payload=payload
        )
        await self._redis.publish(RedisChannel.WORKER_SYNC.value, event.to_json())
        logger.debug(f"Broadcast worker sync: {event_type}/{action} org={org_id}")

    async def request(
        self,
        event_type: str,
        action: str,
        org_id: str,
        payload: dict[str, Any],
        *,
        timeout: float = 5.0,
    ) -> dict[str, Any] | None:
        """Publish a command and wait for the owning worker's acknowledgement.

        The handler returns a result only on the worker that owns the resource.
        That worker writes the result to a short-lived Redis key, allowing the
        requester to distinguish an executed command from a pub/sub publish.
        """
        if not self._redis:
            raise RuntimeError("WorkerSyncManager is not started")
        request_id = str(uuid.uuid4())
        ack_key = f"worker-sync:ack:{request_id}"
        event = WorkerSyncEvent(
            event_type=event_type,
            action=action,
            org_id=org_id,
            payload={**payload, "request_id": request_id},
        )
        expected_workers = await self._redis.publish(
            RedisChannel.WORKER_SYNC.value, event.to_json()
        )
        if not expected_workers:
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            responses = await self._redis.hgetall(ack_key)
            decoded = []
            for result in responses.values():
                try:
                    item = json.loads(result)
                except (TypeError, ValueError):
                    continue
                if isinstance(item, dict):
                    decoded.append(item)
            # The live owner provides a definitive result. Return it without
            # waiting on stale or unrelated subscribers on the shared channel.
            for wanted in (
                "terminated",
                "shutdown_requested_unconfirmed",
                "timeout",
            ):
                for item in decoded:
                    if item.get("status") == wanted:
                        await self._redis.delete(ack_key)
                        return item
            if len(responses) >= expected_workers:
                await self._redis.delete(ack_key)
                return decoded[0] if decoded else None
            await asyncio.sleep(0.05)
        return None

    async def start(self):
        """Open a dedicated Redis connection and start the background listener."""
        self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(RedisChannel.WORKER_SYNC.value)
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("WorkerSyncManager started")

    async def stop(self):
        """Cancel the listener and close the Redis connection."""
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        for task in tuple(self._handler_tasks):
            task.cancel()
        if self._handler_tasks:
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)
        if self._pubsub:
            await self._pubsub.unsubscribe(RedisChannel.WORKER_SYNC.value)
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        logger.info("WorkerSyncManager stopped")

    async def _listen(self):
        """Background loop: receive events and dispatch to handlers."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                event = WorkerSyncEvent.from_json(message["data"])
                if not event:
                    continue
                handler = self._handlers.get(event.event_type)
                if handler:
                    if event.event_type == "call_termination":
                        task = asyncio.create_task(
                            self._dispatch(event, handler),
                            name=f"worker-sync-{event.event_type}",
                        )
                        self._handler_tasks.add(task)
                        task.add_done_callback(self._handler_tasks.discard)
                    else:
                        await self._dispatch(event, handler)
                else:
                    logger.warning(
                        f"No handler for worker sync event: {event.event_type}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker sync listener crashed")
            await asyncio.sleep(1.0)

    async def _dispatch(self, event: WorkerSyncEvent, handler: SyncHandler) -> None:
        try:
            result = await handler(event)
            request_id = (event.payload or {}).get("request_id")
            if request_id and result is not None and self._redis:
                await self._redis.hset(
                    f"worker-sync:ack:{request_id}",
                    self._worker_id,
                    json.dumps(result),
                )
                await self._redis.expire(f"worker-sync:ack:{request_id}", 30)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker sync handler error: {}", event.event_type)


# Module-level singleton, initialized in app lifespan
_manager: WorkerSyncManager | None = None


def get_worker_sync_manager() -> WorkerSyncManager:
    """Get the active WorkerSyncManager instance.

    Raises RuntimeError if called before the manager is started (i.e. outside
    the FastAPI lifespan).
    """
    if _manager is None:
        raise RuntimeError("WorkerSyncManager not initialized")
    return _manager


def set_worker_sync_manager(manager: WorkerSyncManager):
    """Set the module-level singleton. Called from the app lifespan."""
    global _manager
    _manager = manager
