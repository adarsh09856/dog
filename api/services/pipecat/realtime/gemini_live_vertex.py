"""Kodewaves subclass of pipecat's Gemini Live Vertex AI LLM service.

Diamond inheritance: combines the Kodewaves sovereign engine-integration overrides from
:class:`KodewavesGeminiLiveLLMService` with the Vertex-specific tweaks from
upstream's :class:`GeminiLiveVertexLLMService` (no history config,
``NON_BLOCKING`` tools disabled, service-account credentials).
"""

from api.services.pipecat.realtime.gemini_live import KodewavesGeminiLiveLLMService
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.google.gemini_live.vertex.llm import (
    GeminiLiveVertexLLMService,
)


class KodewavesGeminiLiveVertexLLMService(
    KodewavesGeminiLiveLLMService,
    GeminiLiveVertexLLMService,
):
    """Vertex AI variant of Gemini Live with Kodewaves sovereign integration."""

    pass


# Guard against MRO regressions
_mro = KodewavesGeminiLiveVertexLLMService.__mro__
assert _mro[1] is KodewavesGeminiLiveLLMService, (
    f"Expected KodewavesGeminiLiveLLMService at MRO[1], got {_mro[1]}"
)
assert _mro.index(GeminiLiveVertexLLMService) < _mro.index(GeminiLiveLLMService), (
    "Vertex overrides must precede the base Gemini implementation"
)
del _mro


# Compatibility alias
DograhGeminiLiveVertexLLMService = KodewavesGeminiLiveVertexLLMService
