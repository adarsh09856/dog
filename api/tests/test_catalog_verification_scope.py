from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
import importlib
module = importlib.import_module("api.services.catalog.catalog_service")
from api.services.catalog.normalize import google_model_layer


class Response:
    status = 200
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False


class Session:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def post(self, *args, **kwargs): return Response()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gemini-2.5-flash-preview-tts", "gemini-3.8-flash-lite-tts"])
async def test_gemini_tts_verification_uses_selected_models_schema(monkeypatch, model):
    requests = []

    class AudioResponse(Response):
        async def json(self):
            return {"candidates": [{"content": {"parts": [{"inlineData": {"data": "UklGRg=="}}]}}]}

    class AudioSession(Session):
        def post(self, url, **kwargs):
            requests.append((url, kwargs["json"]))
            return AudioResponse()

    service = module.CatalogService()
    monkeypatch.setattr(service, "_get_test_model_for_layer", AsyncMock(return_value=model))
    monkeypatch.setattr(service, "notify_changed", AsyncMock())
    monkeypatch.setattr(module.aiohttp, "ClientSession", lambda **kwargs: AudioSession())
    monkeypatch.setattr(module.kodewaves_db_client, "record_verify_run", AsyncMock())
    monkeypatch.setattr(module.kodewaves_db_client, "update_model_verification_status", AsyncMock())

    ok, _, error = await service.verify_layer("gemini", "tts", {"api_key": "synthetic"})

    assert ok and error is None
    url, payload = requests[0]
    assert model in url
    part = payload["contents"][0]["parts"][0]
    voice = payload["generationConfig"]["speechConfig"]["voiceConfig"]
    if model.startswith("gemini-3.8-"):
        assert part["speech_metadata"]["style"]
        assert voice == {"voice": "Kore"}
    else:
        assert "speech_metadata" not in part
        assert voice == {"prebuiltVoiceConfig": {"voiceName": "Kore"}}


@pytest.mark.asyncio
async def test_gemini_admin_verify_covers_reasoning_realtime_and_voice(monkeypatch):
    service = module.CatalogService()
    monkeypatch.setattr(module.kodewaves_db_client, "list_models", AsyncMock(return_value=[]))
    verify = AsyncMock(return_value=(True, 12, None))
    monkeypatch.setattr(service, "verify_layer", verify)

    result = await service.verify_provider_all_layers("gemini", {"api_key": "synthetic"})

    assert {"llm", "tts", "s2s"} <= set(result)
    assert {call.args[1] for call in verify.await_args_list} >= {"llm", "tts", "s2s"}


@pytest.mark.asyncio
async def test_one_llm_probe_does_not_certify_every_provider_model(monkeypatch):
    service = module.CatalogService()
    monkeypatch.setattr(service, "_get_test_model_for_layer", AsyncMock(return_value="gemini-3.8-flash"))
    monkeypatch.setattr(service, "notify_changed", AsyncMock())
    monkeypatch.setattr(module.aiohttp, "ClientSession", lambda **kwargs: Session())
    monkeypatch.setattr(module.kodewaves_db_client, "record_verify_run", AsyncMock())
    update = AsyncMock()
    monkeypatch.setattr(module.kodewaves_db_client, "update_model_verification_status", update)
    ok, _, _ = await service.verify_layer("google", "llm", {"api_key": "synthetic"})
    assert ok
    assert update.await_args.kwargs["model_identifier"] == "gemini-3.8-flash"
    assert update.await_args.kwargs["status"] == "PASS"


@pytest.mark.asyncio
async def test_credential_check_does_not_certify_tts_generation(monkeypatch):
    service = module.CatalogService()
    monkeypatch.setattr(service, "notify_changed", AsyncMock())
    monkeypatch.setattr(module.aiohttp, "ClientSession", lambda **kwargs: Session())
    monkeypatch.setattr(module.master_credential_service, "test_connection", AsyncMock(return_value=(True, "Accepted")))
    record = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(module.kodewaves_db_client, "record_verify_run", record)
    monkeypatch.setattr(module.kodewaves_db_client, "update_model_verification_status", update)
    ok, _, _ = await service.verify_layer("openai", "tts", {"api_key": "synthetic"})
    assert ok
    assert record.await_args.kwargs["status"] == "UNTESTED"
    update.assert_not_awaited()


@pytest.mark.parametrize("name,methods,expected", [
    ("gemini-3.8-flash", ["generateContent"], "llm"),
    ("gemini-3.8-flash-tts", ["generateContent"], "tts"),
    ("gemini-embedding-2", ["embedContent"], "embeddings"),
    ("gemini-3.1-flash-live-preview", ["bidiGenerateContent"], "s2s"),
    ("gemini-3.5-transcribe", ["generateContent"], "stt"),
    ("gemini-3.1-flash-image", ["generateContent"], None),
    ("gemini-2.5-computer-use-preview", ["generateContent"], None),
    ("gemini-robotics-er-2-preview", ["generateContent"], None),
    ("gemini-no-generation", ["countTokens"], None),
    ("gemini-nano-banana-2.1", ["generateContent"], None),
    ("gemini-robotics-streaming", ["bidiGenerateContent"], None),
    ("gemini-transcribe-live", ["bidiGenerateContent"], None),
    ("gemini-live-translate", ["bidiGenerateContent"], None),
])
def test_discovery_respects_actual_api_methods_and_runtime_layer(name, methods, expected):
    assert google_model_layer({"name": "models/" + name, "supportedGenerationMethods": methods}) == expected


@pytest.mark.asyncio
async def test_discovery_preserves_admin_disabled_model_and_prices(monkeypatch):
    from api.db.kodewaves_client import kodewaves_db_client
    model = NS(provider="google", layer="llm", status="PASS", enabled=False, is_active=False,
               wholesale_cost=9.5, markup_percent=40, recommended=True, languages=["hi-IN"])
    class DBSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def execute(self, stmt): return NS(scalar_one_or_none=lambda: model)
        async def commit(self): pass
    monkeypatch.setattr(kodewaves_db_client, "get_session", lambda: DBSession())
    await kodewaves_db_client.upsert_discovered_model("gemini-example", "Vendor name", "google", "llm")
    assert model.enabled is False and model.is_active is False
    assert model.wholesale_cost == 9.5 and model.markup_percent == 40
    assert model.recommended is True and model.status == "PASS"
    assert model.languages == ["hi-IN"]


def test_gemini_38_indic_metadata_tracks_model_difference():
    models = {m["model_identifier"]: m for m in module.CURATED_PROVIDER_MODELS["gemini"]}
    full = models["gemini-3.8-flash-tts"]["languages"]
    lite = models["gemini-3.8-flash-lite-tts"]["languages"]
    assert {"hi-IN", "ta-IN", "te-IN", "mr-IN", "gu-IN", "bn-IN"} <= set(full) & set(lite)
    assert "sd-IN" in full and "sd-IN" not in lite
