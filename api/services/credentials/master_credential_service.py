import base64
import json
import os
import hashlib
from datetime import UTC, datetime
from typing import Any, Dict, Optional, Tuple

import aiohttp
from cryptography.fernet import Fernet
from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client


class MasterCredentialService:
    """Service to securely store, retrieve, encrypt, decrypt, and validate platform master credentials."""

    def __init__(self):
        # Generate or load a 32-byte URL-safe base64-encoded key for Fernet
        raw_secret = (
            os.environ.get("MASTER_CREDENTIAL_ENCRYPTION_KEY")
            or os.environ.get("KODEWAVES_SECRET_KEY")
            or os.environ.get("OSS_JWT_SECRET")
            or os.environ.get("JWT_SECRET")
            or "kodewaves-master-sovereign-secret-key-32b"
        )
        try:
            # If already a valid 32-byte urlsafe-base64 Fernet key
            self._cipher = Fernet(raw_secret.encode())
        except Exception:
            # Otherwise derive 32-byte key via SHA-256
            key = base64.urlsafe_b64encode(hashlib.sha256(raw_secret.encode()).digest())
            self._cipher = Fernet(key)

    def encrypt(self, plain_text: str) -> str:
        """Encrypt plain text to base64 string."""
        return self._cipher.encrypt(plain_text.encode()).decode()

    def decrypt(self, cipher_text: str) -> str:
        """Decrypt cipher text back to plain text."""
        return self._cipher.decrypt(cipher_text.encode()).decode()

    async def save_master_credential(
        self,
        provider: str,
        category: str,
        credentials_dict: Dict[str, Any],
        is_enabled: bool = True,
    ) -> bool:
        """Encrypt and store credentials JSON for a provider."""
        try:
            payload_str = json.dumps(credentials_dict)
            encrypted_str = self.encrypt(payload_str)
            await kodewaves_db_client.upsert_master_credential(
                provider=provider.lower().strip(),
                category=category.lower().strip(),
                credentials_encrypted=encrypted_str,
                is_enabled=is_enabled,
                health_status="unknown",
            )
            logger.info(f"[MasterCredentialService] Saved master credentials for provider: {provider}")
            return True
        except Exception as e:
            logger.error(f"[MasterCredentialService] Failed to save credentials for {provider}: {e}")
            return False

    async def get_master_credential(self, provider: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt credentials dict for a provider, falling back to environment variables."""
        prov_key = provider.lower().strip()
        lookup_candidates = [prov_key]
        if prov_key == "gemini":
            lookup_candidates.append("google")
        elif prov_key == "google":
            lookup_candidates.append("gemini")
        elif prov_key == "google_realtime":
            lookup_candidates.extend(["gemini", "google"])
        elif prov_key == "openai_realtime":
            lookup_candidates.append("openai")
        elif prov_key == "azure_realtime":
            lookup_candidates.append("azure")
        elif prov_key in ("navana", "bodhi"):
            lookup_candidates.extend(["navana", "bodhi"])

            try:
                record = await kodewaves_db_client.get_master_credential(candidate)
                if record:
                    if not record.is_enabled:
                        logger.info(f"[MasterCredentialService] Provider '{candidate}' is explicitly disabled in DB.")
                        return None
                    if record.credentials_encrypted:
                        try:
                            decrypted_str = self.decrypt(record.credentials_encrypted)
                            data = json.loads(decrypted_str)
                            if data and (data.get("api_key") or data.get("account_sid") or data.get("auth_token")):
                                return data
                        except Exception as e:
                            logger.error(f"[MasterCredentialService] Failed to decrypt credentials for {candidate}: {e}")
            except Exception as db_err:
                logger.debug(f"[MasterCredentialService] DB lookup for {candidate} failed or unavailable: {db_err}")

        # Fallback to environment variables if not configured in DB
        env_map = {
            "openai": "OPENAI_API_KEY",
            "openai_realtime": "OPENAI_API_KEY",
            "deepgram": "DEEPGRAM_API_KEY",
            "cartesia": "CARTESIA_API_KEY",
            "elevenlabs": "ELEVENLABS_API_KEY",
            "sarvam": "SARVAM_API_KEY",
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GEMINI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "google_realtime": "GEMINI_API_KEY",
            "navana": "BODHI_API_KEY",
            "bodhi": "BODHI_API_KEY",
        }
        for candidate in lookup_candidates:
            env_var = env_map.get(candidate, f"{candidate.upper()}_API_KEY")
            val = os.environ.get(env_var) or os.environ.get(f"{candidate.upper()}_API_KEY")
            if val:
                return {"api_key": val}
        return None

    async def test_connection(self, provider: str) -> Tuple[bool, str]:
        """Test active API connectivity to an upstream provider using master credentials."""
        creds = await self.get_master_credential(provider)
        if not creds:
            return False, f"Provider '{provider}' has no master credentials configured or is disabled."

        provider_lower = provider.lower().strip()
        timeout = aiohttp.ClientTimeout(total=8)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1. OpenAI
                if provider_lower == "openai":
                    api_key = creds.get("api_key")
                    base_url = creds.get("base_url") or "https://api.openai.com/v1"
                    async with session.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}) as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to OpenAI API."
                        return False, f"OpenAI returned HTTP status {resp.status}"

                # 2. Anthropic
                elif provider_lower == "anthropic":
                    api_key = creds.get("api_key")
                    async with session.get(
                        "https://api.anthropic.com/v1/models",
                        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                    ) as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to Anthropic API."
                        return False, f"Anthropic returned HTTP status {resp.status}"

                # 3. Google Gemini
                elif provider_lower in ("google", "gemini", "google_realtime"):
                    api_key = creds.get("api_key")
                    async with session.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}") as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to Google Gemini API."
                        return False, f"Google Gemini returned HTTP status {resp.status}"

                # 4. Navana.ai (Indic Speech AI)
                elif provider_lower in ("navana", "bodhi"):
                    api_key = creds.get("api_key")
                    async with session.post(
                        "https://stt.navana.ai/api/transcribe",
                        headers={"X-Api-Key": api_key},
                    ) as resp:
                        if resp.status != 401:
                            return True, "Successfully connected to Navana.ai API."
                        return False, "Navana.ai returned 401 Unauthorized (Invalid API key)"

                # 5. Sarvam AI (Indian Models)
                elif provider_lower == "sarvam":
                    api_key = creds.get("api_key")
                    async with session.get(
                        "https://api.sarvam.ai/v1/models",
                        headers={"api-subscription-key": api_key},
                    ) as resp:
                        # Sarvam might return 200 or 404 for list models, but 401/403 means bad key
                        if resp.status in (200, 404):
                            return True, "Successfully validated Sarvam AI API subscription key."
                        return False, f"Sarvam AI returned HTTP status {resp.status}"

                # 5. ElevenLabs
                elif provider_lower == "elevenlabs":
                    api_key = creds.get("api_key")
                    async with session.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": api_key}) as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to ElevenLabs API."
                        return False, f"ElevenLabs returned HTTP status {resp.status}"

                # 6. Deepgram
                elif provider_lower == "deepgram":
                    api_key = creds.get("api_key")
                    async with session.get("https://api.deepgram.com/v1/projects", headers={"Authorization": f"Token {api_key}"}) as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to Deepgram API."
                        return False, f"Deepgram returned HTTP status {resp.status}"

                # 7. Cartesia
                elif provider_lower == "cartesia":
                    api_key = creds.get("api_key")
                    async with session.get(
                        "https://api.cartesia.ai/voices",
                        headers={"X-API-Key": api_key, "Cartesia-Version": "2024-06-10"},
                    ) as resp:
                        if resp.status == 200:
                            return True, "Successfully connected to Cartesia API."
                        return False, f"Cartesia returned HTTP status {resp.status}"

                # 8. Twilio
                elif provider_lower == "twilio":
                    account_sid = creds.get("account_sid")
                    auth_token = creds.get("auth_token")
                    auth_header = "Basic " + base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
                    async with session.get(f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json", headers={"Authorization": auth_header}) as resp:
                        if resp.status == 200:
                            return True, "Successfully validated Twilio master carrier account."
                        return False, f"Twilio returned HTTP status {resp.status}"

                # 9. Exotel (Indian Carrier)
                elif provider_lower == "exotel":
                    api_key = creds.get("api_key")
                    api_token = creds.get("api_token")
                    subdomain = creds.get("subdomain") or creds.get("account_sid")
                    auth_header = "Basic " + base64.b64encode(f"{api_key}:{api_token}".encode()).decode()
                    async with session.get(f"https://api.exotel.com/v1/Accounts/{subdomain}", headers={"Authorization": auth_header}) as resp:
                        if resp.status in (200, 302):
                            return True, "Successfully validated Exotel Indian carrier credentials."
                        return False, f"Exotel returned HTTP status {resp.status}"

                # 10. Plivo
                elif provider_lower == "plivo":
                    auth_id = creds.get("auth_id")
                    auth_token = creds.get("auth_token")
                    auth_header = "Basic " + base64.b64encode(f"{auth_id}:{auth_token}".encode()).decode()
                    async with session.get(f"https://api.plivo.com/v1/Account/{auth_id}/", headers={"Authorization": auth_header}) as resp:
                        if resp.status == 200:
                            return True, "Successfully validated Plivo master account."
                        return False, f"Plivo returned HTTP status {resp.status}"

                # 11. Custom OpenAI Compatible (Groq, DeepSeek, Ollama, vLLM)
                elif provider_lower == "custom_openai_compatible" or "custom" in provider_lower:
                    api_key = creds.get("api_key") or ""
                    base_url = creds.get("base_url") or "http://localhost:11434/v1"
                    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                    async with session.get(f"{base_url}/models", headers=headers) as resp:
                        if resp.status == 200:
                            return True, f"Successfully connected to custom endpoint at {base_url}."
                        return False, f"Custom endpoint returned HTTP status {resp.status}"

                return False, f"No connection test routine defined for provider '{provider}'"

        except Exception as exc:
            logger.error(f"[MasterCredentialService] Connection test exception for {provider}: {exc}")
            return False, f"Connection failed: {str(exc)}"


master_credential_service = MasterCredentialService()
