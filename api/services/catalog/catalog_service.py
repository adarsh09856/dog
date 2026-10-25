"""
Dynamic Model and Voice Truth Layer Catalog Service for Kodewaves Sovereign Platform.

Core Invariant:
"Key in Admin -> Live Capability Verification -> Dynamic User Catalog"
No hardcoded lists in UI or API. Models vanish when a key is disabled or fails verification.
"""

import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AIModelCatalogModel, VoiceCatalogModel
from api.services.catalog.normalize import normalize_provider_name, tts_runtime_provider, google_model_layer
from api.services.catalog.local_inventory import (
    get_local_tts_models, whisper_api_base, local_tts_api_base,
)
from api.services.catalog.gemini_voices import discover_indian_voices
from api.services.credentials.master_credential_service import master_credential_service
from api.services.configuration.registry import GEMINI_TTS_VOICES
from api.services.configuration.stt_capabilities import stt_model_supports_auto_detect
from api.services.configuration.options.google import GEMINI_38_INDIC_TTS_LANGUAGES
from api.utils.common import normalize_local_ai_endpoint


# Curated catalog definitions from repo and verified vendor docs (Part 4)
CURATED_PROVIDER_MODELS: Dict[str, List[Dict[str, Any]]] = {
    "google": [
        {"model_identifier": "gemini-3.5-flash", "display_name": "Google Gemini 3.5 Flash", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "gemini-3.5-flash-lite", "display_name": "Google Gemini 3.5 Flash Lite", "layer": "llm", "recommended": False, "supports_tools": True},
        {"model_identifier": "gemini-3.1-flash-lite", "display_name": "Google Gemini 3.1 Flash Lite", "layer": "llm", "recommended": False, "supports_tools": True},
        {"model_identifier": "gemini-3.1-flash-live-preview", "display_name": "Google Gemini 3.1 Flash Live (Bidirectional S2S)", "layer": "s2s", "recommended": True},
        {"model_identifier": "text-embedding-004", "display_name": "Google Text Embedding 004", "layer": "embeddings", "recommended": True},
    ],
    "openai": [
        {"model_identifier": "gpt-4o", "display_name": "OpenAI GPT-4o", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "gpt-4o-mini", "display_name": "OpenAI GPT-4o Mini", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "whisper-1", "display_name": "OpenAI Whisper-1", "layer": "stt", "recommended": True},
        {"model_identifier": "tts-1", "display_name": "OpenAI TTS-1", "layer": "tts", "recommended": True},
        {"model_identifier": "tts-1-hd", "display_name": "OpenAI TTS-1 HD", "layer": "tts", "recommended": False},
        {"model_identifier": "gpt-realtime-2.1", "display_name": "OpenAI GPT Realtime 2.1 (Low-Latency S2S)", "layer": "s2s", "recommended": True},
        {"model_identifier": "gpt-realtime-2.1-mini", "display_name": "OpenAI GPT Realtime 2.1 Mini", "layer": "s2s", "recommended": False},
        {"model_identifier": "text-embedding-3-small", "display_name": "OpenAI Text Embedding 3 Small", "layer": "embeddings", "recommended": True},
    ],
    "anthropic": [
        {"model_identifier": "claude-haiku-4-5-20251001", "display_name": "Anthropic Claude Haiku 4.5", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "claude-sonnet-5-5", "display_name": "Anthropic Claude Sonnet 5.5", "layer": "llm", "recommended": False, "supports_tools": True},
    ],
    "groq": [
        {"model_identifier": "llama-3.3-70b-versatile", "display_name": "Groq Llama 3.3 70B", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "llama-3.1-8b-instant", "display_name": "Groq Llama 3.1 8B", "layer": "llm", "recommended": False, "supports_tools": True},
        {"model_identifier": "whisper-large-v3", "display_name": "Groq Whisper Large v3", "layer": "stt", "recommended": True},
    ],
    "deepgram": [
        {"model_identifier": "nova-3", "display_name": "Deepgram Nova-3 (Conversational)", "layer": "stt", "recommended": True},
        {"model_identifier": "nova-2", "display_name": "Deepgram Nova-2 (Telephony)", "layer": "stt", "recommended": False},
        {"model_identifier": "aura-asteria-en", "display_name": "Deepgram Aura Asteria (Female)", "layer": "tts", "recommended": True},
        {"model_identifier": "aura-orion-en", "display_name": "Deepgram Aura Orion (Male)", "layer": "tts", "recommended": False},
    ],
    "cartesia": [
        {"model_identifier": "ink-2", "display_name": "Cartesia Ink-2 STT", "layer": "stt", "recommended": True},
        {"model_identifier": "sonic-3.5", "display_name": "Cartesia Sonic 3.5 (~90ms Ultra-Low Latency)", "layer": "tts", "recommended": True},
        {"model_identifier": "sonic-multilingual", "display_name": "Cartesia Sonic Multilingual", "layer": "tts", "recommended": False},
    ],
    "elevenlabs": [
        {"model_identifier": "scribe_v2_realtime", "display_name": "ElevenLabs Scribe v2 STT", "layer": "stt", "recommended": False},
        {"model_identifier": "eleven_multilingual_v2", "display_name": "ElevenLabs Multilingual v2", "layer": "tts", "recommended": True},
        {"model_identifier": "eleven_flash_v2_5", "display_name": "ElevenLabs Flash v2.5", "layer": "tts", "recommended": True},
    ],
    "sarvam": [
        {"model_identifier": "sarvam-105b", "display_name": "Sarvam 105B Indic LLM", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "saaras:v3", "display_name": "Sarvam Saaras v3 (High Accuracy Indic STT)", "layer": "stt", "recommended": True, "languages": ["hi-IN", "en-IN"]},
        {"model_identifier": "saarika:v2.5", "display_name": "Sarvam Saarika v2.5 STT", "layer": "stt", "recommended": False, "languages": ["hi-IN", "en-IN"]},
        {"model_identifier": "bulbul:v3", "display_name": "Sarvam Bulbul v3 (Native Indic Voices)", "layer": "tts", "recommended": True, "languages": ["hi-IN", "en-IN"]},
        {"model_identifier": "bulbul:v2", "display_name": "Sarvam Bulbul v2", "layer": "tts", "recommended": False, "languages": ["hi-IN", "en-IN"]},
    ],
    "azure": [
        {"model_identifier": "azure-speech", "display_name": "Microsoft Azure Speech STT", "layer": "stt", "recommended": True},
        {"model_identifier": "azure-neural", "display_name": "Microsoft Azure Neural Voice TTS", "layer": "tts", "recommended": True},
        {"model_identifier": "azure_realtime", "display_name": "Microsoft Azure Realtime Voice GA", "layer": "s2s", "recommended": False},
    ],
    "navana": [
        {"model_identifier": "navana-stt", "display_name": "Navana Indic Telephony STT (8kHz)", "layer": "stt", "recommended": True, "languages": ["hi-IN", "te-IN", "kn-IN", "mr-IN"]},
        {"model_identifier": "navana-tts", "display_name": "Navana Indic Telephony TTS", "layer": "tts", "recommended": True, "languages": ["hi-IN", "te-IN", "kn-IN", "mr-IN"]},
    ],
    "grok": [
        {"model_identifier": "grok-2", "display_name": "xAI Grok-2", "layer": "llm", "recommended": True},
        {"model_identifier": "grok_realtime", "display_name": "xAI Grok Realtime S2S", "layer": "s2s", "recommended": True},
    ],
    "ultravox": [
        {"model_identifier": "ultravox_realtime", "display_name": "Ultravox Realtime S2S", "layer": "s2s", "recommended": True},
    ]
}

def _tts_model_credential_provider(provider: str, model_identifier: str) -> str:
    """Map a catalog TTS model to the credential namespace that serves it."""
    return tts_runtime_provider(provider, model_identifier)

CURATED_PROVIDER_VOICES: Dict[str, List[Dict[str, Any]]] = {
    "google": [
        {
            "voice_id": voice,
            "name": voice,
            "languages": [
                "en-US", "hi-IN", "fr-FR", "es-ES", "de-DE", "it-IT",
                "ja-JP", "nl-NL", "pt-BR", "ru-RU",
            ],
        }
        for voice in GEMINI_TTS_VOICES
    ],
    "openai": [
        {"voice_id": "alloy", "name": "Alloy", "gender": "neutral", "languages": ["en-US"]},
        {"voice_id": "echo", "name": "Echo", "gender": "male", "languages": ["en-US"]},
        {"voice_id": "shimmer", "name": "Shimmer", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "ash", "name": "Ash", "gender": "male", "languages": ["en-US"]},
        {"voice_id": "ballad", "name": "Ballad", "gender": "male", "languages": ["en-US"]},
        {"voice_id": "coral", "name": "Coral", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "sage", "name": "Sage", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "verse", "name": "Verse", "gender": "male", "languages": ["en-US"]},
        {"voice_id": "marin", "name": "Marin", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "cedar", "name": "Cedar", "gender": "male", "languages": ["en-US"]},
    ],
    "sarvam": [
        {"voice_id": "arvind", "name": "Arvind (Indian English / Hindi Male)", "gender": "male", "languages": ["hi-IN", "en-IN"]},
        {"voice_id": "amol", "name": "Amol (Business Indian Male)", "gender": "male", "languages": ["hi-IN", "en-IN"]},
        {"voice_id": "amrita", "name": "Amrita (Warm Indian Female)", "gender": "female", "languages": ["hi-IN", "en-IN"]},
        {"voice_id": "ananya", "name": "Ananya (Youthful Indian Female)", "gender": "female", "languages": ["hi-IN", "en-IN"]},
        {"voice_id": "aditi", "name": "Aditi (Fluent Multilingual Female)", "gender": "female", "languages": ["hi-IN", "en-IN"]},
        {"voice_id": "abhinav", "name": "Abhinav (Clear Articulation Male)", "gender": "male", "languages": ["hi-IN", "en-IN"]},
    ],
    "navana": [
        {"voice_id": "hi-female-1", "name": "Navana Hindi Female (8kHz Telephony)", "gender": "female", "languages": ["hi-IN"]},
        {"voice_id": "hi-male-1", "name": "Navana Hindi Male (8kHz Telephony)", "gender": "male", "languages": ["hi-IN"]},
        {"voice_id": "te-female-1", "name": "Navana Telugu Female", "gender": "female", "languages": ["te-IN"]},
        {"voice_id": "kn-female-1", "name": "Navana Kannada Female", "gender": "female", "languages": ["kn-IN"]},
        {"voice_id": "mr-female-1", "name": "Navana Marathi Female", "gender": "female", "languages": ["mr-IN"]},
    ],
    "deepgram": [
        {"voice_id": "aura-asteria-en", "name": "Asteria (Conversational Female)", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "aura-luna-en", "name": "Luna (Warm Support)", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "aura-stella-en", "name": "Stella (Energetic Engagement)", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "aura-athena-en", "name": "Athena (Clear Articulation)", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "aura-orion-en", "name": "Orion (Authoritative Male)", "gender": "male", "languages": ["en-US"]},
    ],
    "azure": [
        {"voice_id": "hi-IN-SwaraNeural", "name": "Swara (Hindi Neural Female)", "gender": "female", "languages": ["hi-IN"]},
        {"voice_id": "hi-IN-MadhurNeural", "name": "Madhur (Hindi Neural Male)", "gender": "male", "languages": ["hi-IN"]},
        {"voice_id": "en-US-JennyNeural", "name": "Jenny (US English Neural Female)", "gender": "female", "languages": ["en-US"]},
        {"voice_id": "en-US-GuyNeural", "name": "Guy (US English Neural Male)", "gender": "male", "languages": ["en-US"]},
    ],
}

CURATED_PROVIDER_MODELS["gemini"] = [
    {"model_identifier": "gemini-3.8-flash-lite-tts", "display_name": "Google Gemini 3.8 Flash-Lite (Low-Latency TTS)", "layer": "tts", "recommended": True, "languages": ["hi-IN", "en-US", "fr-FR", "es-ES", "de-DE", "it-IT", "ja-JP", "nl-NL", "pt-BR", "ru-RU"]},
    {"model_identifier": "gemini-3.8-flash-tts", "display_name": "Google Gemini 3.8 Flash (High-Fidelity TTS)", "layer": "tts", "recommended": False, "languages": ["hi-IN", "en-US", "fr-FR", "es-ES", "de-DE", "it-IT", "ja-JP", "nl-NL", "pt-BR", "ru-RU"]},
    {"model_identifier": "gemini-3.1-flash-tts-preview", "display_name": "Google Gemini 3.1 Flash TTS (Legacy Preview)", "layer": "tts", "recommended": False, "languages": ["hi-IN", "en-US"]},
    {"model_identifier": "gemini-2.5-pro-preview-tts", "display_name": "Google Gemini 2.5 Pro Preview TTS", "layer": "tts", "recommended": False, "languages": ["hi-IN", "en-US"]},
]
CURATED_PROVIDER_VOICES["gemini"] = CURATED_PROVIDER_VOICES["google"]

for _model in CURATED_PROVIDER_MODELS["gemini"]:
    if _model["model_identifier"].startswith("gemini-3.8-"):
        _model["languages"] = list(dict.fromkeys(_model["languages"] + GEMINI_38_INDIC_TTS_LANGUAGES))
        if _model["model_identifier"] == "gemini-3.8-flash-tts":
            _model["languages"].append("sd-IN")

CURATED_PROVIDER_VOICES["gemini"] = [
    {**voice, "languages": list(dict.fromkeys(voice["languages"] + GEMINI_38_INDIC_TTS_LANGUAGES))}
    for voice in CURATED_PROVIDER_VOICES["google"]
]


class CatalogService:
    """Truth layer catalog service providing live capability manifests and dynamic caches."""

    def __init__(self):
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self.cache_ttl_seconds = 60

    def invalidate_cache(self) -> None:
        """Clear dynamic catalog cache across all organizations."""
        self._cache.clear()
        logger.info("[CatalogService] Catalog cache cleared.")

    async def notify_changed(self) -> None:
        """Invalidate available models on every API worker after a catalog mutation."""
        self.invalidate_cache()
        from api.services.worker_sync.manager import get_worker_sync_manager
        from api.services.worker_sync.protocol import WorkerSyncEventType
        try:
            await get_worker_sync_manager().broadcast(WorkerSyncEventType.MODEL_CATALOG, "update")
        except Exception as exc:
            logger.warning(f"Model catalog broadcast failed; cache TTL remains active: {exc}")

    async def seed_curated_models_if_needed(self, provider: str) -> None:
        """Seed built-in curated models for a provider into the database if missing."""
        raw_provider = (provider or "").lower().strip()
        prov_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
        models = CURATED_PROVIDER_MODELS.get(prov_norm, [])
        for m in models:
            existing = await kodewaves_db_client.get_model(m["model_identifier"])
            if not existing:
                await kodewaves_db_client.upsert_model(
                    model_identifier=m["model_identifier"],
                    display_name=m["display_name"],
                    provider=prov_norm,
                    layer=m["layer"],
                    enabled=True,
                    recommended=m.get("recommended", False),
                    source="built-in",
                    status="UNTESTED",
                    languages=m.get("languages", ["en-US"]),
                    supports_tools=m.get("supports_tools", False),
                    supports_streaming=True,
                )

        if prov_norm == "gemini":
            # The shared named speakers work across documented model languages.
            # Native directory locale != the model's entire language coverage.
            # Keep these model-scoped rows so e.g. Tamil isn't hidden merely
            # because a native locale directory page contains Hindi/English.
            rows = [dict(
                provider="gemini", tts_model=model["model_identifier"],
                voice_id=voice["voice_id"], name=voice["name"], gender=voice.get("gender"),
                languages=list(dict.fromkeys(voice.get("languages", []) + model.get("languages", []))),
                preview_ok=False, is_active=True,
            ) for model in CURATED_PROVIDER_MODELS.get("gemini", []) if model["layer"] == "tts"
              for voice in CURATED_PROVIDER_VOICES["google"]]
            if rows:
                await kodewaves_db_client.upsert_discovered_voices(rows)
            return

        voices = CURATED_PROVIDER_VOICES.get(prov_norm, [])
        for v in voices:
            await kodewaves_db_client.upsert_voice(
                provider=prov_norm,
                voice_id=v["voice_id"],
                name=v["name"],
                gender=v.get("gender"),
                languages=v.get("languages", ["en-US"]),
                preview_ok=True,
                is_active=True,
            )

    async def discover_provider(self, provider: str, creds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Discover models and voices for a provider using active credentials.
        Writes discovered capabilities into ai_model_catalog and voice_catalog.
        """
        raw_provider = (provider or "").lower().strip()
        prov_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
        if creds is None:
            creds = await master_credential_service.get_master_credential(prov_norm)

        api_key = (creds or {}).get("api_key") or ""
        discovered_models: List[str] = []
        discovered_voices: List[str] = []

        # 1. Seed base curated models first
        await self.seed_curated_models_if_needed(prov_norm)

        # 2. Live API discovery where supported
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if prov_norm in ("google", "gemini") and api_key:
                    url = "https://generativelanguage.googleapis.com/v1beta/models"
                    async with session.get(url, headers={"x-goog-api-key": api_key}, params={"pageSize": 1000}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("models", []):
                                name = m.get("name", "").replace("models/", "")
                                layer = google_model_layer(m)
                                if layer is None:
                                    continue
                                discovered_models.append(name)
                                await kodewaves_db_client.upsert_discovered_model(
                                    model_identifier=name,
                                    display_name=m.get("displayName") or name,
                                    provider="gemini" if layer == "tts" else "google",
                                    layer=layer,
                                    languages=next((entry.get("languages") for entry in CURATED_PROVIDER_MODELS["gemini"]
                                                    if entry["model_identifier"] == name), None),
                                )

                    speech_models = [model for model in discovered_models
                                     if model.startswith("gemini-3.8-") and "tts" in model]
                    if speech_models:
                        voice_rows = []
                        for voice in await discover_indian_voices(session, api_key):
                            discovered_voices.append(voice["voice_id"])
                            for speech_model in speech_models:
                                if (voice["languages"][0].split("-")[0].lower() == "sd"
                                        and "lite" in speech_model):
                                    continue
                                voice_rows.append(dict(
                                    provider="gemini", tts_model=speech_model, **voice,
                                    preview_ok=False, is_active=True,
                                ))
                        if voice_rows:
                            await kodewaves_db_client.upsert_discovered_voices(voice_rows)

                elif prov_norm == "openai" and api_key:
                    base_url = (creds or {}).get("base_url") or "https://api.openai.com/v1"
                    async with session.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("data", []):
                                mid = m.get("id", "")
                                if mid.startswith(("gpt-4", "gpt-3.5", "o1", "o3", "whisper", "tts")):
                                    discovered_models.append(mid)

                elif prov_norm == "groq" and api_key:
                    async with session.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("data", []):
                                mid = m.get("id", "")
                                discovered_models.append(mid)

                elif prov_norm == "cartesia" and api_key:
                    async with session.get("https://api.cartesia.ai/voices", headers={"X-API-Key": api_key, "Cartesia-Version": "2024-06-10"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for v in (data if isinstance(data, list) else data.get("voices", [])):
                                vid = v.get("id")
                                vname = v.get("name") or vid
                                if vid:
                                    discovered_voices.append(vid)
                                    await kodewaves_db_client.upsert_voice(
                                        provider="cartesia",
                                        voice_id=vid,
                                        name=vname,
                                        gender=v.get("gender"),
                                        languages=[v.get("language")] if v.get("language") else ["en"],
                                    )

                elif prov_norm == "elevenlabs" and api_key:
                    async with session.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": api_key}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for v in data.get("voices", []):
                                vid = v.get("voice_id")
                                vname = v.get("name") or vid
                                if vid:
                                    discovered_voices.append(vid)
                                    await kodewaves_db_client.upsert_voice(
                                        provider="elevenlabs",
                                        voice_id=vid,
                                        name=vname,
                                        gender=v.get("labels", {}).get("gender"),
                                        preview_url=v.get("preview_url"),
                                    )

                elif prov_norm == "piper":
                    piper_url = os.environ.get("PIPER_ENDPOINT", "http://piper:5000")
                    async with session.get(f"{piper_url.rstrip('/')}/voices") as resp:
                        if resp.status == 200:
                            vdata = await resp.json()
                            vdict = vdata if isinstance(vdata, dict) else {x: x for x in vdata}
                            for vid, vinfo in vdict.items():
                                name = vinfo.get("name") if isinstance(vinfo, dict) else vid
                                language_info = vinfo.get("language") if isinstance(vinfo, dict) else None
                                language_code = language_info.get("code") if isinstance(language_info, dict) else None
                                if not language_code:
                                    language_code = vid.split("-", 1)[0]
                                language_code = language_code.replace("_", "-")
                                language_parts = language_code.split("-")
                                if len(language_parts) != 2 or not all(part.isalpha() for part in language_parts):
                                    logger.warning(f"[CatalogService] Skipping Piper voice with invalid language: {vid}")
                                    continue
                                discovered_voices.append(vid)
                                await kodewaves_db_client.upsert_voice(
                                    provider="piper",
                                    voice_id=vid,
                                    name=name or vid,
                                    languages=[language_code],
                                )
        except Exception as e:
            logger.debug(f"[CatalogService] Discovery error for {prov_norm}: {e}")

        self.invalidate_cache()
        return {
            "provider": prov_norm,
            "discovered_models": discovered_models,
            "discovered_voices": discovered_voices,
        }

    async def _get_test_model_for_layer(
        self,
        provider: str,
        layer: str,
        creds: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Dynamically determine an active, valid model identifier to verify a provider's capability layer.
        1. Checks DB ai_model_catalog for provider=prov_norm, layer=layer_norm, enabled=True.
        2. If none in DB, calls live discovery API for the provider.
        3. If live discovery fails, checks CURATED_PROVIDER_MODELS in memory.
        4. Returns None if no model is available.
        """
        raw_provider = (provider or "").lower().strip()
        prov_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
        layer_norm = layer.lower().strip()
        api_key = (creds or {}).get("api_key") or ""

        # 1. Query database catalog
        try:
            db_models = await kodewaves_db_client.list_models(
                layer=layer_norm,
                provider=prov_norm,
                enabled_only=True,
            )
            if prov_norm == "gemini" and layer_norm != "tts":
                db_models += await kodewaves_db_client.list_models(
                    layer=layer_norm,
                    provider="google",
                    enabled_only=True,
                )
            if db_models:
                recom = [m for m in db_models if getattr(m, "recommended", False)]
                target = recom[0] if recom else db_models[0]
                return target.model_identifier
        except Exception as e:
            logger.debug(f"[CatalogService] DB query for test model failed: {e}")

        # 2. Live API discovery fallback if catalog has not yet been seeded
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if prov_norm in ("google", "gemini") and api_key:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("models", []):
                                name = m.get("name", "").replace("models/", "")
                                methods = m.get("supportedGenerationMethods", [])
                                if layer_norm == "llm" and "generateContent" in methods and "tts" not in name and "live" not in name:
                                    asyncio.create_task(self.discover_provider(prov_norm, creds=creds))
                                    return name

                elif prov_norm == "anthropic" and api_key:
                    url = "https://api.anthropic.com/v1/models"
                    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("data", []):
                                mid = m.get("id", "")
                                if mid.startswith("claude-"):
                                    asyncio.create_task(self.discover_provider(prov_norm, creds=creds))
                                    return mid

                elif prov_norm == "openai" and api_key:
                    base_url = (creds or {}).get("base_url") or "https://api.openai.com/v1"
                    url = f"{base_url.rstrip('/')}/models"
                    async with session.get(url, headers={"Authorization": f"Bearer {api_key}"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m.get("id", "") for m in data.get("data", [])]
                            for pref in ("gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"):
                                if pref in models:
                                    return pref
                            for mid in models:
                                if mid.startswith("gpt-"):
                                    return mid

                elif prov_norm == "groq" and api_key:
                    url = "https://api.groq.com/openai/v1/models"
                    async with session.get(url, headers={"Authorization": f"Bearer {api_key}"}) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = [m.get("id", "") for m in data.get("data", [])]
                            for pref in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
                                if pref in models:
                                    return pref
                            if models:
                                return models[0]

                elif prov_norm == "ollama":
                    ollama_url = os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")
                    async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            models = data.get("models", [])
                            if models:
                                return models[0].get("name", "llama3.2")
        except Exception as e:
            logger.debug(f"[CatalogService] Live model discovery for test failed: {e}")

        # 3. Curated built-in fallback
        curated = [m for m in CURATED_PROVIDER_MODELS.get(prov_norm, []) if m.get("layer") == layer_norm]
        if curated:
            return curated[0]["model_identifier"]

        return None

    async def verify_layer(
        self,
        provider: str,
        layer: str,
        creds: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Perform real execution test for a provider's capability layer.
        Writes result to catalog_verify_runs and updates model status in catalog.
        """
        raw_provider = (provider or "").lower().strip()
        prov_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
        layer_norm = layer.lower().strip()

        if creds is None:
            creds = await master_credential_service.get_master_credential(
                "gemini" if prov_norm == "gemini" else prov_norm
            )

        if not creds and prov_norm not in ("piper", "whisper", "ollama"):
            error_msg = f"No active credentials configured for provider '{provider}'"
            await kodewaves_db_client.record_verify_run(
                provider=prov_norm,
                layer=layer_norm,
                status="FAIL",
                error_message=error_msg,
            )
            return False, None, error_msg

        start_time = time.monotonic()
        success = False
        error_msg: Optional[str] = None
        executed_model: str | None = None

        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. LLM Verification
                if layer_norm == "llm":
                    test_model = await self._get_test_model_for_layer(prov_norm, layer_norm, creds)
                    if not test_model and prov_norm not in ("piper", "whisper", "ollama"):
                        error_msg = f"No models available for {prov_norm}/{layer_norm} to verify against"
                        await kodewaves_db_client.record_verify_run(
                            provider=prov_norm,
                            layer=layer_norm,
                            status="FAIL",
                            error_message=error_msg,
                        )
                        return False, None, error_msg

                    api_key = creds.get("api_key", "")
                    if prov_norm in ("google", "gemini"):
                        executed_model = test_model
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent"
                        payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
                        async with session.post(url, json=payload, headers={"x-goog-api-key": api_key}) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                err_txt = await resp.text()
                                error_msg = f"Gemini LLM returned HTTP status {resp.status}: {err_txt[:100]}"

                    elif prov_norm == "openai":
                        executed_model = test_model
                        base_url = (creds or {}).get("base_url") or "https://api.openai.com/v1"
                        url = f"{base_url.rstrip('/')}/chat/completions"
                        payload = {"model": test_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
                        async with session.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                err_txt = await resp.text()
                                error_msg = f"OpenAI chat completions returned HTTP {resp.status}: {err_txt[:100]}"

                    elif prov_norm == "anthropic":
                        executed_model = test_model
                        url = "https://api.anthropic.com/v1/messages"
                        payload = {
                            "model": test_model,
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 5,
                        }
                        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                        async with session.post(url, headers=headers, json=payload) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                err_txt = await resp.text()
                                error_msg = f"Anthropic returned HTTP status {resp.status}: {err_txt[:100]}"

                    elif prov_norm == "groq":
                        executed_model = test_model
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        payload = {"model": test_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
                        async with session.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                err_txt = await resp.text()
                                error_msg = f"Groq returned HTTP status {resp.status}: {err_txt[:100]}"

                    elif prov_norm == "ollama":
                        ollama_url = os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")
                        async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                error_msg = f"Ollama returned HTTP status {resp.status}"

                    else:
                        success, message = await master_credential_service.test_connection(prov_norm)
                        if not success:
                            error_msg = message

                # 2. STT Verification
                elif layer_norm == "stt":
                    test_model = await self._get_test_model_for_layer(prov_norm, layer_norm, creds)
                    if prov_norm == "deepgram":
                        api_key = creds.get("api_key", "")
                        stt_model = test_model or "nova-3"
                        url = f"https://api.deepgram.com/v1/listen?model={stt_model}"
                        async with session.post(url, headers={"Authorization": f"Token {api_key}"}, data=b"RIFF....") as resp:
                            # 200 or 400 with audio error means valid authentication! 401 means invalid
                            if resp.status in (200, 400):
                                success = True
                            else:
                                error_msg = f"Deepgram STT returned HTTP status {resp.status}"
                    else:
                        success, message = await master_credential_service.test_connection(prov_norm)
                        if not success:
                            error_msg = message

                # 3. TTS Verification
                elif layer_norm == "tts":
                    if prov_norm == "gemini":
                        test_model = await self._get_test_model_for_layer(
                            prov_norm, layer_norm, creds
                        )
                        if not test_model:
                            error_msg = "No Gemini TTS model is enabled in the catalog"
                        else:
                            executed_model = test_model
                            url = (
                                "https://generativelanguage.googleapis.com/v1beta/models/"
                                f"{test_model}:generateContent"
                            )
                            part = {"text": "नमस्ते, यह आवाज़ की जाँच है।"}
                            if test_model.startswith("gemini-3.8-"):
                                part["speech_metadata"] = {
                                    "style": "natural, relaxed conversational delivery"
                                }
                                voice_config = {"voice": "Kore"}
                            else:
                                # Earlier TTS models reject turn-level metadata
                                # and require the legacy prebuilt voice shape.
                                voice_config = {
                                    "prebuiltVoiceConfig": {"voiceName": "Kore"}
                                }
                            payload = {
                                "contents": [{"role": "user", "parts": [part]}],
                                "generationConfig": {
                                    "responseModalities": ["AUDIO"],
                                    "speechConfig": {"voiceConfig": voice_config},
                                },
                            }
                            async with session.post(
                                url,
                                headers={"x-goog-api-key": creds.get("api_key", "")},
                                json=payload,
                            ) as resp:
                                if resp.status == 200:
                                    body = await resp.json()
                                    success = any(
                                        part.get("inlineData", {}).get("data")
                                        for candidate in body.get("candidates", [])
                                        for part in candidate.get("content", {}).get("parts", [])
                                    )
                                    if not success:
                                        error_msg = "Gemini TTS verification returned no audio"
                                else:
                                    error_msg = f"Gemini TTS returned HTTP {resp.status}: {(await resp.text())[:100]}"
                    elif prov_norm == "cartesia":
                        api_key = creds.get("api_key", "")
                        async with session.get("https://api.cartesia.ai/voices", headers={"X-API-Key": api_key, "Cartesia-Version": "2024-06-10"}) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                error_msg = f"Cartesia TTS returned HTTP {resp.status}"
                    elif prov_norm == "elevenlabs":
                        api_key = creds.get("api_key", "")
                        async with session.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": api_key}) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                error_msg = f"ElevenLabs TTS returned HTTP {resp.status}"
                    elif prov_norm == "piper":
                        piper_url = os.environ.get("PIPER_ENDPOINT", "http://piper:5000")
                        async with session.get(f"{piper_url.rstrip('/')}/voices") as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                error_msg = f"Piper TTS returned HTTP {resp.status}"
                    else:
                        success, message = await master_credential_service.test_connection(prov_norm)
                        if not success:
                            error_msg = message

                # 4. S2S / Realtime Verification
                elif layer_norm in ("s2s", "realtime"):
                    success, message = await master_credential_service.test_connection(prov_norm)
                    if not success:
                        error_msg = message

                # 5. Embeddings Verification
                elif layer_norm == "embeddings":
                    success, message = await master_credential_service.test_connection(prov_norm)
                    if not success:
                        error_msg = message

                else:
                    success, message = await master_credential_service.test_connection(prov_norm)
                    if not success:
                        error_msg = message

        except Exception as ex:
            success = False
            error_msg = str(ex)

        latency_ms = int((time.monotonic() - start_time) * 1000)
        # A successful auth/voice-list probe does not execute a model. Do not
        # certify all models in a provider layer from that weaker evidence.
        status_str = ("PASS" if success else "FAIL") if executed_model else "UNTESTED"

        # Record test run in DB if reachable
        db_provider = "google" if prov_norm == "gemini" and layer_norm != "tts" else prov_norm
        try:
            await kodewaves_db_client.record_verify_run(
                provider=db_provider,
                layer=layer_norm,
                status=status_str,
                latency_ms=latency_ms,
                error_message=error_msg,
            )

            # Update models in database
            if executed_model:
                await kodewaves_db_client.update_model_verification_status(
                    provider=db_provider,
                    layer=layer_norm,
                    model_identifier=executed_model,
                    status=status_str,
                    latency_ms=latency_ms,
                    error_message=error_msg,
                )
        except Exception as dberr:
            logger.debug(f"[CatalogService] DB logging skipped (offline): {dberr}")

        await self.notify_changed()
        return success, latency_ms, error_msg

    async def verify_provider_all_layers(
        self,
        provider: str,
        creds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify all layers supported by a provider."""
        raw_provider = (provider or "").lower().strip()
        prov_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(provider)
        models = list(CURATED_PROVIDER_MODELS.get(prov_norm, []))
        if prov_norm == "gemini":
            models.extend(CURATED_PROVIDER_MODELS.get("google", []))
        layers = list({m["layer"] for m in models})

        try:
            db_models = await kodewaves_db_client.list_models(provider=prov_norm, enabled_only=False)
            if prov_norm == "gemini":
                db_models += await kodewaves_db_client.list_models(provider="google", enabled_only=False)
            for m in db_models:
                if m.layer and m.layer not in layers:
                    layers.append(m.layer)
        except Exception:
            pass

        if not layers:
            layers = ["llm"]

        results = {}
        for layer in layers:
            ok, lat, err = await self.verify_layer(prov_norm, layer, creds=creds)
            results[layer] = {"success": ok, "latency_ms": lat, "error": err}
        return results

    async def get_available_catalog(
        self,
        organization_id: int,
        user_has_local_ai: bool = False,
    ) -> Dict[str, Any]:
        """
        Dynamically build catalog for an organization according to visibility rules.
        60s cache with immediate invalidation on key change.
        """
        cache_key = f"{organization_id}:{user_has_local_ai}"
        now = time.monotonic()
        if cache_key in self._cache:
            ts, val = self._cache[cache_key]
            if now - ts < self.cache_ttl_seconds:
                return val

        # 1. Fetch active credentials in platform_master_credentials
        master_creds = await kodewaves_db_client.list_master_credentials()
        active_providers: Set[str] = set()
        for r in master_creds:
            if r.is_enabled and r.credentials_encrypted:
                raw_provider = str(r.provider).lower().strip()
                p_norm = "gemini" if raw_provider == "gemini" else normalize_provider_name(r.provider)
                active_providers.add(p_norm)
                # Keep original alias accessible
                active_providers.add(r.provider.lower().strip())

        # Also check org policy if any
        org_policy = await kodewaves_db_client.get_org_ai_policy(organization_id)
        local_allowed = org_policy.local_allowed if org_policy else True
        s2s_allowed = org_policy.s2s_allowed if org_policy else True

        # Ensure seed data exists for active providers
        for p in active_providers:
            await self.seed_curated_models_if_needed(p)

        # 2. Query enabled models from database
        all_models = await kodewaves_db_client.list_models(enabled_only=True)

        cloud_llm: List[Dict[str, Any]] = []
        cloud_stt: List[Dict[str, Any]] = []
        cloud_tts: List[Dict[str, Any]] = []
        cloud_s2s: List[Dict[str, Any]] = []

        for m in all_models:
            raw_provider = str(m.provider).lower().strip()
            prov = "gemini" if raw_provider == "gemini" else normalize_provider_name(m.provider)
            # Visibility rule: Provider key active AND status != 'FAIL' AND status != 'UNAVAILABLE'
            credential_provider = (
                _tts_model_credential_provider(prov, m.model_identifier)
                if (m.layer or m.category) == "tts"
                else prov
            )
            if (credential_provider not in active_providers
                    and m.provider.lower().strip() not in active_providers):
                continue
            if m.status in ("FAIL", "UNAVAILABLE"):
                continue
            if (prov in ("google", "gemini")
                    and any(kind in m.model_identifier.lower() for kind in
                            ("image", "nano-banana", "computer-use", "robotics", "translate"))):
                continue
            if ((m.layer or m.category) in ("s2s", "realtime") and prov in ("google", "gemini")
                    and "transcribe" in m.model_identifier.lower()):
                continue
            if ((m.layer or m.category) == "llm" and prov in ("google", "gemini")
                    and google_model_layer({"name": f"models/{m.model_identifier}",
                                            "supportedGenerationMethods": ["generateContent"]}) != "llm"):
                # Older discovery incorrectly put image, embedding and task
                # specific models into the voice agent's chat-model menu.
                continue

            entry = {
                "value": m.model_identifier,
                "label": f"{m.display_name} ★" if m.recommended else m.display_name,
                "provider": m.provider,
                "has_master_key": True,
                "recommended": m.recommended,
                "supports_tools": m.supports_tools,
                "supports_streaming": m.supports_streaming,
                "verification_status": m.status,
                "languages": m.languages or [],
                "supports_auto_detect": (
                    (m.layer or m.category) == "stt"
                    and stt_model_supports_auto_detect(prov, m.model_identifier)
                ),
            }

            layer = m.layer or m.category
            if layer == "llm":
                cloud_llm.append(entry)
            elif layer == "stt":
                cloud_stt.append(entry)
            elif layer == "tts":
                cloud_tts.append(entry)
            elif layer == "s2s" and s2s_allowed:
                cloud_s2s.append(entry)

        # 3. Local Models (only if local AI is enabled & healthy)
        installed_local_llm: List[Dict[str, Any]] = []
        local_stt: List[Dict[str, Any]] = []
        local_tts: List[Dict[str, Any]] = []

        local_ai_setting = await kodewaves_db_client.get_setting("local_ai") or {}
        org_access = await kodewaves_db_client.get_setting(f"local_ai_org_{organization_id}") or {}
        public_access = local_ai_setting.get("local_ai_access_policy", "public") in ("public", "all_workspaces")
        local_access = public_access or bool(org_access.get("enabled", False))
        local_engine_enabled = bool(local_ai_setting.get("enable_local_ai_engine", False) and local_allowed and local_access)

        if local_engine_enabled:
            # Check Ollama installed models
            ollama_url = local_ai_setting.get("ollama_endpoint") or os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")
            ollama_url = normalize_local_ai_endpoint(ollama_url).rstrip("/").removesuffix("/v1")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m_obj in data.get("models", []):
                                name = m_obj.get("name", "")
                                size_gb = round(m_obj.get("size", 0) / (1024 ** 3), 1)
                                label = f"{name} ({size_gb} GB download)" if size_gb > 0 else name
                                if name:
                                    installed_local_llm.append({"value": name, "label": label, "provider": "ollama"})
            except Exception:
                pass

            # Do not offer Faster-Whisper for new self-hosted selections. Keep
            # its runtime adapter for existing saved agents until they migrate.
            # Advertise the CPU Indic recognizer only when its weights and
            # selected language checkpoints are present in the running sidecar.
            indic_stt_url = local_ai_setting.get("indic_stt_endpoint") or os.environ.get(
                "INDIC_STT_ENDPOINT", "http://indic-stt:8000/v1"
            )
            indic_stt_url = whisper_api_base(normalize_local_ai_endpoint(indic_stt_url))
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
                    async with session.get(f"{indic_stt_url.rstrip('/')}/models") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for installed_model in data.get("data", []):
                                if (isinstance(installed_model, dict)
                                        and installed_model.get("task") == "automatic-speech-recognition"
                                        and installed_model.get("installed", True)
                                        and installed_model.get("id")):
                                    local_stt.append({
                                        "value": installed_model["id"],
                                        "label": (
                                            "IndicConformer CTC INT8 + Moonshine English (installed languages)"
                                            if "en-IN" in installed_model.get("languages", [])
                                            else "IndicConformer CTC INT8 (installed languages)"
                                        ),
                                        "provider": "indicconformer",
                                        "languages": installed_model.get("languages", []),
                                        "supports_auto_detect": False,
                                    })
            except (aiohttp.ClientError, TimeoutError):
                pass

            # Advertise DhVaani only when its local checkpoint and licensed
            # reference voices are loaded and reported by the serving engine.
            try:
                dhvaani_url = local_tts_api_base(local_ai_setting, "dhvaani-0.5")
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
                    async with session.get(f"{dhvaani_url}/models") as resp:
                        if resp.status == 200:
                            for dhvaani_model in (await resp.json()).get("data", []):
                                if (
                                    isinstance(dhvaani_model, dict)
                                    and dhvaani_model.get("id") == "dhvaani-0.5"
                                    and dhvaani_model.get("task") == "text-to-speech"
                                    and dhvaani_model.get("installed") is True
                                ):
                                    local_tts.append({
                                        "value": dhvaani_model["id"],
                                        "label": dhvaani_model.get("name") or "DhVaani 0.5 — Indian languages + English",
                                        "provider": "speaches",
                                        "languages": dhvaani_model.get("languages", []),
                                        "voices": dhvaani_model.get("voices", []),
                                        "streaming": dhvaani_model.get("streaming", False),
                                    })
            except (aiohttp.ClientError, TimeoutError):
                pass

            # Show only TTS models actually installed on the local Speaches server.
            speaches_url = local_ai_setting.get("whisper_endpoint") or os.environ.get(
                "WHISPER_ENDPOINT", "http://whisper:8000/v1"
            )
            speaches_url = whisper_api_base(normalize_local_ai_endpoint(speaches_url))
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
                    async with session.get(f"{speaches_url.rstrip('/')}/models") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for installed_model in data.get("data", []):
                                if (isinstance(installed_model, dict)
                                        and installed_model.get("task") == "text-to-speech"
                                        and installed_model.get("installed") is not False
                                        and installed_model.get("id")):
                                    model_id = installed_model["id"]
                                    local_tts.append({
                                        "value": model_id,
                                        "label": model_id.split("/")[-1] + " (Local CPU)",
                                        "provider": "speaches",
                                        # Keep the installed engine's real support
                                        # boundary visible to model configuration.
                                        "languages": installed_model.get("languages", []),
                                        "voices": installed_model.get("voices", []),
                                        "streaming": installed_model.get("streaming", False),
                                    })
            except Exception:
                pass

            # Regional VITS voices are selectable only after their CPU sidecar
            # is ready. Keep its 13-language boundary and speaker metadata.
            try:
                regional_models = await get_local_tts_models(
                    local_tts_api_base(local_ai_setting, "indic-vits-rasa-13")
                )
                regional_model = regional_models.get("indic-vits-rasa-13")
                if regional_model and regional_model.get("installed") is True:
                    local_tts.append({
                        "value": regional_model["id"],
                        "label": regional_model.get("name") or "Kodewaves Regional + Hindi + Indian English (CPU)",
                        "provider": "speaches",
                        "languages": regional_model.get("languages", []),
                        "voices": regional_model.get("voices", []),
                        "streaming": regional_model.get("streaming", False),
                    })
            except (aiohttp.ClientError, TimeoutError):
                pass

            # Only expose Parler after the offline checkpoint has loaded.
            try:
                parler_models = await get_local_tts_models(
                    local_tts_api_base(local_ai_setting, "indic-parler-tts")
                )
                parler_model = parler_models.get("indic-parler-tts")
                if parler_model and parler_model.get("installed") is True:
                    local_tts.append({
                        "value": parler_model["id"],
                        "label": parler_model.get("name") or "Indic-Parler — Indian languages + English (CPU)",
                        "provider": "speaches",
                        "languages": parler_model.get("languages", []),
                        "voices": parler_model.get("voices", []),
                        "streaming": parler_model.get("streaming", False),
                    })
            except (aiohttp.ClientError, TimeoutError):
                pass

            # Indic-Mio is served by its own CPU LiteRT sidecar. Read its live
            # inventory so a model is selectable only after its bundle loads.
            indic_mio_url = local_tts_api_base(local_ai_setting, "indic-mio-tts")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.5)) as session:
                    async with session.get(f"{indic_mio_url}/models") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for installed_model in data.get("data", []):
                                if (
                                    isinstance(installed_model, dict)
                                    and installed_model.get("task") == "text-to-speech"
                                    and installed_model.get("id") == "indic-mio-tts"
                                    and installed_model.get("installed") is True
                                ):
                                    local_tts.append({
                                        "value": installed_model["id"],
                                        "label": installed_model.get(
                                            "name",
                                            "Indic-Mio 0.6B — 22 Indian languages + English (CPU)",
                                        ),
                                        "provider": "speaches",
                                        "languages": installed_model.get("languages", []),
                                        "voices": installed_model.get("voices", []),
                                        "streaming": installed_model.get("streaming", False),
                                    })
            except Exception:
                pass

        # Prepend 'auto' item ONLY if cloud models exist
        if cloud_llm:
            cloud_llm.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": True})
        if cloud_stt:
            cloud_stt.insert(0, {
                "value": "auto",
                "label": "Auto model selection (language detection depends on that model)",
                "provider": "auto",
                "has_master_key": True,
                "supports_auto_detect": False,
            })
        if cloud_tts:
            cloud_tts.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": True})
        if cloud_s2s:
            cloud_s2s.insert(0, {"value": "auto", "label": "Auto (Recommended S2S)", "provider": "auto", "has_master_key": True})

        manifest = {
            "active_providers": list(active_providers),
            "cloud_llm_models": cloud_llm,
            "cloud_stt_models": cloud_stt,
            "cloud_tts_models": cloud_tts,
            "cloud_s2s_models": cloud_s2s,
            "local_llm_models": installed_local_llm,
            "local_stt_models": local_stt,
            "local_tts_models": local_tts,
            "local_engine_enabled": local_engine_enabled,
            "has_local_ai_access": bool(local_allowed and local_access),
            "supported_modes": ["general", "realtime"],
        }

        self._cache[cache_key] = (now, manifest)
        return manifest


catalog_service = CatalogService()


async def handle_catalog_sync(_event) -> None:
    catalog_service.invalidate_cache()
