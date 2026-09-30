#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves Sovereign Pipecat Services.

Provides native OpenAI-compatible LLM, STT, and TTS services for Kodewaves,
connecting directly to self-hosted Ollama & Speaches or Admin Master Keys
with zero external cloud dependencies.
"""

from .llm import KodewavesLLMService
from .stt import KodewavesSTTService, KodewavesSTTSettings
from .tts import KodewavesTTSService, KodewavesTTSSettings

__all__ = [
    "KodewavesLLMService",
    "KodewavesSTTService",
    "KodewavesSTTSettings",
    "KodewavesTTSService",
    "KodewavesTTSSettings",
]
