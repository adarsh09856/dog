import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from api.services.catalog.gemini_voices import discover_indian_voices, supports_gemini_voice
from api.services.catalog.voice_selection import model_voice_ids


class Response:
    status = 200
    def __init__(self, body): self.body = body
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self.body


@pytest.mark.asyncio
async def test_discovery_preserves_locale_and_follows_bounded_pages():
    class Session:
        def __init__(self): self.calls = []
        def get(self, url, *, params, headers):
            self.calls.append(dict(params))
            assert 'language_code' not in params
            index = 2 if params.get('page_token') else 1
            return Response({'voices': [
                {'id': f"{lang.lower()}-advisor-{index}", 'display_name': 'Native speaker', 'language_code': lang, 'accent': 'Indian'}
                for lang in ('hi-IN', 'en-IN', 'ta-IN', 'ml-IN', 'bn-IN')
            ] + [
                {'id': 'en-us-other-1', 'language_code': 'en-US'},
            ], 'next_page_token': 'page2'})
    session = Session()
    voices = await discover_indian_voices(session, 'synthetic')
    assert len(session.calls) == 2
    assert len(voices) == 10
    assert all(len(v['languages']) == 1 for v in voices)
    assert {v['languages'][0] for v in voices} == {'hi-IN', 'en-IN', 'ta-IN', 'ml-IN', 'bn-IN'}
    assert all(v['name'] == 'Native speaker (Indian)' for v in voices)


def test_new_voice_ids_are_model_specific_and_do_not_accept_paths():
    assert supports_gemini_voice('gemini-3.8-flash-tts', 'en-in-advisor-10')
    assert supports_gemini_voice('gemini-3.8-flash-lite-tts', 'hi-in-advisor-1')
    assert not supports_gemini_voice('gemini-2.5-flash-preview-tts', 'en-in-advisor-10')
    assert not supports_gemini_voice('gemini-3.8-flash-tts', '../secret')
    assert model_voice_ids('gemini', 'gemini-3.8-flash-tts') is None
    assert supports_gemini_voice('gemini-2.5-flash-preview-tts', 'Kore')


@pytest.mark.asyncio
async def test_native_voice_remains_visible_in_selected_model_voice_selector(monkeypatch):
    from api.routes import user as routes
    monkeypatch.setattr(routes.kodewaves_db_client, 'get_setting', AsyncMock(return_value={}))
    monkeypatch.setattr(routes.kodewaves_db_client, 'get_org_ai_policy', AsyncMock(return_value=None))
    monkeypatch.setattr(routes.master_credential_service, 'get_master_credential', AsyncMock(return_value={'api_key':'synthetic'}))
    monkeypatch.setattr(routes.kodewaves_db_client, 'list_voices', AsyncMock(return_value=[SimpleNamespace(
        voice_id='en-in-advisor-10', name='Indian advisor', gender='female', languages=['en-IN'], provider='gemini', preview_url=None,
    )]))
    response = await routes.get_voices('gemini', model='gemini-3.8-flash-tts', user=SimpleNamespace(selected_organization_id=1))
    assert [voice.voice_id for voice in response.voices] == ['en-in-advisor-10']
    assert response.voices[0].languages == ['en-IN']
    assert response.voices[0].accent == 'in'


@pytest.mark.asyncio
async def test_shared_gemini_speakers_keep_supported_indian_languages_without_native_directory_rows(monkeypatch):
    from api.services.catalog.catalog_service import catalog_service
    from api.db.kodewaves_client import kodewaves_db_client
    monkeypatch.setattr(kodewaves_db_client, 'get_model', AsyncMock(return_value=object()))
    write = AsyncMock()
    monkeypatch.setattr(kodewaves_db_client, 'upsert_discovered_voices', write)
    await catalog_service.seed_curated_models_if_needed('gemini')
    rows = write.await_args.args[0]
    for model in ('gemini-3.8-flash-tts', 'gemini-3.8-flash-lite-tts'):
        assert any(row['tts_model'] == model and 'ta-IN' in row['languages'] and 'ml-IN' in row['languages'] for row in rows)
    assert any(row['tts_model'] == 'gemini-3.8-flash-tts' and 'sd-IN' in row['languages'] for row in rows)
    assert not any(row['tts_model'] == 'gemini-3.8-flash-lite-tts' and 'sd-IN' in row['languages'] for row in rows)
