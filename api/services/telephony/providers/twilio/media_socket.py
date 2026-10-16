"""Observe call audio delivery and media flow without recording audio content."""

import base64
import json
import time

from loguru import logger


class TwilioMediaSocket:
    """Delegate the socket while checking delivery through Twilio's mark protocol."""

    def __init__(self, websocket, *, stream_sid: str, workflow_run_id: int):
        self._websocket = websocket
        self._stream_sid = stream_sid
        self._run_id = workflow_run_id
        self._mark_name = f"kodewaves-first-audio-{workflow_run_id}"
        self._sent_at = None
        self._acknowledged = False
        self._cleared = False
        self._inbound_packets = 0
        self._inbound_bytes = 0
        self._inbound_non_silent_packets = 0

    def __getattr__(self, name):
        return getattr(self._websocket, name)

    async def send_text(self, data: str):
        await self._websocket.send_text(data)
        try:
            message = json.loads(data)
        except (ValueError, TypeError):
            return
        if not isinstance(message, dict):
            return
        if message.get("event") == "clear" and self._sent_at is not None:
            self._cleared = True
        if self._sent_at is not None or message.get("event") != "media":
            return
        try:
            audio = base64.b64decode(message["media"]["payload"], validate=True)
        except (KeyError, ValueError, TypeError):
            return
        # Both mu-law zero encodings occur in silence; do not count idle mixer output.
        if not any(sample not in (0xFF, 0x7F) for sample in audio):
            return
        self._sent_at = time.monotonic()
        logger.info(
            "[run {}] First non-silent Twilio media sent ({} mu-law bytes)",
            self._run_id,
            len(audio),
        )
        try:
            await self._websocket.send_text(
                json.dumps(
                    {
                        "event": "mark",
                        "streamSid": self._stream_sid,
                        "mark": {"name": self._mark_name},
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001 — diagnostics must not interrupt media
            # Media already went out. Diagnostic failure must not stop the call.
            logger.warning(
                "[run {}] Twilio playback mark could not be sent ({})",
                self._run_id,
                type(exc).__name__,
            )

    async def receive(self):
        message = await self._websocket.receive()
        if message.get("type") == "websocket.receive" and message.get("text"):
            try:
                event = json.loads(message["text"])
            except (ValueError, TypeError):
                return message
            if not isinstance(event, dict):
                return message
            if event.get("event") == "media":
                try:
                    audio = base64.b64decode(event["media"]["payload"], validate=True)
                except (KeyError, ValueError, TypeError):
                    audio = b""
                if audio:
                    self._inbound_packets += 1
                    self._inbound_bytes += len(audio)
                    # Mu-law silence uses 0xff (some gateways also send 0x7f).
                    if any(sample not in (0xFF, 0x7F) for sample in audio):
                        self._inbound_non_silent_packets += 1
                    if self._inbound_packets == 1:
                        logger.info(
                            "[run {}] First inbound Twilio media received ({} mu-law bytes)",
                            self._run_id,
                            len(audio),
                        )
                    elif self._inbound_packets % 250 == 0:
                        logger.info(
                            "[run {}] Twilio inbound audio: {} packets, {} bytes, "
                            "{} non-silent packets",
                            self._run_id,
                            self._inbound_packets,
                            self._inbound_bytes,
                            self._inbound_non_silent_packets,
                        )
            if not isinstance(event.get("mark", {}), dict):
                return message
            if (
                event.get("event") == "mark"
                and event.get("streamSid") == self._stream_sid
                and event.get("mark", {}).get("name") == self._mark_name
                and self._sent_at is not None
                and not self._acknowledged
            ):
                self._acknowledged = True
                logger.info(
                    "[run {}] Twilio first-audio mark acknowledged after {} ms (cleared={})",
                    self._run_id,
                    round((time.monotonic() - self._sent_at) * 1000),
                    self._cleared,
                )
        elif message.get("type") == "websocket.disconnect":
            logger.info(
                "[run {}] Twilio inbound audio ended: {} packets, {} bytes, "
                "{} non-silent packets",
                self._run_id,
                self._inbound_packets,
                self._inbound_bytes,
                self._inbound_non_silent_packets,
            )
        return message
