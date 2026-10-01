#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Backward compatibility module for Dograh STT service.

Use `pipecat.services.kodewaves.stt` instead.
"""

from pipecat.services.kodewaves.stt import (
    DograhSTTService,
    DograhSTTSettings,
    KodewavesSTTService,
    KodewavesSTTSettings,
)

__all__ = [
    "DograhSTTService",
    "DograhSTTSettings",
    "KodewavesSTTService",
    "KodewavesSTTSettings",
]
