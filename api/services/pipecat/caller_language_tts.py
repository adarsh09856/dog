"""Provider-aware TTS language routing for per-call caller language hints."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

from api.services.configuration.language_normalizer import normalize_language_code
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
