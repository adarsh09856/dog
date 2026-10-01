#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves STT Service implementation using self-contained WebSocket streaming."""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from loguru import logger

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterimTranscriptionFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    StartFrame,
    STTMetadataFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import WebsocketSTTService
from pipecat.transcriptions.language import Language
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies
from pipecat.utils.time import time_now_iso8601
from pipecat.utils.tracing.service_decorators import traced_stt

try:
    import websockets
    from websockets.protocol import State
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use STT, you need to `pip install websockets`.")
    raise Exception(f"Missing module: {e}")


@dataclass
class KodewavesSTTSettings(STTSettings):
    """Settings for KodewavesSTTService."""

    pass


class KodewavesSTTService(WebsocketSTTService):
    """Kodewaves sovereign speech-to-text service using local Whisper or master STT keys.

    Provides real-time speech recognition using Kodewaves's unified WebSocket API
    with zero external cloud tracking or dependencies.
    """

    Settings = KodewavesSTTSettings

    def __init__(
        self,
        *,
        api_key: str = "kodewaves-sovereign-token",
        base_url: str = "ws://localhost:8000",
        ws_path: str = "/v1/audio/transcriptions",
        correlation_id: str | None = None,
        sample_rate: int | None = None,
        interim_results: bool = True,
        vad_events: bool = False,
        keyterms: list[str] | None = None,
        settings: KodewavesSTTSettings | None = None,
        ttfs_p99_latency: float | None = 0.5,
        **kwargs,
    ):
        clean_url = base_url or "ws://localhost:8000"
        if "services.dograh.com" in clean_url:
            clean_url = "ws://localhost:8000"

        default_settings = KodewavesSTTSettings(model="default", language="multi")
        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            reconnect_on_error=True,
            sample_rate=sample_rate,
            settings=default_settings,
            ttfs_p99_latency=ttfs_p99_latency,
            **kwargs,
        )

        self._api_key = api_key or "kodewaves-sovereign-token"
        self._base_url = clean_url
        self._ws_path = ws_path
        self._correlation_id = correlation_id
        self._interim_results = interim_results
        self._vad_events = vad_events
        self._keyterms = keyterms or []

        self._receive_task = None
        self._protocol_keepalive_task = None
        self._start_metadata = None

        if self._vad_events:
            self._register_event_handler("on_speech_started")
            self._register_event_handler("on_speech_ended")

    @property
    def vad_enabled(self):
        return self._vad_events

    def service_metadata_frame(self) -> STTMetadataFrame:
        frame = super().service_metadata_frame()
        if self._vad_events:
            frame.user_turn_strategies = ExternalUserTurnStrategies()
        return frame

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

            logger.debug(f"[KodewavesSTT] Connecting to WebSocket at {url}")
            ws = await self._websocket_connect(url, additional_headers=headers)
            self._websocket = ws

            config_msg = {
                "type": "config",
                "model": self._settings.model,
                "language": self._settings.language,
                "sample_rate": self.sample_rate,
                "interim_results": self._interim_results,
                "vad_events": self._vad_events,
            }

            if self._keyterms:
                config_msg["keyterms"] = self._keyterms

            correlation_id = self._get_correlation_id()
            if correlation_id:
                config_msg["correlation_id"] = correlation_id

            await ws.send(json.dumps(config_msg))
            logger.info("[KodewavesSTT] Connected to STT service")

        except Exception as e:
            self._websocket = None
            logger.error(f"[KodewavesSTT] Failed to connect: {e}")
            raise

    async def _disconnect_websocket(self):
        try:
            if self._websocket:
                logger.debug("[KodewavesSTT] Disconnecting from STT service")
                end_msg = {"type": "end_of_stream"}
                await self._websocket.send(json.dumps(end_msg))
                await self._websocket.close()
                logger.debug("[KodewavesSTT] Disconnected successfully")
        except Exception as e:
            logger.error(f"[KodewavesSTT] Error disconnecting: {e}")
        finally:
            self._websocket = None

    async def _connect(self):
        await super()._connect()
        await self._connect_websocket()

        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(self._receive_task_handler(self._report_error))

        if self._websocket and not self._protocol_keepalive_task:
            self._protocol_keepalive_task = self.create_task(
                self._protocol_keepalive_task_handler()
            )

    async def _disconnect(self):
        await super()._disconnect()

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        if self._protocol_keepalive_task:
            await self.cancel_task(self._protocol_keepalive_task)
            self._protocol_keepalive_task = None

        await self._disconnect_websocket()

    async def _receive_messages(self):
        if not self._websocket:
            return

        async for message in self._websocket:
            try:
                msg = json.loads(message)
                msg_type = msg.get("type")

                if msg_type == "transcription":
                    await self._handle_transcription(msg)
                elif msg_type == "speech_started":
                    await self._handle_speech_started(msg)
                elif msg_type == "speech_ended":
                    await self._handle_speech_ended(msg)
                elif msg_type == "error":
                    error_msg = msg.get("message", "Unknown error")
                    await self.push_frame(
                        ErrorFrame(error=f"[KodewavesSTT] error: {error_msg}"),
                        direction=FrameDirection.UPSTREAM,
                    )
                    raise Exception(f"[KodewavesSTT] error: {error_msg}")
                elif msg_type == "ready":
                    logger.debug("[KodewavesSTT] Service ready")

            except asyncio.CancelledError:
                raise
            except json.JSONDecodeError as e:
                logger.error(f"[KodewavesSTT] Failed to decode message: {e}")
                raise
            except Exception as e:
                logger.error(f"[KodewavesSTT] Error processing message: {e}")
                raise

    async def _protocol_keepalive_task_handler(self):
        KEEPALIVE_SLEEP = 5
        while True:
            await asyncio.sleep(KEEPALIVE_SLEEP)
            try:
                if self._websocket and self._websocket.state == State.OPEN:
                    keepalive_msg = {"type": "keepalive"}
                    await self._websocket.send(json.dumps(keepalive_msg))
                    logger.trace("[KodewavesSTT] Sent keepalive")
            except websockets.ConnectionClosed:
                logger.debug("[KodewavesSTT] Keepalive connection closed")
                break
            except Exception as e:
                logger.error(f"[KodewavesSTT] Keepalive error: {e}")

    @traced_stt
    async def _handle_transcription_traced(
        self, transcript: str, is_final: bool, language: Language | None = None
    ):
        pass

    async def _send_finalize(self):
        if self._websocket and self._websocket.state == State.OPEN:
            finalize_msg = json.dumps({"type": "finalize"})
            await self._websocket.send(finalize_msg)
            logger.trace("[KodewavesSTT] Sent finalize")

    async def _handle_transcription(self, msg: dict):
        transcript = msg.get("text", "")
        is_final = msg.get("is_final", False)
        from_finalize = msg.get("from_finalize", False)
        confidence = msg.get("confidence", 0.0)
        language_code = msg.get("language")

        language: Language | None = None
        if language_code:
            try:
                language = Language(language_code)
            except ValueError:
                settings_language = self._settings.language
                if isinstance(settings_language, Language):
                    language = settings_language

        if transcript:
            if is_final:
                if from_finalize:
                    self.confirm_finalize()
                logger.debug(f"[KodewavesSTT] Final transcription: {transcript}")
                await self.push_frame(
                    TranscriptionFrame(
                        text=transcript,
                        user_id=self._user_id,
                        timestamp=time_now_iso8601(),
                        language=language,
                        result={"confidence": confidence} if confidence else None,
                    )
                )
                await self._handle_transcription_traced(transcript, is_final, language)
            else:
                await self.push_frame(
                    InterimTranscriptionFrame(
                        text=transcript,
                        user_id=self._user_id,
                        timestamp=time_now_iso8601(),
                        language=language,
                        result={"confidence": confidence} if confidence else None,
                    )
                )

    async def _handle_speech_started(self, msg: dict):
        logger.debug("[KodewavesSTT] Speech started detected")
        await self.start_ttfb_metrics()
        await self.broadcast_frame(ProposedUserStartedSpeakingFrame)
        await self._call_event_handler("on_speech_started")

    async def _handle_speech_ended(self, msg: dict):
        logger.debug("[KodewavesSTT] Speech ended detected")
        await self.broadcast_frame(ProposedUserStoppedSpeakingFrame)
        await self._call_event_handler("on_speech_ended")

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._start_metadata = frame.metadata
        await self._connect()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            if self._websocket and self._websocket.state == State.OPEN:
                self.request_finalize()
                await self._send_finalize()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if self._websocket and self._websocket.state == State.OPEN:
            await self._websocket.send(audio)
        yield None
