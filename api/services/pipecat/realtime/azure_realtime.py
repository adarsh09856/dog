"""Azure authentication and transport with Kodewaves sovereign OpenAI realtime behavior."""

from api.services.pipecat.realtime.openai_realtime import KodewavesOpenAIRealtimeLLMService
from pipecat.services.azure.realtime.llm import AzureRealtimeLLMService


class KodewavesAzureRealtimeLLMService(
    KodewavesOpenAIRealtimeLLMService, AzureRealtimeLLMService
):
    """Share OpenAI conversation handling while retaining Azure's constructor."""


# Compatibility alias
DograhAzureRealtimeLLMService = KodewavesAzureRealtimeLLMService
