"""Kodewaves sovereign subclasses of pipecat realtime LLM services.

Provides native conversational realtime wrappers for Gemini Live, OpenAI Realtime,
OpenAI Live, Grok Realtime, Ultravox, Azure, and AWS Nova Sonic.
"""

from .conversation import RealtimeConversationMixin

try:
    from .aws_nova_sonic import KodewavesAWSNovaSonicLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesAWSNovaSonicLLMService = None  # type: ignore

try:
    from .azure_realtime import KodewavesAzureRealtimeLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesAzureRealtimeLLMService = None  # type: ignore

try:
    from .gemini_live import KodewavesGeminiLiveLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesGeminiLiveLLMService = None  # type: ignore

try:
    from .gemini_live_vertex import KodewavesGeminiLiveVertexLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesGeminiLiveVertexLLMService = None  # type: ignore

try:
    from .grok_realtime import KodewavesGrokRealtimeLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesGrokRealtimeLLMService = None  # type: ignore

try:
    from .openai_live import KodewavesOpenAILiveLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesOpenAILiveLLMService = None  # type: ignore

try:
    from .openai_realtime import KodewavesOpenAIRealtimeLLMService
except (ImportError, ModuleNotFoundError):
    KodewavesOpenAIRealtimeLLMService = None  # type: ignore

try:
    from .ultravox_realtime import (
        KodewavesUltravoxOneShotInputParams,
        KodewavesUltravoxRealtimeLLMService,
    )
except (ImportError, ModuleNotFoundError):
    KodewavesUltravoxOneShotInputParams = None  # type: ignore
    KodewavesUltravoxRealtimeLLMService = None  # type: ignore

__all__ = [
    "RealtimeConversationMixin",
    "KodewavesAWSNovaSonicLLMService",
    "KodewavesAzureRealtimeLLMService",
    "KodewavesGeminiLiveLLMService",
    "KodewavesGeminiLiveVertexLLMService",
    "KodewavesGrokRealtimeLLMService",
    "KodewavesOpenAILiveLLMService",
    "KodewavesOpenAIRealtimeLLMService",
    "KodewavesUltravoxOneShotInputParams",
    "KodewavesUltravoxRealtimeLLMService",
]
