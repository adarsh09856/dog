#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Backward compatibility module for Dograh Flux services.

Use `pipecat.services.kodewaves.flux` instead.
"""

from pipecat.services.kodewaves.flux.stt import (
    DograhFluxSTTService,
    KodewavesFluxSTTService,
)

__all__ = [
    "DograhFluxSTTService",
    "KodewavesFluxSTTService",
]
