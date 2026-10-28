import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pipecat.processors.filters.identity_filter import IdentityFilter
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.pipecat.speaches_stt import BoundedSpeachesSTTService


@pytest.mark.asyncio
@pytest.mark.parametrize('accepted', [False, True])
async def test_idle_waits_for_recognition_and_respects_accepted_turn(accepted):
    source = IdentityFilter()
    idle = asyncio.Event()
    async def notify(_attempt):
        idle.set()
    monitor = CallMonitorProcessor(
        response_source=lambda: source, on_response_timeout=Mock(),
        on_user_idle=notify, conversation_enabled=lambda: True,
    )
    monitor.bind_source(source, enabled=lambda: True)
    monitor.user_aggregator = SimpleNamespace(
        user_turn_controller=SimpleNamespace(has_active_user_turn=False),
        remove_event_handler=lambda *args: None,
    )
    monitor.user_aggregator.user_turn_controller.remove_event_handler = lambda *args: None
    monitor.user_idle_timeout = .01
    pending = True
    monitor.recognition_pending = lambda: pending
    monitor.activate(waiting_for_user=True)
    await asyncio.sleep(.04)
    assert not idle.is_set()
    assert monitor._retry_count == 0
    pending = False
    if accepted:
        monitor._user_started()
    await asyncio.sleep(.3)
    assert idle.is_set() is not accepted
    monitor.close()


def test_local_recognition_pending_includes_work_and_queue():
    fake = SimpleNamespace(_recognizing_segment=False, _user_speaking=False,
                           _segment_queue=asyncio.Queue())
    pending = BoundedSpeachesSTTService.recognition_pending.fget
    assert not pending(fake)
    fake._recognizing_segment = True
    assert pending(fake)
    fake._recognizing_segment = False
    fake._segment_queue.put_nowait(b'audio')
    assert pending(fake)
