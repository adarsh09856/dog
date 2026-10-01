"""Backward compatibility shim for dograh_service."""

from .kodewaves_service import (  # noqa: F401
    DograhEmbeddingService,
    KodewavesEmbeddingService,
    MPS_BILLING_VERSION_KEY,
    MPS_BILLING_VERSION_V2,
)

__all__ = [
    "DograhEmbeddingService",
    "KodewavesEmbeddingService",
    "MPS_BILLING_VERSION_KEY",
    "MPS_BILLING_VERSION_V2",
]
