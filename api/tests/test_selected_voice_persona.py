from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.configuration import speech_persona


@pytest.mark.asyncio
@pytest.mark.parametrize("gender,expected", [("male", "masculine"), ("female", "feminine"), (None, "gender-neutral")])
async def test_persona_uses_selected_voice_metadata(monkeypatch, gender, expected):
    lookup = AsyncMock(return_value=[SimpleNamespace(voice_id="selected", gender=gender), SimpleNamespace(voice_id="other", gender="female")])
    monkeypatch.setattr(speech_persona.kodewaves_db_client, "list_voices", lookup)
    config = SimpleNamespace(tts=SimpleNamespace(provider="speaches", model="piper", voice="selected"))
    instruction = await speech_persona.selected_voice_persona_instruction(config)
    assert expected in instruction
    assert "every selected language" in instruction
    lookup.assert_awaited_once_with(provider="piper", tts_model="piper")


@pytest.mark.asyncio
async def test_conflicting_metadata_does_not_guess_gender(monkeypatch):
    lookup = AsyncMock(return_value=[SimpleNamespace(voice_id="selected", gender=g) for g in ("male", "female")])
    monkeypatch.setattr(speech_persona.kodewaves_db_client, "list_voices", lookup)
    config = SimpleNamespace(tts=SimpleNamespace(provider="local", model="model", voice="selected"))
    assert "gender-neutral" in await speech_persona.selected_voice_persona_instruction(config)


@pytest.mark.asyncio
async def test_indus_inaya_uses_installed_model_female_voice_metadata(monkeypatch):
    lookup = AsyncMock(return_value=[])
    monkeypatch.setattr(speech_persona.kodewaves_db_client, "list_voices", lookup)
    config = SimpleNamespace(tts=SimpleNamespace(
        provider="speaches", model="indus-pocket-tts", voice="Inaya",
    ))

    instruction = await speech_persona.selected_voice_persona_instruction(config)

    assert "feminine first-person grammar" in instruction
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_catalog_failure_does_not_abort_call(monkeypatch):
    monkeypatch.setattr(speech_persona.kodewaves_db_client, "list_voices", AsyncMock(side_effect=RuntimeError("offline")))
    config = SimpleNamespace(tts=SimpleNamespace(provider="local", model="model", voice="selected"))
    assert "gender-neutral" in await speech_persona.selected_voice_persona_instruction(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("model,voice,gender,expected", [
    ("indic-vits-rasa-13", "MAR_M", "male", "masculine"),
    ("indic-vits-rasa-13", "MAR_F", "female", "feminine"),
    ("dhvaani-0.5", "indian-female", "female", "feminine"),
    ("indic-parler-tts", "Divya", "female", "feminine"),
    ("indic-parler-tts", "Rohit", "male", "masculine"),
])
async def test_regional_voice_persona_uses_selected_installed_speaker(monkeypatch, model, voice, gender, expected):
    inventory = AsyncMock(return_value={model: {"voices": [
        {"id": voice, "gender": gender}, {"id": "other", "gender": "unknown"},
    ]}})
    monkeypatch.setattr("api.services.catalog.local_inventory.get_local_tts_models", inventory)
    config = SimpleNamespace(tts=SimpleNamespace(
        provider="speaches", model=model, voice=voice,
        base_url="http://regional-voices:8000/v1",
    ))
    assert expected in await speech_persona.selected_voice_persona_instruction(config)
    inventory.assert_awaited_once_with("http://regional-voices:8000/v1")
