#
# Copyright (c) 2026, Kodewaves Sovereign Voice AI
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Kodewaves LLM Service implementation using OpenAI-compatible interface."""

from collections.abc import AsyncIterator
from loguru import logger
from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk

from pipecat.frames.frames import Frame, StartFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.openai.base_llm import OpenAILLMInvocationParams, OpenAILLMSettings
from pipecat.services.openai.llm import OpenAILLMService


class KodewavesLLMService(OpenAILLMService):
    """A sovereign LLM service using Kodewaves local Ollama or platform master keys.

    Extends OpenAILLMService to connect locally to host/container Ollama or
    the configured master provider keys with zero external cloud dependencies.
    """

    supports_developer_role = False

    def __init__(
        self,
        *,
        api_key: str = "kodewaves-sovereign-token",
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen2.5:0.5b",
        correlation_id: str | None = None,
        usage_context: str | None = None,
        settings: OpenAILLMSettings | None = None,
        **kwargs,
    ):
        clean_key = api_key or "kodewaves-sovereign-token"
        clean_url = base_url or "http://localhost:11434/v1"
        if "services.dograh.com" in clean_url:
            clean_url = "http://localhost:11434/v1"

        if settings is None:
            settings = OpenAILLMSettings(model=model)
        elif not settings.model:
            settings.model = model

        super().__init__(
            api_key=clean_key,
            base_url=clean_url,
            settings=settings,
            **kwargs,
        )
        self._correlation_id = correlation_id
        self._usage_context = usage_context
        logger.info(f"[KodewavesLLM] Initialized sovereign LLM at {clean_url} with model {settings.model}")
