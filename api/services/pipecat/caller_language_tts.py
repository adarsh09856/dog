"""Provider-aware TTS language routing for per-call caller language hints."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from api.services.configuration.language_normalizer import (
    SPEECH_LANGUAGE_NAMES,
    normalize_language_code,
)
from pipecat.transcriptions.language import Language


# Sarvam Bulbul v3's current Pipecat adapter explicitly maps these languages to
# Sarvam locale tags. Do not infer support from the much wider STT inventory.
SARVAM_SUPPORTED_LANGUAGE_ENUMS = {
    "bn": Language.BN_IN,
    "en": Language.EN_IN,
    "gu": Language.GU_IN,
    "hi": Language.HI_IN,
    "kn": Language.KN_IN,
    "ml": Language.ML_IN,
    "mr": Language.MR_IN,
    "or": Language.OR_IN,
    "pa": Language.PA_IN,
    "ta": Language.TA_IN,
    "te": Language.TE_IN,
}

_NO_ACTIVE_CALLER_LANGUAGE_TURN = object()

# This is the reply-language intersection exposed by the currently configured
# Rasa 13 local voice router, not the wider Indic STT detector inventory.
LOCAL_RASA_REPLY_LANGUAGE_CODES = frozenset({
    "as", "bn", "brx", "doi", "en", "hi", "kn", "mai", "ml", "mr",
    "ne", "pa", "sa", "ta", "te",
})
LOCAL_RASA_VOICE_GENDERS = {
    "asm_f": "female", "asm_m": "male",
    "ben_f": "female", "ben_m": "male",
    "brx_f": "female", "brx_m": "male",
    "doi_f": "female", "doi_m": "male",
    "kan_f": "female", "kan_m": "male",
    "mai_m": "male", "mal_f": "female",
    "mar_f": "female", "mar_m": "male",
    "nep_f": "female", "pan_f": "female", "pan_m": "male",
    "san_m": "male", "tam_f": "female", "tel_f": "female",
    "hin_m": "male", "hin_f": "female", "eng_in": "unspecified",
}
LOCAL_RASA_VOICE_NATIVE_LANGUAGES = {
    "asm": "as", "ben": "bn", "brx": "brx", "doi": "doi",
    "kan": "kn", "mai": "mai", "mal": "ml", "mar": "mr",
    "nep": "ne", "pan": "pa", "san": "sa", "tam": "ta",
    "tel": "te", "hin": "hi", "eng": "en",
}
def caller_language_tts_capabilities(service: Any) -> frozenset[str]:
    """Return language codes this configured TTS service can route per turn.

    Provider adapters advertise only combinations for which runtime voice
    switching is implemented and the selected voice is verified. Other
    providers are treated as fixed-language services and expose only their
    configured language.
    """
    if service is None:
        return frozenset()

    settings = getattr(service, "_settings", None)
    model = str(getattr(settings, "model", "") or "").casefold()
    voice = str(getattr(settings, "voice", "") or "").casefold()

    if model == "indic-mio-tts":
        contract = getattr(service, "_caller_language_tts_capability_contract", None)
        inventory_endpoint = getattr(
            service, "_caller_language_tts_capability_inventory_endpoint", None
        )
        if isinstance(inventory_endpoint, str) and inventory_endpoint:
            # Reuse only the short-lived inventory fetched during node setup;
            # never add a model-service network request to the call path.
            from api.services.catalog.local_inventory import (
                get_cached_local_tts_model,
                local_tts_capability_contract,
            )

            inventory = get_cached_local_tts_model(inventory_endpoint, model)
            if inventory is not None:
                contract = local_tts_capability_contract(inventory)
                service._caller_language_tts_capability_contract = contract
                service._caller_language_tts_snapshot_verified = True
            elif not getattr(service, "_caller_language_tts_snapshot_verified", False):
                contract = None
        if (
            voice in {"default", "indic-mio-default"}
            and isinstance(contract, dict)
            and contract.get("model") == model
        ):
            installed_voices = contract.get("voices")
            languages = contract.get("languages")
            if (
                isinstance(installed_voices, (set, frozenset, list, tuple))
                and voice in {str(item).casefold() for item in installed_voices}
                and isinstance(languages, (set, frozenset, list, tuple))
            ):
                return frozenset(
                    str(item).strip().casefold().replace("_", "-").split("-", 1)[0]
                    for item in languages
                    if isinstance(item, str) and str(item).strip()
                )
        return frozenset()

    if model == "indic-vits-rasa-13":
        contract = getattr(service, "_caller_language_tts_capability_contract", None)
        inventory_endpoint = getattr(
            service, "_caller_language_tts_capability_inventory_endpoint", None
        )
        if isinstance(inventory_endpoint, str) and inventory_endpoint:
            # Read only the short-lived /v1/models cache populated by catalog
            # or node-preparation code. Never probe a local model from a turn.
            from api.services.catalog.local_inventory import (
                get_cached_local_tts_model,
                local_tts_capability_contract,
            )

            inventory = get_cached_local_tts_model(
                inventory_endpoint, "indic-vits-rasa-13"
            )
            if inventory is not None:
                contract = local_tts_capability_contract(inventory)
                service._caller_language_tts_capability_contract = contract
                service._caller_language_tts_snapshot_verified = True
            elif not getattr(service, "_caller_language_tts_snapshot_verified", False):
                contract = None
        if isinstance(contract, dict) and contract.get("model") == model:
            installed_voices = contract.get("voices")
            languages = contract.get("languages")
            if not isinstance(installed_voices, (set, frozenset, list, tuple)):
                return frozenset()
            if voice not in {str(item).casefold() for item in installed_voices}:
                return frozenset()
            if not isinstance(languages, (set, frozenset, list, tuple)):
                return frozenset()
            return frozenset(
                str(item).strip().casefold().replace("_", "-").split("-", 1)[0]
                for item in languages
                if isinstance(item, str)
                and str(item).strip().casefold().replace("_", "-").split("-", 1)[0]
                in LOCAL_RASA_REPLY_LANGUAGE_CODES
            )

        # A cold cache can safely promise only the configured regional voice's
        # native language. Hindi/English aliases are readiness-dependent:
        # HIN_M can be absent when Indus replaces Piper, and ENG_IN can be
        # absent when neither Indus nor Melo is loaded. HIN_F is present in
        # both supported runtime modes (Inaya or Piper Hindi female).
        if voice == "hin_f":
            return frozenset({"hi"})
        if voice in {"hin_m", "eng_in"}:
            return frozenset()
        native_language = LOCAL_RASA_VOICE_NATIVE_LANGUAGES.get(
            voice.rsplit("_", 1)[0]
        )
        if native_language and voice in LOCAL_RASA_VOICE_GENDERS:
            return frozenset({native_language})

    if (
        getattr(service, "_caller_language_routing_enabled", False)
        and model == "bulbul:v3"
    ):
        speakers = {
            str(speaker).casefold()
            for speaker in getattr(getattr(service, "_config", None), "speakers", ())
        }
        if voice and voice in speakers:
            return frozenset(SARVAM_SUPPORTED_LANGUAGE_ENUMS)

    configured = getattr(settings, "language", None)
    raw_configured = getattr(configured, "value", configured)
    if raw_configured is not None and str(raw_configured).strip():
        if str(raw_configured).strip().casefold() in {
            "auto", "multi", "multilingual", "unknown", "default", "none",
        }:
            return frozenset()
        code = normalize_language_code(str(raw_configured))
        if code in SPEECH_LANGUAGE_NAMES:
            return frozenset({code})
    return frozenset()


def refresh_caller_language_tts_capabilities(llm: Any, tts: Any) -> frozenset[str]:
    """Refresh LLM and shared recognizer routing after voice discovery."""
    capabilities = caller_language_tts_capabilities(tts)
    if llm is not None:
        llm._caller_language_supported_codes = capabilities
        # A workflow can activate a different agent after the shared STT
        # service was constructed. Keep its filter aligned with the active
        # agent's verified TTS inventory instead of the prior agent's cache.
        source = getattr(llm, "_caller_language_source", None)
        if source is not None:
            source._caller_language_supported_codes = capabilities
    return capabilities


def caller_reply_language(
    source: Any,
    configured_language: str | Language | None = None,
    supported_codes: set[str] | frozenset[str] | None = None,
) -> str | None:
    """Return a supported language hint, respecting confidence-filtered metadata.

    A present ``latest_tts_language=None`` means the STT router intentionally
    rejected its latest language guess. In that case do not fall back to the
    raw ``latest_detected_language`` value; retain only the configured TTS
    language. Older recognizers without ``latest_tts_language`` still use
    their legacy detected-language field.
    """
    supported = (
        frozenset(SARVAM_SUPPORTED_LANGUAGE_ENUMS)
        if supported_codes is None
        else supported_codes
    )
    candidates: list[Any] = []

    if source is not None:
        override = getattr(source, "reply_language_override", None)
        if override is not None:
            candidates.append(override)

        if hasattr(source, "latest_tts_language"):
            candidates.append(getattr(source, "latest_tts_language", None))
        else:
            candidates.append(getattr(source, "latest_detected_language", None))

    candidates.append(configured_language)

    for value in candidates:
        if value is None:
            continue
        raw_value = getattr(value, "value", value)
        raw_code = str(raw_value).strip().casefold().replace("_", "-")
        if raw_code in {
            "", "auto", "multi", "multilingual", "unknown", "default", "none",
        }:
            continue
        code = normalize_language_code(raw_code)
        if code in supported:
            return code
    return None


class CallerLanguageSarvamTTSMixin:
    """Update Sarvam's per-connection locale before sending each TTS phrase.

    Sarvam's websocket accepts a configuration message with a target language;
    the Pipecat adapter resends that configuration through ``_update_settings``.
    The configured speaker ID is never changed. Language changes are enabled
    only for Bulbul v3 voices listed by the pinned Pipecat capability table.
    """

    def __init__(
        self,
        *args,
        caller_language_configured: str | Language | None = None,
        caller_language_routing_enabled: bool = True,
        **kwargs,
    ):
        self._caller_language_configured = caller_language_configured
        self._caller_language_routing_enabled = caller_language_routing_enabled
        self._caller_language_logged_state: tuple[str | None, str] | None = None
        self._caller_language_turn_snapshot = _NO_ACTIVE_CALLER_LANGUAGE_TURN
        super().__init__(*args, **kwargs)

    async def _apply_caller_language(self) -> None:
        settings = getattr(self, "_settings", None)
        current = getattr(settings, "language", None)
        model = str(getattr(settings, "model", "") or "").casefold()
        voice = str(getattr(settings, "voice", "") or "").casefold()
        model_config = getattr(self, "_config", None)
        verified_speakers = {
            str(speaker).casefold()
            for speaker in getattr(model_config, "speakers", ())
        }
        eligible = (
            self._caller_language_routing_enabled
            and model == "bulbul:v3"
            and voice in verified_speakers
        )
        if not eligible:
            state = (None, "provider_capability_not_verified")
            if state != self._caller_language_logged_state:
                logger.info(
                    "tts_caller_language_route provider=sarvam enabled=false model={} voice_capability=unverified",
                    model or "unknown",
                )
                self._caller_language_logged_state = state
            return

        if self._caller_language_turn_snapshot is _NO_ACTIVE_CALLER_LANGUAGE_TURN:
            # Direct TTSSpeakFrame use outside an LLM turn remains supported:
            # consult the latest call-scoped source for that standalone phrase.
            language = caller_reply_language(
                getattr(self, "_caller_language_source", None),
                configured_language=self._caller_language_configured,
                supported_codes=SARVAM_SUPPORTED_LANGUAGE_ENUMS.keys(),
            )
        else:
            # All phrases in one response use the same caller-language choice,
            # even if STT state changes while the response is still streaming.
            language = self._caller_language_turn_snapshot
        if language is None:
            state = (None, "no_supported_language")
            if state != self._caller_language_logged_state:
                logger.info(
                    "tts_caller_language_route provider=sarvam enabled=true result=unchanged reason=no_supported_language"
                )
                self._caller_language_logged_state = state
            return

        target = SARVAM_SUPPORTED_LANGUAGE_ENUMS[language]
        current_code = normalize_language_code(str(getattr(current, "value", current) or ""))
        if current_code != language:
            await self._update_settings(self.Settings(language=target))
        state = (language, "applied")
        if state != self._caller_language_logged_state:
            logger.info(
                "tts_caller_language_route provider=sarvam enabled=true language={} voice_preserved=true",
                language,
            )
            self._caller_language_logged_state = state

    async def on_turn_context_created(self, context_id: str):
        source = getattr(self, "_caller_language_source", None)
        self._caller_language_turn_snapshot = caller_reply_language(
            source,
            configured_language=self._caller_language_configured,
            supported_codes=SARVAM_SUPPORTED_LANGUAGE_ENUMS.keys(),
        )
        try:
            await super().on_turn_context_created(context_id)
        except BaseException:
            self._caller_language_turn_snapshot = _NO_ACTIVE_CALLER_LANGUAGE_TURN
            raise

    async def on_turn_context_completed(self):
        try:
            await super().on_turn_context_completed()
        finally:
            self._caller_language_turn_snapshot = _NO_ACTIVE_CALLER_LANGUAGE_TURN

    async def _handle_interruption(self, frame, direction):
        try:
            await super()._handle_interruption(frame, direction)
        finally:
            self._caller_language_turn_snapshot = _NO_ACTIVE_CALLER_LANGUAGE_TURN

    async def cleanup(self):
        self._caller_language_turn_snapshot = _NO_ACTIVE_CALLER_LANGUAGE_TURN
        await super().cleanup()

    async def run_tts(self, text: str, context_id: str):
        await self._apply_caller_language()
        async for frame in super().run_tts(text, context_id):
            yield frame


@lru_cache(maxsize=None)
def caller_language_sarvam_service_class(base_class: type):
    """Build and cache a mixin subclass around Pipecat's Sarvam service."""
    return type(
        f"CallerLanguage{base_class.__name__}",
        (CallerLanguageSarvamTTSMixin, base_class),
        {"__module__": __name__},
    )
