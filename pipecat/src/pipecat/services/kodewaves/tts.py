#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves TTS Service implementation."""

from dataclasses import dataclass
from pipecat.services.settings import TTSSettings
from pipecat.services.dograh.tts import DograhTTSService, DograhTTSSettings


@dataclass
class KodewavesTTSSettings(DograhTTSSettings):
    """Settings for KodewavesTTSService."""
    pass


class KodewavesTTSService(DograhTTSService):
    """Kodewaves sovereign text-to-speech service using local Kokoro or master TTS keys."""

    Settings = KodewavesTTSSettings

    def __init__(
        self,
        *,
        api_key: str = "kodewaves-sovereign-token",
        base_url: str = "ws://localhost:8000",
        ws_path: str = "/v1/audio/speech",
        settings: KodewavesTTSSettings | None = None,
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
