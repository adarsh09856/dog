#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves TTS Service implementation using self-contained WebSocket streaming."""

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    StartFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TextAggregationMode, WebsocketTTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.tracing.service_decorators import traced_tts
from pipecat.utils.types import NOT_GIVEN, NotGiven

try:
    import websockets
    from websockets.protocol import State
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use TTS, you need to `pip install websockets`.")
    raise Exception(f"Missing module: {e}")


def calculate_word_times(
    alignment_info: dict[str, Any], cumulative_time: float
) -> list[tuple[str, float]]:
    words_data = alignment_info.get("words", [])
    word_times = []

    for word_info in words_data:
        word = word_info.get("word", "")
        start_time_ms = word_info.get("start", 0)
        start_time_seconds = cumulative_time + (start_time_ms / 1000.0)
        word_times.append((word, start_time_seconds))

    return word_times


@dataclass
class KodewavesTTSSettings(TTSSettings):
    """Settings for KodewavesTTSService.

    Parameters:
        speed: Speech speed control (0.5 to 2.0).
        pitch: Voice pitch control (-1.0 to 1.0).
        volume: Volume control (0.0 to 1.0).
    """

    speed: float | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    pitch: float | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    volume: float | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)


class KodewavesTTSService(WebsocketTTSService):
    """Kodewaves sovereign text-to-speech service with word timestamps.

    Provides real-time text-to-speech using Kodewaves's unified WebSocket API
    with zero external cloud tracking or dependencies.
    """

    Settings = KodewavesTTSSettings

    def __init__(
        self,
        *,
        api_key: str = "kodewaves-sovereign-token",
        base_url: str = "ws://localhost:8000",
        ws_path: str = "/v1/audio/speech",
        correlation_id: str | None = None,
        sample_rate: int | None = None,
        settings: KodewavesTTSSettings | None = None,
        text_aggregation_mode: TextAggregationMode | None = None,
        **kwargs,
    ):
        clean_url = base_url or "ws://localhost:8000"
        if "services.dograh.com" in clean_url:
            clean_url = "ws://localhost:8000"

        default_settings = KodewavesTTSSettings(
            model="default",
            voice="default",
            language="en",
            speed=1.0,
            pitch=0.0,
            volume=1.0,
        )
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            text_aggregation_mode=text_aggregation_mode,
            push_text_frames=False,
            push_stop_frames=True,
            pause_frame_processing=True,
            sample_rate=sample_rate,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key or "kodewaves-sovereign-token"
        self._base_url = clean_url
        self._ws_path = ws_path
        self._correlation_id = correlation_id
        self._voice_settings: dict[str, float | bool] = {}
        speed = default_settings.speed
        if isinstance(speed, (int, float)):
            self._voice_settings["speed"] = float(speed)

        self._receive_task = None
        self._keepalive_task = None
        self._cumulative_time = 0
        self._start_metadata = None
        self._remote_initialized_context_ids: set[str] = set()
        self._finished_context_ids: set[str] = set()
        self._cancelled_context_ids: set[str] = set()

    def can_generate_metrics(self) -> bool:
        return True

    def _reset_state(self):
        self._cumulative_time = 0

    async def set_language(self, language: Language):
        self._settings.language = language.value

    def _get_correlation_id(self) -> str | None:
        if self._correlation_id:
            return self._correlation_id
        if self._start_metadata:
            cid = self._start_metadata.get("mps_correlation_id") or self._start_metadata.get("correlation_id")
            if cid is not None:
                return str(cid)
        return None

    async def _connect_websocket(self):
        try:
            if self._websocket and self._websocket.state is State.OPEN:
                return

            url = f"{self._base_url}{self._ws_path}"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            logger.debug(f"[KodewavesTTS] Connecting to WebSocket at {url}")
            ws = await self._websocket_connect(url, additional_headers=headers)
            self._websocket = ws
            self._remote_initialized_context_ids.clear()
            self._finished_context_ids.clear()
            self._cancelled_context_ids.clear()

            config_msg = {
                "type": "config",
                "model": self._settings.model,
                "voice": self._settings.voice,
                "sample_rate": self.sample_rate,
            }
            if self._voice_settings:
                config_msg["settings"] = self._voice_settings

            correlation_id = self._get_correlation_id()
            if correlation_id:
                config_msg["correlation_id"] = correlation_id

            await ws.send(json.dumps(config_msg))
            logger.info("[KodewavesTTS] Connected to TTS service")

        except Exception as e:
            self._websocket = None
            logger.error(f"[KodewavesTTS] Failed to connect: {e}")
            raise

    async def _disconnect_websocket(self):
        try:
            await self.stop_all_metrics()
            if self._websocket:
                logger.debug("[KodewavesTTS] Disconnecting from TTS service")
                await self._websocket.close()
                logger.debug("[KodewavesTTS] Disconnected successfully")
        except Exception as e:
            logger.error(f"[KodewavesTTS] Error disconnecting: {e}")
        finally:
            self._remote_initialized_context_ids.clear()
            self._finished_context_ids.clear()
            self._cancelled_context_ids.clear()
            await self.remove_active_audio_context()
            self._websocket = None

    async def _connect(self):
        await super()._connect()
        await self._connect_websocket()

        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(self._receive_task_handler(self._report_error))

        if self._websocket and not self._keepalive_task:
            self._keepalive_task = self.create_task(self._keepalive_task_handler())

    async def _disconnect(self):
        await super()._disconnect()

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        if self._keepalive_task:
            await self.cancel_task(self._keepalive_task)
            self._keepalive_task = None

        await self._disconnect_websocket()

    def _get_websocket(self):
        if self._websocket:
            return self._websocket
        raise Exception("Websocket not connected")

    async def _receive_messages(self):
        async for message in self._get_websocket():
            try:
                msg = json.loads(message)
                msg_type = msg.get("type")
                ctx_id = msg.get("context_id")

                if msg_type == "final":
                    if ctx_id:
                        self._remote_initialized_context_ids.discard(ctx_id)
                        if self.audio_context_available(ctx_id):
                            await self.remove_audio_context(ctx_id)
                    continue

                if ctx_id and not self.audio_context_available(ctx_id):
                    if self.get_active_audio_context_id() == ctx_id:
                        await self.create_audio_context(ctx_id)
                    else:
                        continue

                if msg_type == "audio":
                    await self.stop_ttfb_metrics()
                    await self.start_word_timestamps()

                    audio_data = msg.get("audio")
                    if audio_data:
                        audio = base64.b64decode(audio_data)
                        frame = TTSAudioRawFrame(audio, self.sample_rate, 1, context_id=ctx_id)
                        effective_ctx_id = ctx_id or self.get_active_audio_context_id()
                        if effective_ctx_id:
                            await self.append_to_audio_context(effective_ctx_id, frame)

                elif msg_type == "alignment":
                    alignment = msg.get("data", {})
                    word_times = calculate_word_times(alignment, self._cumulative_time)
                    if word_times:
                        await self.add_word_timestamps(word_times, ctx_id)
                        self._cumulative_time = word_times[-1][1]

                elif msg_type == "error":
                    error_msg = msg.get("message", "Unknown error")
                    await self.push_frame(TTSStoppedFrame())
                    await self.stop_all_metrics()
                    raise Exception(f"[KodewavesTTS] error: {error_msg}")

            except asyncio.CancelledError:
                raise
            except json.JSONDecodeError as e:
                logger.error(f"[KodewavesTTS] Failed to decode message: {e}")
                raise
            except Exception as e:
                logger.error(f"[KodewavesTTS] Error processing message: {e}")
                raise

    async def _keepalive_task_handler(self):
        KEEPALIVE_SLEEP = 10
        while True:
            await asyncio.sleep(KEEPALIVE_SLEEP)
            try:
                if self._websocket and self._websocket.state is State.OPEN:
                    context_id = self.get_active_audio_context_id()
                    if not context_id or context_id not in self._remote_initialized_context_ids:
                        continue
                    keepalive_msg = {
                        "type": "keepalive",
                        "context_id": context_id,
                    }
                    await self._websocket.send(json.dumps(keepalive_msg))
            except websockets.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"[KodewavesTTS] Keepalive error: {e}")

    async def _send_text(self, text: str, context_id: str):
        if self._websocket and context_id:
            msg = {"type": "synthesize", "text": text, "context_id": context_id}
            await self._websocket.send(json.dumps(msg))

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        try:
            if not self._websocket or self._websocket.state is State.CLOSED:
                await self._connect()

            try:
                if not self.audio_context_available(context_id):
                    await self.create_audio_context(context_id)
                    await self.start_ttfb_metrics()
                    yield TTSStartedFrame(context_id=context_id)
                    self._cumulative_time = 0

                    context_msg = {
                        "type": "create_context",
                        "context_id": context_id,
                        "voice": self._settings.voice,
                        "model": self._settings.model,
                    }
                    if self._voice_settings:
                        context_msg["settings"] = self._voice_settings

                    correlation_id = self._get_correlation_id()
                    if correlation_id:
                        context_msg["correlation_id"] = correlation_id

                    await self._get_websocket().send(json.dumps(context_msg))
                    self._remote_initialized_context_ids.add(context_id)
                    self._finished_context_ids.discard(context_id)
                    self._cancelled_context_ids.discard(context_id)

                await self._send_text(text, context_id)
                await self.start_tts_usage_metrics(text)
            except Exception as e:
                yield TTSStoppedFrame(context_id=context_id)
                yield ErrorFrame(error=f"[KodewavesTTS] Unknown error occurred: {e}")
                return

            yield None

        except Exception as e:
            yield ErrorFrame(error=f"[KodewavesTTS] Unknown error occurred: {e}")

    async def _finish_context(self, context_id: str):
        if context_id and self._websocket and context_id not in self._finished_context_ids:
            self._remote_initialized_context_ids.discard(context_id)
            self._finished_context_ids.add(context_id)
            try:
                await self._websocket.send(
                    json.dumps({"type": "close_context", "context_id": context_id})
                )
            except Exception as e:
                logger.error(f"[KodewavesTTS] Error finishing context: {e}")

    async def _cancel_context(self, context_id: str):
        if context_id and self._websocket and context_id not in self._cancelled_context_ids:
            self._remote_initialized_context_ids.discard(context_id)
            self._cancelled_context_ids.add(context_id)
            try:
                await self._websocket.send(json.dumps({"type": "cancel", "context_id": context_id}))
            except Exception as e:
                logger.error(f"[KodewavesTTS] Error cancelling context: {e}")

        self._reset_state()

    async def on_audio_context_interrupted(self, context_id: str):
        await self._cancel_context(context_id)
        await super().on_audio_context_interrupted(context_id)
        self._cancelled_context_ids.discard(context_id)

    async def on_audio_context_completed(self, context_id: str):
        self._reset_state()
        await super().on_audio_context_completed(context_id)
        self._finished_context_ids.discard(context_id)

    async def on_turn_context_completed(self):
        context_id = self._turn_context_id
        should_finish = bool(context_id and self.audio_context_available(context_id))
        await super().on_turn_context_completed()
        if should_finish and context_id:
            await self._finish_context(context_id)

    async def flush_audio(self, context_id: str | None = None):
        flush_id = context_id or self.get_active_audio_context_id()
        if not flush_id or not self._websocket:
            return
        msg = {"type": "flush", "context_id": flush_id}
        await self._websocket.send(json.dumps(msg))

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._start_metadata = frame.metadata
        self._reset_state()
        await self._connect()
