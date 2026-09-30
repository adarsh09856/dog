#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves STT Service implementation."""

from dataclasses import dataclass
from pipecat.services.stt_settings import STTSettings
from pipecat.services.dograh.stt import DograhSTTService, DograhSTTSettings


@dataclass
class KodewavesSTTSettings(DograhSTTSettings):
    """Settings for KodewavesSTTService."""
    pass


class KodewavesSTTService(DograhSTTService):
    """Kodewaves sovereign speech-to-text service using local Whisper or master STT keys."""

    Settings = KodewavesSTTSettings

    def __init__(
        self,
        *,
        api_key: str = "kodewaves-sovereign-token",
        base_url: str = "ws://localhost:8000",
        ws_path: str = "/v1/audio/transcriptions",
        settings: KodewavesSTTSettings | None = None,
        **kwargs,
    ):
        clean_url = base_url or "ws://localhost:8000"
        if "services.dograh.com" in clean_url:
            clean_url = "ws://localhost:8000"

        super().__init__(
            api_key=api_key or "kodewaves-sovereign-token",
            base_url=clean_url,
            ws_path=ws_path,
            settings=settings,
            **kwargs,
        )
