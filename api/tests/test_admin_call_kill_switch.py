"""Focused coverage for cross-worker admin termination of live calls."""

import asyncio
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.enums import RedisChannel, WorkflowRunState
from api.routes.admin import monitoring
from api.services.pipecat import active_runtime
from api.services.worker_sync.manager import WorkerSyncManager
from api.services.worker_sync.protocol import WorkerSyncEvent, WorkerSyncEventType


class FakeBus:
    def __init__(self):
        self.queues = defaultdict(list)
        self.values = {}

    def subscribe(self, channel):
        queue = asyncio.Queue()
        self.queues[channel].append(queue)
        return queue

    async def publish(self, channel, data):
        for queue in self.queues[channel]:
            await queue.put({"type": "message", "data": data})
        return len(self.queues[channel])


class FakePubSub:
    def __init__(self, bus):
        self.bus = bus
        self.queue = None

    async def subscribe(self, channel):
        self.queue = self.bus.subscribe(channel)

    async def listen(self):
        while True:
            yield await self.queue.get()

    async def unsubscribe(self, _channel):
        return None

    async def close(self):
        return None


class FakeRedis:
    def __init__(self, bus):
        self.bus = bus
        self.values = bus.values

    def pubsub(self):
        return FakePubSub(self.bus)

    async def publish(self, channel, data):
        return await self.bus.publish(channel, data)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def hset(self, key, field, value):
        self.values.setdefault(key, {})[field] = value

    async def hgetall(self, key):
        return dict(self.values.get(key, {}))

    async def expire(self, _key, _seconds):
        return True

    async def delete(self, key):
        self.values.pop(key, None)

    async def close(self):
        return None


async def _start_manager(bus, handler):
    manager = WorkerSyncManager("redis://unused")
    manager._redis = FakeRedis(bus)
    manager._pubsub = manager._redis.pubsub()
    await manager._pubsub.subscribe(RedisChannel.WORKER_SYNC.value)
    manager.register(WorkerSyncEventType.CALL_TERMINATION, handler)
    manager._listener_task = asyncio.create_task(manager._listen())
    return manager


@pytest.fixture(autouse=True)
def clear_runtime_registry():
    active_runtime._runtimes.clear()
    yield
    active_runtime._runtimes.clear()


@pytest.mark.asyncio
async def test_admin_kill_is_delivered_to_the_worker_owning_the_call():
    bus = FakeBus()
    # Simulate an old/unhandled subscriber on the channel. It must not block a
    # definitive result from the worker that owns the run.
    bus.subscribe(RedisChannel.WORKER_SYNC.value)
    idle_worker = await _start_manager(bus, active_runtime.handle_worker_termination)
    owner = await _start_manager(bus, active_runtime.handle_worker_termination)
    runner_ready = asyncio.Event()
    allow_runner_exit = asyncio.Event()

    class Engine:
        async def end_call_with_reason(self, reason, abort_immediately=False):
            assert reason == "admin kill"
            assert abort_immediately is True
            allow_runner_exit.set()

    async def run_call():
        active_runtime.register_active_runtime(42, "org-7")
        active_runtime.bind_active_engine(42, Engine())
        runner_ready.set()
        try:
            await allow_runner_exit.wait()
        finally:
            active_runtime.unregister_active_runtime(42)

    runner = asyncio.create_task(run_call())
    await runner_ready.wait()
    try:
        result = await idle_worker.request(
            WorkerSyncEventType.CALL_TERMINATION,
            "terminate",
            "org-7",
            {"run_id": 42, "reason": "admin kill"},
            timeout=0.5,
        )
        assert result == {"status": "terminated", "run_id": 42}
        assert runner.done()
    finally:
        await idle_worker.stop()
        await owner.stop()


@pytest.mark.asyncio
async def test_unhandled_subscriber_does_not_block_owner_ack():
    bus = FakeBus()
    bus.subscribe(RedisChannel.WORKER_SYNC.value)  # subscriber with no handler
    requester = await _start_manager(bus, active_runtime.handle_worker_termination)
    owner = await _start_manager(bus, active_runtime.handle_worker_termination)
    runner_ready = asyncio.Event()
    allow_runner_exit = asyncio.Event()

    class Engine:
        async def end_call_with_reason(self, _reason, abort_immediately=False):
            assert abort_immediately is True
            allow_runner_exit.set()

    async def run_call():
        active_runtime.register_active_runtime(46, "org-7")
        active_runtime.bind_active_engine(46, Engine())
        runner_ready.set()
        try:
            await allow_runner_exit.wait()
        finally:
            active_runtime.unregister_active_runtime(46)

    runner = asyncio.create_task(run_call())
    await runner_ready.wait()
    try:
        result = await requester.request(
            WorkerSyncEventType.CALL_TERMINATION,
            "terminate",
            "org-7",
            {"run_id": 46, "reason": "admin kill"},
            timeout=0.5,
        )
        assert result == {"status": "terminated", "run_id": 46}
        assert runner.done()
    finally:
        await requester.stop()
        await owner.stop()


@pytest.mark.asyncio
async def test_worker_sync_reports_no_active_owner_without_marking_any_run():
    bus = FakeBus()
    worker_a = await _start_manager(bus, active_runtime.handle_worker_termination)
    worker_b = await _start_manager(bus, active_runtime.handle_worker_termination)
    try:
        result = await worker_a.request(
            WorkerSyncEventType.CALL_TERMINATION,
            "terminate",
            "org-7",
            {"run_id": 404, "reason": "admin kill"},
            timeout=0.5,
        )
        assert result == {"status": "inactive", "run_id": 404}
    finally:
        await worker_a.stop()
        await worker_b.stop()


@pytest.mark.asyncio
async def test_unconfirmed_shutdown_is_reported_and_does_not_cancel_call_runner():
    runner_ready = asyncio.Event()
    allow_runner_exit = asyncio.Event()

    class Engine:
        async def end_call_with_reason(self, _reason, abort_immediately=False):
            assert abort_immediately is True

    async def run_call():
        active_runtime.register_active_runtime(43, "org-7")
        active_runtime.bind_active_engine(43, Engine())
        runner_ready.set()
        try:
            await allow_runner_exit.wait()
        finally:
            active_runtime.unregister_active_runtime(43)

    runner = asyncio.create_task(run_call())
    await runner_ready.wait()
    result = await active_runtime.terminate_active_runtime(
        43, "admin kill", timeout=0.01
    )
    assert result == {"status": "shutdown_requested_unconfirmed", "run_id": 43}
    assert not runner.done()
    allow_runner_exit.set()
    await runner


@pytest.mark.asyncio
async def test_kill_during_pipeline_setup_waits_for_engine_binding():
    runner_ready = asyncio.Event()
    allow_runner_exit = asyncio.Event()

    class Engine:
        async def end_call_with_reason(self, _reason, abort_immediately=False):
            assert abort_immediately is True
            allow_runner_exit.set()

    async def run_call():
        active_runtime.register_active_runtime(44, "org-7")
        runner_ready.set()
        try:
            await allow_runner_exit.wait()
        finally:
            active_runtime.unregister_active_runtime(44)

    runner = asyncio.create_task(run_call())
    await runner_ready.wait()
    kill = asyncio.create_task(
        active_runtime.terminate_active_runtime(44, "admin kill", timeout=0.5)
    )
    await asyncio.sleep(0)
    assert not kill.done()
    active_runtime.bind_active_engine(44, Engine())
    assert await kill == {"status": "terminated", "run_id": 44}
    assert runner.done()


@pytest.mark.asyncio
async def test_failed_termination_attempt_does_not_poison_a_retry():
    runner_ready = asyncio.Event()
    allow_runner_exit = asyncio.Event()

    class Engine:
        calls = 0

        async def end_call_with_reason(self, _reason, abort_immediately=False):
            assert abort_immediately is True
            self.calls += 1
            allow_runner_exit.set()

    engine = Engine()

    async def run_call():
        active_runtime.register_active_runtime(45, "org-7")
        active_runtime.bind_active_engine(45, engine)
        runner_ready.set()
        try:
            await allow_runner_exit.wait()
        finally:
            active_runtime.unregister_active_runtime(45)

    runner = asyncio.create_task(run_call())
    await runner_ready.wait()
    runtime = active_runtime._runtimes[45]

    async def failed_attempt():
        return {"status": "timeout", "run_id": 45}

    runtime.termination_task = asyncio.create_task(failed_attempt())
    assert await active_runtime.terminate_active_runtime(45, "admin kill") == {
        "status": "timeout",
        "run_id": 45,
    }
    assert runtime.termination_task is None
    assert await active_runtime.terminate_active_runtime(45, "admin kill") == {
        "status": "terminated",
        "run_id": 45,
    }
    assert engine.calls == 1
    assert runner.done()


@pytest.mark.asyncio
async def test_completed_run_is_not_reported_as_killed_again(monkeypatch):
    run = SimpleNamespace(
        id=51,
        is_completed=True,
        state=WorkflowRunState.COMPLETED.value,
        organization_id="org-7",
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: run)

    monkeypatch.setattr(monitoring.kodewaves_db_client, "get_session", lambda: Session())
    manager_request = AsyncMock()
    monkeypatch.setattr(monitoring, "get_worker_sync_manager", lambda: SimpleNamespace(request=manager_request))
    with pytest.raises(HTTPException) as error:
        await monitoring._terminate_call(51, "admin kill")
    assert error.value.status_code == 409
    manager_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("worker_result", "expected_status"),
    [
        ({"status": "inactive", "run_id": 52}, 409),
        ({"status": "shutdown_requested_unconfirmed", "run_id": 52}, 503),
    ],
)
async def test_unconfirmed_or_inactive_worker_never_marks_run_complete(
    monkeypatch, worker_result, expected_status
):
    run = SimpleNamespace(
        id=52,
        is_completed=False,
        state=WorkflowRunState.RUNNING.value,
        organization_id="org-7",
        logs={},
    )
    commits = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: run)

        async def commit(self):
            commits.append(True)

    monkeypatch.setattr(monitoring.kodewaves_db_client, "get_session", lambda: Session())
    manager_request = AsyncMock(return_value=worker_result)
    monkeypatch.setattr(
        monitoring,
        "get_worker_sync_manager",
        lambda: SimpleNamespace(request=manager_request),
    )
    with pytest.raises(HTTPException) as error:
        await monitoring._terminate_call(52, "admin kill")
    assert error.value.status_code == expected_status
    assert run.is_completed is False
    assert run.state == WorkflowRunState.RUNNING.value
    assert commits == []
