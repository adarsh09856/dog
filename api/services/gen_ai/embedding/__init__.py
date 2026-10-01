"""Embedding services for document processing and retrieval."""

from .azure_openai_service import (
    AzureEmbeddingAPIKeyNotConfiguredError,
    AzureOpenAIEmbeddingService,
)
from .base import BaseEmbeddingService
from .kodewaves_service import DograhEmbeddingService, KodewavesEmbeddingService
from .factory import build_embedding_service, resolve_embedding_correlation_id
from .openai_service import EmbeddingAPIKeyNotConfiguredError, OpenAIEmbeddingService

__all__ = [
    "AzureEmbeddingAPIKeyNotConfiguredError",
    "AzureOpenAIEmbeddingService",
    "BaseEmbeddingService",
    "KodewavesEmbeddingService",
    "DograhEmbeddingService",
    "EmbeddingAPIKeyNotConfiguredError",
    "OpenAIEmbeddingService",
    "build_embedding_service",
    "resolve_embedding_correlation_id",
]
