"""Shared bootstrap model for local LLM paths without an explicit selection."""

import os

DEFAULT_LOCAL_LLM_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "qwen3.5:2b-q4_K_M").strip() or "qwen3.5:2b-q4_K_M"
