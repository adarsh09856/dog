"""Keep first-person grammar aligned with the selected voice's metadata."""

from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client


def voice_persona_instruction(gender: str | None) -> str:
    gender = str(gender or "").strip().lower()
    if gender == "male":
        grammar = (
            "Use masculine first-person grammar where the language marks it "
            "(Hindi example: मैं आपकी मदद कर सकता हूँ)."
        )
    elif gender == "female":
        grammar = (
            "Use feminine first-person grammar where the language marks it "
            "(Hindi example: मैं आपकी मदद कर सकती हूँ)."
        )
    else:
        grammar = (
            "The selected voice has no verified gender metadata. Use natural "
            "gender-neutral self-references (Hindi example: मैं मदद के लिए यहाँ हूँ). "
            "Do not infer the assistant's gender from its name."
        )
    return (
        "Spoken persona rule: " + grammar + " Apply this to the assistant's own "
        "speech in every selected language, overriding conflicting earlier "
        "self-reference examples. Do not infer or change the caller's gender."
    )


async def selected_voice_persona_instruction(user_config) -> str:
    tts = getattr(user_config, "tts", None)
    voice = getattr(tts, "voice", None)
    provider = getattr(tts, "provider", None)
    provider = getattr(provider, "value", provider)
    model = getattr(tts, "model", None)
    if not voice or not provider:
        return voice_persona_instruction(None)
    if provider == "speaches" and (model == "piper" or str(model).startswith("piper/")):
        provider = "piper"
    try:
        rows = await kodewaves_db_client.list_voices(provider=provider, tts_model=model)
        genders = {
            str(row.gender).strip().lower()
            for row in rows
            if row.voice_id == voice and row.gender
        }
        gender = next(iter(genders)) if len(genders) == 1 else None
    except Exception:
        # Metadata availability must not prevent a call or add inference work.
        logger.warning("Voice persona metadata unavailable; using neutral self-references")
        gender = None
    return voice_persona_instruction(gender)
