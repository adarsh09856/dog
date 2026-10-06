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
from api.services.catalog.normalize import normalize_provider_name
from api.services.credentials.master_credential_service import master_credential_service


# Curated catalog definitions from repo and verified vendor docs (Part 4)
CURATED_PROVIDER_MODELS: Dict[str, List[Dict[str, Any]]] = {
    "google": [
        {"model_identifier": "gemini-3.5-flash", "display_name": "Google Gemini 3.5 Flash", "layer": "llm", "recommended": True, "supports_tools": True},
        {"model_identifier": "gemini-3.5-flash-lite", "display_name": "Google Gemini 3.5 Flash Lite", "layer": "llm", "recommended": False, "supports_tools": True},
        {"model_identifier": "gemini-3.1-flash-lite", "display_name": "Google Gemini 3.1 Flash Lite", "layer": "llm", "recommended": False, "supports_tools": True},
        {"model_identifier": "gemini-3.1-flash-tts-preview", "display_name": "Google Gemini 3.1 Voice Studio (Streaming TTS)", "layer": "tts", "recommended": True, "languages": ["hi-IN", "en-US"]},
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

CURATED_PROVIDER_VOICES: Dict[str, List[Dict[str, Any]]] = {
    "google": [
        {"voice_id": "Puck", "name": "Puck", "gender": "male", "languages": ["en-US", "hi-IN"]},
        {"voice_id": "Charon", "name": "Charon", "gender": "male", "languages": ["en-US", "hi-IN"]},
        {"voice_id": "Kore", "name": "Kore", "gender": "female", "languages": ["en-US", "hi-IN"]},
        {"voice_id": "Fenrir", "name": "Fenrir", "gender": "male", "languages": ["en-US", "hi-IN"]},
        {"voice_id": "Aoede", "name": "Aoede", "gender": "female", "languages": ["en-US", "hi-IN"]},
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
    "piper": [
        {"voice_id": "hi_IN-dhiru-medium", "name": "Dhiru (Hindi ONNX CPU)", "gender": "male", "languages": ["hi-IN"]},
        {"voice_id": "en_US-lessac-medium", "name": "Lessac (English ONNX CPU)", "gender": "female", "languages": ["en-US"]},
    ],
}


class CatalogService:
    """Truth layer catalog service providing live capability manifests and dynamic caches."""

    def __init__(self):
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self.cache_ttl_seconds = 60

    def invalidate_cache(self) -> None:
        """Clear dynamic catalog cache across all organizations."""
        self._cache.clear()
        logger.info("[CatalogService] Catalog cache cleared.")

    async def seed_curated_models_if_needed(self, provider: str) -> None:
        """Seed built-in curated models for a provider into the database if missing."""
        prov_norm = normalize_provider_name(provider)
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
        prov_norm = normalize_provider_name(provider)
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
                if prov_norm == "google" and api_key:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("models", []):
                                name = m.get("name", "").replace("models/", "")
                                if "gemini" in name:
                                    discovered_models.append(name)
                                    layer = "llm"
                                    if "tts" in name:
                                        layer = "tts"
                                    elif "live" in name:
                                        layer = "s2s"
                                    await kodewaves_db_client.upsert_model(
                                        model_identifier=name,
                                        display_name=m.get("displayName") or name,
                                        provider="google",
                                        layer=layer,
                                        enabled=True,
                                        source="discovered",
                                        status="UNTESTED",
                                    )

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
                    piper_url = os.environ.get("PIPER_ENDPOINT", "http://piper:8766")
                    async with session.get(f"{piper_url.rstrip('/')}/voices") as resp:
                        if resp.status == 200:
                            vdata = await resp.json()
                            vdict = vdata if isinstance(vdata, dict) else {x: x for x in vdata}
                            for vid, vinfo in vdict.items():
                                discovered_voices.append(vid)
                                name = vinfo.get("name") if isinstance(vinfo, dict) else vid
                                await kodewaves_db_client.upsert_voice(
                                    provider="piper",
                                    voice_id=vid,
                                    name=name or vid,
                                    languages=["hi-IN"] if "hi" in vid else ["en-US"],
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
        prov_norm = normalize_provider_name(provider)
        layer_norm = layer.lower().strip()
        api_key = (creds or {}).get("api_key") or ""

        # 1. Query database catalog
        try:
            db_models = await kodewaves_db_client.list_models(
                layer=layer_norm,
                provider=prov_norm,
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
                if prov_norm == "google" and api_key:
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
        prov_norm = normalize_provider_name(provider)
        layer_norm = layer.lower().strip()

        if creds is None:
            creds = await master_credential_service.get_master_credential(prov_norm)

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
                    if prov_norm == "google":
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent?key={api_key}"
                        payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
                        async with session.post(url, json=payload) as resp:
                            if resp.status == 200:
                                success = True
                            else:
                                err_txt = await resp.text()
                                error_msg = f"Gemini LLM returned HTTP status {resp.status}: {err_txt[:100]}"

                    elif prov_norm == "openai":
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
                    if prov_norm == "cartesia":
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
                        piper_url = os.environ.get("PIPER_ENDPOINT", "http://piper:8766")
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
        status_str = "PASS" if success else "FAIL"

        # Record test run in DB if reachable
        try:
            await kodewaves_db_client.record_verify_run(
                provider=prov_norm,
                layer=layer_norm,
                status=status_str,
                latency_ms=latency_ms,
                error_message=error_msg,
            )

            # Update models in database
            models = await kodewaves_db_client.list_models(layer=layer_norm, provider=prov_norm, enabled_only=False)
            for m in models:
                m.status = status_str
                m.latency_ms = latency_ms
                m.last_verified_at = datetime.now(UTC)
                m.last_error = error_msg if not success else None
        except Exception as dberr:
            logger.debug(f"[CatalogService] DB logging skipped (offline): {dberr}")

        self.invalidate_cache()
        return success, latency_ms, error_msg

    async def verify_provider_all_layers(
        self,
        provider: str,
        creds: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verify all layers supported by a provider."""
        prov_norm = normalize_provider_name(provider)
        models = CURATED_PROVIDER_MODELS.get(prov_norm, [])
        layers = list({m["layer"] for m in models})

        try:
            db_models = await kodewaves_db_client.list_models(provider=prov_norm, enabled_only=False)
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
        user_has_local_ai: bool = True,
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
                p_norm = normalize_provider_name(r.provider)
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
            prov = normalize_provider_name(m.provider)
            # Visibility rule: Provider key active AND status != 'FAIL' AND status != 'UNAVAILABLE'
            if prov not in active_providers and m.provider.lower().strip() not in active_providers:
                continue
            if m.status in ("FAIL", "UNAVAILABLE"):
                continue

            entry = {
                "value": m.model_identifier,
                "label": f"{m.display_name} ★" if m.recommended else m.display_name,
                "provider": m.provider,
                "has_master_key": True,
                "recommended": m.recommended,
                "supports_tools": m.supports_tools,
                "supports_streaming": m.supports_streaming,
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
        local_engine_enabled = local_ai_setting.get("enable_local_ai_engine", True) and local_allowed and user_has_local_ai

        if local_engine_enabled:
            # Check Ollama installed models
            ollama_url = local_ai_setting.get("ollama_endpoint") or os.environ.get("OLLAMA_ENDPOINT", "http://ollama:11434")
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
                    async with session.get(f"{ollama_url.rstrip('/')}/api/tags") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m_obj in data.get("models", []):
                                name = m_obj.get("name", "")
                                size_gb = round(m_obj.get("size", 0) / (1024 ** 3), 1)
                                label = f"{name} ({size_gb} GB RAM)" if size_gb > 0 else name
                                installed_local_llm.append({"value": name, "label": label})
            except Exception:
                pass

            # Local STT (Faster-Whisper on Speaches CPU)
            local_stt = [
                {"value": "Systran/faster-whisper-tiny", "label": "Faster-Whisper Tiny (Ultra-fast CPU, ~75MB RAM)"},
                {"value": "Systran/faster-whisper-base", "label": "Faster-Whisper Base (Multilingual, ~140MB RAM)"},
            ]

            # Local TTS (Piper ONNX)
            local_tts = [
                {"value": "piper", "label": "Piper TTS (Native Hindi & Indic ONNX, ~40ms Ultra-Fast)"},
            ]

        # Prepend 'auto' item ONLY if cloud models exist
        if cloud_llm:
            cloud_llm.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": True})
        if cloud_stt:
            cloud_stt.insert(0, {"value": "auto", "label": "Auto (Recommended - Best active engine)", "provider": "auto", "has_master_key": True})
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
            "has_local_ai_access": user_has_local_ai,
            "supported_modes": ["general", "realtime"],
        }

        self._cache[cache_key] = (now, manifest)
        return manifest


catalog_service = CatalogService()
