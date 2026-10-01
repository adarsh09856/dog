#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Backward compatibility module for Dograh TTS service.

Use `pipecat.services.kodewaves.tts` instead.
"""

from pipecat.services.kodewaves.tts import (
    DograhTTSService,
    DograhTTSSettings,
    KodewavesTTSService,
    KodewavesTTSSettings,
)

__all__ = [
    "DograhTTSService",
    "DograhTTSSettings",
    "KodewavesTTSService",
    "KodewavesTTSSettings",
]
