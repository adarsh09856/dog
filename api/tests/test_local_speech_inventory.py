from api.services.catalog.local_inventory import piper_voice_inventory, whisper_api_base
from api.services.catalog.local_inventory import (
    local_tts_inventory,
    local_model_voice_ids,
    local_model_voice_ids_for_language,
)
from api.services.catalog.local_inventory import local_model_voice_catalog
from api.services.catalog import local_inventory


def test_voice_catalog_keeps_all_real_languages_without_inventing_accents():
    rows = local_model_voice_catalog({"voices": [
        {"id": "speaker-1", "name": "Native Tamil", "language": "ta-IN", "gender": "female"},
        {"id": "speaker-2", "language": "hi", "gender": "male"},
        {"id": "hidden", "installed": False},
    ]})
    assert [row["voice_id"] for row in rows] == ["speaker-1", "speaker-2"]
    assert rows[0]["languages"] == ["ta-IN"]
    assert rows[1]["language"] == "hi"
    assert all(row["accent"] is None for row in rows)


def test_local_tts_capabilities_follow_installed_model_manifest():
    payload = {"data": [
        {"id": "new-indic-model", "task": "text-to-speech", "voices": [
            {"id": "tamil-speaker", "language": "ta"},
            {"id": "hindi-speaker", "language": "hi"},
            {"id": "not-installed", "installed": False},
        ]},
        {"id": "stt-only", "task": "automatic-speech-recognition"},
        {"id": "missing-model", "task": "text-to-speech", "installed": False},
    ]}
    models = local_tts_inventory(payload)
    assert set(models) == {"new-indic-model"}
    assert local_model_voice_ids(models["new-indic-model"]) == {"tamil-speaker", "hindi-speaker"}
    assert local_model_voice_ids_for_language(models["new-indic-model"], "ta-IN") == {"tamil-speaker"}
    assert local_model_voice_ids_for_language(models["new-indic-model"], "hi-IN") == {"hindi-speaker"}
    assert local_model_voice_ids_for_language(models["new-indic-model"], "bn-IN") == set()
    assert local_tts_inventory({"data": None}) == {}
    assert local_model_voice_ids({"voices": 4}) == set()


def test_voice_language_manifest_accepts_scalar_and_multi_language_values():
    model = {"voices": [
        {"id": "tamil", "language": "ta-IN"},
        {"id": "bengali", "languages": ["bn-IN", "en-IN"]},
        {"id": "disabled", "languages": ["hi-IN"], "installed": False},
    ]}
    assert local_model_voice_ids_for_language(model, "ta") == {"tamil"}
    assert local_model_voice_ids_for_language(model, "bn") == {"bengali"}
    assert local_model_voice_ids_for_language(model, "en-IN") == {"bengali"}
    assert local_model_voice_ids_for_language(model, "hi") == set()
    assert local_model_voice_ids_for_language(model, "multi") == {"tamil", "bengali"}


def test_hinglish_requires_one_voice_to_support_hindi_and_english():
    model = {"voices": [
        {"id": "hindi-only", "languages": ["hi-IN"]},
        {"id": "english-only", "languages": ["en-IN"]},
        {"id": "bilingual", "languages": ["hi-IN", "en-IN"]},
        {"id": "explicit-mixed", "language": "hi-en"},
    ]}
    for language in ("hinglish", "hi-en", "en-hi"):
        assert local_model_voice_ids_for_language(model, language) == {
            "bilingual", "explicit-mixed",
        }


def test_piper_native_mapping_excludes_uninstalled_voices():
    assert piper_voice_inventory({
        "hi_IN-pratham-medium": {"language": {"family": "hi"}},
        "missing": {"installed": False},
    }) == {"hi_IN-pratham-medium": {"language": {"family": "hi"}}}


def test_wrapped_and_list_inventories():
    assert set(piper_voice_inventory({"voices": ["present", {"id": "other"},
                                                            {"id": "missing", "installed": False}]})) == {"present", "other"}


def test_whisper_api_base_preserves_version_and_custom_prefix():
    assert whisper_api_base("http://whisper:8000") == "http://whisper:8000/v1"
    assert whisper_api_base("http://whisper:8000/v1/") == "http://whisper:8000/v1"
    assert whisper_api_base("https://example.com/speech/v1/models") == "https://example.com/speech/v1"


async def test_local_tts_model_inventory_is_cached_for_call_start(monkeypatch):
    calls = []

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {"data": [{"id": "tts", "task": "text-to-speech"}]}

    class Session:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def get(self, url):
            calls.append(url)
            return Response()

    monkeypatch.setattr(local_inventory.aiohttp, "ClientSession", Session)
    local_inventory._tts_model_cache.clear()
    try:
        assert "tts" in await local_inventory.get_local_tts_models("http://local/v1")
        assert "tts" in await local_inventory.get_local_tts_models("http://local/v1/")
        assert calls == ["http://local/v1/models"]
    finally:
        local_inventory._tts_model_cache.clear()


async def test_local_stt_inventory_exposes_only_installed_recognizers(monkeypatch):
    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def raise_for_status(self):
            return None

        async def json(self):
            return {"data": [
                {"id": "indicconformer-ctc-int8", "task": "automatic-speech-recognition", "languages": ["hi-IN"]},
                {"id": "not-installed", "task": "automatic-speech-recognition", "installed": False},
                {"id": "tts", "task": "text-to-speech"},
            ]}

    class Session:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def get(self, _):
            return Response()

    monkeypatch.setattr(local_inventory.aiohttp, "ClientSession", Session)
    local_inventory._stt_model_cache.clear()
    try:
        result = await local_inventory.get_local_stt_models("http://indic-stt:8000/v1")
        assert list(result) == ["indicconformer-ctc-int8"]
        assert result["indicconformer-ctc-int8"]["languages"] == ["hi-IN"]
    finally:
        local_inventory._stt_model_cache.clear()
