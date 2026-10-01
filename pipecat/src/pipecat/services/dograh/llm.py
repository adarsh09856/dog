#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Backward compatibility module for Dograh LLM service.

Use `pipecat.services.kodewaves.llm` instead.
"""

from pipecat.services.kodewaves.llm import (
    DograhLLMService,
    KodewavesLLMService,
)

__all__ = [
    "DograhLLMService",
    "KodewavesLLMService",
]
