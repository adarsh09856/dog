#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Backward compatibility module for Dograh services.

All implementations have migrated to Kodewaves. This module provides backward
compatibility aliases pointing to `pipecat.services.kodewaves`.
"""

from pipecat.services.kodewaves import (
    DograhFluxSTTService,
    DograhLLMService,
    DograhSTTService,
    DograhSTTSettings,
    DograhTTSService,
    DograhTTSSettings,
)

__all__ = [
    "DograhFluxSTTService",
    "DograhLLMService",
    "DograhSTTService",
    "DograhSTTSettings",
    "DograhTTSService",
    "DograhTTSSettings",
]
