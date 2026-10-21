import asyncio
from types import SimpleNamespace
import pytest
from pipecat.processors.filters.identity_filter import IdentityFilter
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor


@pytest.mark.asyncio
@pytest.mark.parametrize('content,realtime,should_expire', [('',False,False), ('recognized words',False,True), (None,True,True)])
async def test_empty_cascade_turn_does_not_await_an_inference_that_was_never_requested(content,realtime,should_expire):
    source = IdentityFilter()
    expired = asyncio.Event()
    monitor = CallMonitorProcessor(response_source=lambda: source,
        on_response_timeout=lambda _:expired.set(),
        on_user_idle=lambda _: asyncio.sleep(0), conversation_enabled=lambda:True,
        response_timeout=.025)
    monitor.bind_source(source,enabled=lambda:True)
    monitor.activate()
    monitor._user_started()
    monitor._user_stopped()  # Speaking frame precedes the complete message.
    assert monitor.pending_response
    monitor._user_stopped(SimpleNamespace(_realtime_service_mode=realtime),None,SimpleNamespace(content=content))
    await asyncio.sleep(.05)
    assert expired.is_set() is should_expire
    assert monitor.pending_response is should_expire
    monitor.close()


@pytest.mark.asyncio
async def test_empty_user_message_does_not_cancel_an_explicit_opening_request():
    source=IdentityFilter()
    expired=asyncio.Event()
    monitor=CallMonitorProcessor(response_source=lambda:source,
        on_response_timeout=lambda _:expired.set(),on_user_idle=lambda _:asyncio.sleep(0),
        conversation_enabled=lambda:True,response_timeout=.025)
    monitor.bind_source(source,enabled=lambda:True)
    monitor.activate();monitor.expect_response()
    monitor._user_started();monitor._user_stopped()
    monitor._user_stopped(SimpleNamespace(_realtime_service_mode=False),None,SimpleNamespace(content=None))
    await asyncio.sleep(.05)
    assert expired.is_set()
    monitor.close()
