import base64
import json
from unittest.mock import AsyncMock

import pytest

from api.services.telephony.providers.twilio.media_socket import (
    TwilioMediaSocket,
    _has_speech_energy,
    _mu_law_rms,
)


def media(audio):
    return json.dumps(
        {
            "event": "media",
            "streamSid": "MZtest",
            "media": {"payload": base64.b64encode(audio).decode()},
        }
    )


@pytest.mark.asyncio
async def test_first_audio_above_energy_threshold_marks_playback_and_keeps_order():
    ws = type("Socket", (), {"send_text": AsyncMock(), "client_state": "connected"})()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)
    await socket.send_text(media(bytes([255, 127]) * 80))
    assert len(ws.send_text.await_args_list) == 1
    await socket.send_text(media(bytes([23, 44]) * 80))
    await socket.send_text(media(bytes([25]) * 160))
    messages = [json.loads(c.args[0]) for c in ws.send_text.await_args_list]
    assert [m["event"] for m in messages] == ["media", "media", "mark", "media"]
    assert messages[2] == {
        "event": "mark",
        "streamSid": "MZtest",
        "mark": {"name": "kodewaves-first-audio-22"},
    }
    assert socket.client_state == "connected"


@pytest.mark.asyncio
async def test_mark_failure_does_not_interrupt_media_delivery():
    ws = type(
        "Socket",
        (),
        {"send_text": AsyncMock(side_effect=[None, RuntimeError("closed"), None])},
    )()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)
    await socket.send_text(media(bytes([22]) * 160))
    await socket.send_text(media(bytes([22]) * 160))
    assert ws.send_text.await_count == 3


@pytest.mark.asyncio
async def test_ack_requires_exact_stream_and_mark_and_preserves_message():
    ws = type("Socket", (), {"send_text": AsyncMock(), "receive": AsyncMock()})()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)
    await socket.send_text(media(bytes([23]) * 160))
    for sid, name in [("MZother", "kodewaves-first-audio-22"), ("MZtest", "other")]:
        ws.receive.return_value = {
            "type": "websocket.receive",
            "text": json.dumps(
                {"event": "mark", "streamSid": sid, "mark": {"name": name}}
            ),
        }
        await socket.receive()
        assert not socket._acknowledged
    message = {
        "type": "websocket.receive",
        "text": json.dumps(
            {
                "event": "mark",
                "streamSid": "MZtest",
                "mark": {"name": "kodewaves-first-audio-22"},
            }
        ),
    }
    ws.receive.return_value = message
    assert await socket.receive() == message
    assert socket._acknowledged


@pytest.mark.asyncio
async def test_receive_counts_inbound_audio_without_logging_audio_content():
    messages = [
        {"type": "websocket.receive", "text": media(bytes([255, 127]) * 80)},
        {"type": "websocket.receive", "text": media(bytes([23, 44]) * 80)},
    ]
    ws = type("Socket", (), {"receive": AsyncMock(side_effect=messages)})()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)

    assert await socket.receive() == messages[0]
    assert await socket.receive() == messages[1]

    assert socket._inbound_packets == 2
    assert socket._inbound_bytes == 320
    assert socket._inbound_speech_energy_packets == 1


def test_mu_law_energy_treats_both_silence_codes_and_quantization_as_silence():
    assert _mu_law_rms(bytes([0xFF, 0x7F]) * 80) == 0
    assert not _has_speech_energy(bytes([0xFF, 0x7F]) * 80)
    assert not _has_speech_energy(bytes([0xFE, 0x7E]) * 80)


def test_mu_law_energy_detects_telephone_voice_without_exposing_audio():
    speech = bytes(range(0x20, 0xC0))
    assert _has_speech_energy(speech)


@pytest.mark.asyncio
async def test_clear_is_not_reported_as_playback_proof():
    ws = type("Socket", (), {"send_text": AsyncMock()})()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)
    await socket.send_text(media(bytes([22]) * 160))
    await socket.send_text(json.dumps({"event": "clear", "streamSid": "MZtest"}))
    assert socket._cleared


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", ["[]", "not json", '{"event":"media","media":null}']
)
async def test_malformed_diagnostic_payload_is_passed_through(payload):
    ws = type("Socket", (), {"send_text": AsyncMock()})()
    socket = TwilioMediaSocket(ws, stream_sid="MZtest", workflow_run_id=22)
    await socket.send_text(payload)
    ws.send_text.assert_awaited_once_with(payload)
