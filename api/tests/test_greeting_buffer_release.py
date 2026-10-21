from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pipecat.frames.frames import Frame, VADUserStartedSpeakingFrame

from api.services.pipecat.greeting import GreetingController


@pytest.mark.asyncio
@pytest.mark.parametrize('speaking', [False, True])
async def test_completed_greeting_releases_buffered_short_reply(speaking):
    guard = SimpleNamespace(trigger_user_turn_started=AsyncMock())
    stop = SimpleNamespace(process_frame=AsyncMock())
    controller = SimpleNamespace(
        has_active_user_turn=False,
        user_turn_strategies=SimpleNamespace(start=[guard], stop=[stop]),
        update_strategies=AsyncMock(), force_user_turn_stop=AsyncMock(),
    )
    user = SimpleNamespace(user_turn_controller=controller, aggregation_string=lambda: 'हाँ')
    greeting = GreetingController(SimpleNamespace(greeting_pending=False), Mock())
    normal = SimpleNamespace(start=[])
    greeting._normal_strategies = normal
    onset = VADUserStartedSpeakingFrame() if speaking else None
    greeting._speech_start = onset

    await greeting._update_strategies(user, Frame())

    guard.trigger_user_turn_started.assert_awaited_once_with(enable_interruptions=False)
    controller.update_strategies.assert_awaited_once_with(normal)
    assert controller.force_user_turn_stop.await_count == (0 if speaking else 1)
    if speaking:
        stop.process_frame.assert_awaited_once_with(onset)


@pytest.mark.asyncio
@pytest.mark.parametrize('text,active', [('', False), ('हाँ', True)])
async def test_no_duplicate_or_empty_turn_after_greeting(text, active):
    guard = SimpleNamespace(trigger_user_turn_started=AsyncMock())
    controller = SimpleNamespace(
        has_active_user_turn=active,
        user_turn_strategies=SimpleNamespace(start=[guard], stop=[]),
        update_strategies=AsyncMock(), force_user_turn_stop=AsyncMock(),
    )
    greeting = GreetingController(SimpleNamespace(greeting_pending=False), Mock())
    greeting._normal_strategies = SimpleNamespace(start=[])
    user = SimpleNamespace(user_turn_controller=controller, aggregation_string=lambda: text)
    await greeting._update_strategies(user, Frame())
    guard.trigger_user_turn_started.assert_not_awaited()
    controller.force_user_turn_stop.assert_not_awaited()
