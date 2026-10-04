"""
Catalog Routes — Dynamic Provider, Model & Voice capability manifests for Studio & Organization settings.
"""

import os
from typing import Any, Dict, List, Optional
import aiohttp
from fastapi import APIRouter, Depends
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.credentials.master_credential_service import master_credential_service

router = APIRouter(prefix="/catalog", tags=["catalog"])

# Official verified cloud models matching actual provider APIs
DEFAULT_CLOUD_LLM_MODELS = [
    {"value": "gemini-2.5-flash", "label": "Google Gemini 2.5 Flash", "provider": "google"},
    {"value": "gemini-2.5-pro", "label": "Google Gemini 2.5 Pro (Deep Reasoning)", "provider": "google"},
    {"value": "gemini-2.0-flash", "label": "Google Gemini 2.0 Flash (Fast Production)", "provider": "google"},
    {"value": "gpt-4o", "label": "OpenAI GPT-4o (High Intelligence)", "provider": "openai"},
    {"value": "gpt-4o-mini", "label": "OpenAI GPT-4o Mini (Fast & Cost-effective)", "provider": "openai"},
    {"value": "claude-3-5-sonnet-20241022", "label": "Anthropic Claude 3.5 Sonnet (Advanced)", "provider": "anthropic"},
    {"value": "claude-3-5-haiku-20241022", "label": "Anthropic Claude 3.5 Haiku (Fast)", "provider": "anthropic"},
    {"value": "llama-3.3-70b-versatile", "label": "Groq Llama 3.3 70B (Ultra Low Latency)", "provider": "groq"},
    {"value": "llama-3.1-8b-instant", "label": "Groq Llama 3.1 8B (Sub-100ms)", "provider": "groq"},
    {"value": "sarvam-2b", "label": "Sarvam Indic 2B (Indian Languages)", "provider": "sarvam"},
]

DEFAULT_CLOUD_STT_MODELS = [
    {"value": "gemini-2.5-flash", "label": "Google Gemini 2.5 Flash Audio STT", "provider": "google"},
    {"value": "gemini-2.0-flash", "label": "Google Gemini 2.0 Flash Audio STT", "provider": "google"},
    {"value": "nova-3", "label": "Deepgram Nova-3 (Conversational)", "provider": "deepgram"},
    {"value": "nova-2", "label": "Deepgram Nova-2 (Conversational & Telephony)", "provider": "deepgram"},
    {"value": "whisper-1", "label": "OpenAI Whisper-1 (Accurate Multilingual)", "provider": "openai"},
    {"value": "saaras:v2", "label": "Sarvam Saaras v2 (High-accuracy Indic Speech)", "provider": "sarvam"},
    {"value": "azure-speech", "label": "Microsoft Azure Speech STT", "provider": "azure"},
]

DEFAULT_CLOUD_TTS_MODELS = [
    {"value": "gemini-2.5-flash-preview-tts", "label": "Google Gemini 2.5 Voice Studio", "provider": "google"},
    {"value": "sonic-3.5", "label": "Cartesia Sonic 3.5 (Ultra-low latency, ~90ms)", "provider": "cartesia"},
    {"value": "sonic-multilingual", "label": "Cartesia Sonic Multilingual", "provider": "cartesia"},
    {"value": "eleven_multilingual_v2", "label": "ElevenLabs Multilingual v2 (Rich Neural)", "provider": "elevenlabs"},
    {"value": "eleven_flash_v2_5", "label": "ElevenLabs Flash v2.5 (High Speed & Expressive)", "provider": "elevenlabs"},
    {"value": "eleven_turbo_v2_5", "label": "ElevenLabs Turbo v2.5", "provider": "elevenlabs"},
    {"value": "tts-1", "label": "OpenAI TTS-1 (Standard Natural Speech)", "provider": "openai"},
    {"value": "tts-1-hd", "label": "OpenAI TTS-1 HD (High Definition Studio)", "provider": "openai"},
    {"value": "bulbul:v1", "label": "Sarvam Bulbul v1 (Native Indian Languages)", "provider": "sarvam"},
    {"value": "aura-asteria-en", "label": "Deepgram Aura Asteria (Female Conversational)", "provider": "deepgram"},
    {"value": "aura-orion-en", "label": "Deepgram Aura Orion (Male Authoritative)", "provider": "deepgram"},
    {"value": "azure-neural", "label": "Microsoft Azure Neural Voice", "provider": "azure"},
]

DEFAULT_LOCAL_STT_MODELS = []

DEFAULT_LOCAL_TTS_MODELS = [
    {"value": "piper", "label": "Piper TTS (Native Hindi & Indic ONNX, ~40ms Ultra-Fast)"},
]


@router.get("/available")
async def get_available_catalog(
    user: UserModel = Depends(get_user),
) -> Dict[str, Any]:
    """
    Returns dynamic list of models and engines actually available to this organization:
    1. Returns all supported cloud models, prioritizing and tagging models backed by active master keys.
    2. Only local LLM models actually downloaded on the host Ollama instance.
    3. Engine and local AI entitlement flags for the requesting user.
    """
    # 1. Determine active providers with master keys
    candidate_providers = [
        "openai", "anthropic", "google", "gemini", "deepgram",
        "cartesia", "elevenlabs", "sarvam", "groq", "azure", "navana"
    ]
    active_providers = set()
    for prov in candidate_providers:
        creds = await master_credential_service.get_master_credential(prov)
        if creds and (creds.get("api_key") or creds.get("auth_token")):
            active_providers.add(prov)
            if prov in ("google", "gemini"):
                active_providers.add("google")
                active_providers.add("gemini")

    # Helper to return only models backed by active master keys
    def build_categorized_models(default_list: list[dict]) -> list[dict]:
        active_items = []
        for item in default_list:
            prov = item.get("provider", "")
            has_master = prov in active_providers
            if has_master:
                label = item["label"]
                if "★" not in label:
                    label = f"{label} ★"
                active_items.append({**item, "label": label, "has_master_key": True})
        
        # If active master keys are configured in Admin, ONLY show models for active providers!
        if active_items:
            return active_items
        
        # If no master keys are configured anywhere yet, return default models
        return [{**item, "has_master_key": False} for item in default_list]

    cloud_llm = build_categorized_models(DEFAULT_CLOUD_LLM_MODELS)
    cloud_stt = build_categorized_models(DEFAULT_CLOUD_STT_MODELS)
    cloud_tts = build_categorized_models(DEFAULT_CLOUD_TTS_MODELS)

    # Prepend Auto recommendation
    cloud_llm.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": len(active_providers) > 0})
    cloud_stt.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": len(active_providers) > 0})
    cloud_tts.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": len(active_providers) > 0})

    # 3. Query installed Ollama models
    local_ai_setting = await kodewaves_db_client.get_setting("local_ai") or {}
    ollama_endpoint = local_ai_setting.get("ollama_endpoint") or os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")

    installed_local_llm = []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session:
            async with session.get(f"{ollama_endpoint.rstrip('/')}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for model_obj in data.get("models", []):
                        name = model_obj.get("name", "")
                        size_gb = round(model_obj.get("size", 0) / (1024 ** 3), 1)
                        label = f"{name} ({size_gb} GB RAM)" if size_gb > 0 else name
                        installed_local_llm.append({"value": name, "label": label})
    except Exception as e:
        logger.debug(f"[Catalog] Unable to query Ollama at {ollama_endpoint}: {e}")

    # Fallback if Ollama unreachable
    if not installed_local_llm:
        installed_local_llm = [
            {"value": "qwen2.5:0.5b", "label": "Qwen 2.5 0.5B (Fast CPU Default)"},
        ]

    # 4. Permissions & platform toggles
    engine_enabled = local_ai_setting.get("enable_local_ai_engine", True)
    has_local_access = getattr(user, "has_local_ai_access", True)
    if has_local_access is None:
        has_local_access = True

    return {
        "active_providers": list(active_providers),
        "cloud_llm_models": cloud_llm,
        "cloud_stt_models": cloud_stt,
        "cloud_tts_models": cloud_tts,
        "local_llm_models": installed_local_llm,
        "local_stt_models": DEFAULT_LOCAL_STT_MODELS,
        "local_tts_models": DEFAULT_LOCAL_TTS_MODELS,
        "local_engine_enabled": engine_enabled,
        "has_local_ai_access": has_local_access,
    }
