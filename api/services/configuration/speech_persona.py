"""Keep first-person grammar aligned with the selected voice's metadata."""

from loguru import logger

from api.db.kodewaves_client import kodewaves_db_client


def voice_persona_instruction(gender: str | None) -> str:
    gender = str(gender or "").strip().lower()
    if gender == "male":
        grammar = "Use masculine first-person grammar where the language marks it."
    elif gender == "female":
        grammar = "Use feminine first-person grammar where the language marks it."
    else:
        grammar = (
            "The selected voice has no verified gender metadata. Use natural "
            "gender-neutral self-references. "
            "Do not infer the assistant's gender from its name."
        )
    return (
        "Spoken persona rule: " + grammar + " Apply this to the assistant's own "
        "speech in every selected language, overriding conflicting earlier "
        "self-reference examples. Keep the caller's language; voice gender does "
        "not select a language. Do not infer or change the caller's gender."
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
    # Indus Pocket TTS exposes its voice metadata from its installed-model
    # inventory rather than the shared voice_catalog table. Keep the LLM's
    # first-person Hindi grammar aligned with the only bundled voice instead
    # of falling back to neutral wording for a known female voice.
    if (
        provider == "speaches"
        and str(model or "").casefold() == "indus-pocket-tts"
        and str(voice).casefold() == "inaya"
    ):
        return voice_persona_instruction("female")
    try:
        if provider == "speaches" and model in {"indic-vits-rasa-13", "dhvaani-0.5", "indic-parler-tts"}:
            from api.services.catalog.local_inventory import get_local_tts_models

            endpoint = str(getattr(tts, "base_url", "") or "").rstrip("/").removesuffix("/audio/speech")
            inventory = await get_local_tts_models(endpoint)
            voices = inventory.get(model, {}).get("voices", [])
            genders = {
                str(item["gender"]).strip().lower()
                for item in voices if isinstance(item, dict)
                and item.get("id") == voice and item.get("gender")
            }
            return voice_persona_instruction(next(iter(genders)) if len(genders) == 1 else None)
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
