from types import SimpleNamespace as NS

from api.services.pipecat.caller_language_tts import (
    LOCAL_RASA_REPLY_LANGUAGE_CODES,
    SARVAM_SUPPORTED_LANGUAGE_ENUMS,
    caller_language_tts_capabilities,
    refresh_caller_language_tts_capabilities,
)


def test_local_rasa_capabilities_use_the_configured_multilingual_model_and_voice():
    service = NS(_settings=NS(model="indic-vits-rasa-13", voice="KAN_F"))

    capabilities = caller_language_tts_capabilities(service)
    assert capabilities == frozenset({"kn"})
    assert "mai" not in capabilities
    assert capabilities <= LOCAL_RASA_REPLY_LANGUAGE_CODES

    service._settings.voice = "MAI_M"
    male_capabilities = caller_language_tts_capabilities(service)
    assert male_capabilities == frozenset({"mai"})
    assert "en" not in male_capabilities
    assert "sa" not in male_capabilities

    service._settings.voice = "not-a-loaded-voice"
    assert caller_language_tts_capabilities(service) == frozenset()


def test_indic_mio_capabilities_require_a_fresh_installed_multilingual_voice():
    from api.services.catalog import local_inventory

    endpoint = "http://indic-mio-tts:8000/v1"
    local_inventory._tts_model_cache.clear()
    service = NS(
        _settings=NS(model="indic-mio-tts", voice="default"),
        _caller_language_tts_capability_inventory_endpoint=endpoint,
    )
    languages = [
        "as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "gu-IN", "hi-IN",
        "kn-IN", "ks-IN", "kok-IN", "mai-IN", "ml-IN", "mni-IN", "mr-IN",
        "ne-IN", "or-IN", "pa-IN", "sa-IN", "sat-IN", "sd-IN", "ta-IN",
        "te-IN", "ur-IN",
    ]
    try:
        assert caller_language_tts_capabilities(service) == frozenset()
        local_inventory._tts_model_cache[endpoint] = (
            local_inventory.time.monotonic(),
            {"indic-mio-tts": {
                "id": "indic-mio-tts",
                "installed": True,
                "languages": languages,
                "voices": [{"id": "default", "languages": languages}],
            }},
        )

        expected = frozenset(item.split("-", 1)[0] for item in languages)
        assert caller_language_tts_capabilities(service) == expected
        service._settings.voice = "unavailable-voice"
        assert caller_language_tts_capabilities(service) == frozenset()
    finally:
        local_inventory._tts_model_cache.clear()


def test_local_rasa_auto_voice_router_uses_installed_model_language_union():
    from api.services.catalog.local_inventory import local_tts_capability_contract

    contract = local_tts_capability_contract({
        "id": "indic-vits-rasa-13",
        "languages": ["hi-IN", "en-IN"],
        "automatic_voice_routing": "reply-script-with-language-context",
        "voices": [
            {"id": "HIN_M", "languages": ["hi-IN"], "gender": "male"},
            {"id": "ENG_IN", "languages": ["en-IN"], "gender": "unspecified"},
        ],
    })
    service = NS(
        _settings=NS(model="indic-vits-rasa-13", voice="HIN_M"),
        _caller_language_tts_capability_contract=contract,
    )

    assert caller_language_tts_capabilities(service) == frozenset({"hi", "en"})

    service._settings.voice = "ENG_IN"
    assert caller_language_tts_capabilities(service) == frozenset({"hi", "en"})


def test_fixed_multilingual_tts_respects_empty_selected_voice_language_list():
    from api.services.catalog.local_inventory import local_tts_capability_contract

    contract = local_tts_capability_contract({
        "id": "indic-mio-tts",
        "languages": ["hi-IN", "en-IN"],
        "voices": [
            {"id": "default", "languages": []},
        ],
    })
    service = NS(
        _settings=NS(model="indic-mio-tts", voice="default"),
        _caller_language_tts_capability_contract=contract,
    )

    assert caller_language_tts_capabilities(service) == frozenset()


def test_sarvam_capabilities_require_the_dynamic_model_and_verified_voice():
    service = NS(
        _caller_language_routing_enabled=True,
        _settings=NS(model="bulbul:v3", voice="shubh"),
        _config=NS(speakers=["shubh", "anushka"]),
    )

    assert caller_language_tts_capabilities(service) == frozenset(
        SARVAM_SUPPORTED_LANGUAGE_ENUMS
    )

    service._settings.voice = "unverified-custom-voice"
    assert caller_language_tts_capabilities(service) == frozenset()


def test_fixed_tts_service_exposes_only_its_configured_language():
    service = NS(
        _caller_language_routing_enabled=False,
        _settings=NS(model="fixed-model", voice="voice-1", language="hi-IN"),
    )

    assert caller_language_tts_capabilities(service) == frozenset({"hi"})


def test_tts_without_language_capability_does_not_advertise_switching():
    service = NS(_settings=NS(model="fixed-model", voice="voice-1", language=None))

    assert caller_language_tts_capabilities(service) == frozenset()

    service._settings.language = "auto"
    assert caller_language_tts_capabilities(service) == frozenset()


def test_indus_inventory_keeps_inaya_bilingual_and_hides_unloaded_hindi_male():
    service = NS(
        _settings=NS(model="indic-vits-rasa-13", voice="HIN_F"),
        _caller_language_tts_capability_contract={
            "model": "indic-vits-rasa-13",
            "languages": ["as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "hi-IN", "kn-IN"],
            "voices": {"hin_f", "eng_in", "asm_f", "ben_f"},
        },
    )

    assert caller_language_tts_capabilities(service) == frozenset(
        {"as", "bn", "brx", "doi", "en", "hi", "kn"}
    )

    service._settings.voice = "ENG_IN"
    assert {"en", "hi"} <= caller_language_tts_capabilities(service)

    service._settings.voice = "HIN_M"
    assert caller_language_tts_capabilities(service) == frozenset()


def test_rasa_only_inventory_keeps_hindi_male_but_does_not_invent_bilingual_voice():
    service = NS(
        _settings=NS(model="indic-vits-rasa-13", voice="HIN_M"),
        _caller_language_tts_capability_contract={
            "model": "indic-vits-rasa-13",
            "languages": ["as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "hi-IN", "kn-IN"],
            "voices": {"hin_m", "hin_f", "eng_in", "asm_f", "ben_f"},
        },
    )

    assert "hi" in caller_language_tts_capabilities(service)

    service._settings.voice = "HIN_F"
    assert "en" in caller_language_tts_capabilities(service)


def test_missing_english_inventory_does_not_advertise_english_for_hindi_voice():
    service = NS(
        _settings=NS(model="indic-vits-rasa-13", voice="HIN_F"),
        _caller_language_tts_capability_contract={
            "model": "indic-vits-rasa-13",
            "languages": ["hi-IN", "kn-IN"],
            "voices": {"hin_f", "kan_f"},
        },
    )

    assert caller_language_tts_capabilities(service) == {"hi", "kn"}


def test_local_rasa_special_voice_fallback_is_conservative_without_inventory():
    service = NS(_settings=NS(model="indic-vits-rasa-13", voice="HIN_M"))
    assert caller_language_tts_capabilities(service) == frozenset()

    service._settings.voice = "HIN_F"
    assert caller_language_tts_capabilities(service) == frozenset({"hi"})

    service._settings.voice = "ENG_IN"
    assert caller_language_tts_capabilities(service) == frozenset()


def test_capabilities_refresh_after_existing_async_inventory_lookup(monkeypatch):
    from api.services.catalog import local_inventory

    endpoint = "http://indic-vits-tts:8000/v1"
    local_inventory._tts_model_cache.clear()
    service = NS(
        _settings=NS(model="indic-vits-rasa-13", voice="HIN_F"),
        _caller_language_tts_capability_inventory_endpoint=endpoint,
        _caller_language_tts_capability_contract={
            "model": "indic-vits-rasa-13",
            "languages": {"hi", "en"},
            "voices": {"hin_f", "hin_m", "eng_in"},
        },
    )
    llm = NS()
    monkeypatch.setattr(local_inventory.time, "monotonic", lambda: 101.0)
    try:
        # The attached construction-time snapshot is stale once its cache
        # expires; only the configured voice's safe native fallback remains.
        assert refresh_caller_language_tts_capabilities(llm, service) == {"hi"}

        # Models the existing async voice-persona / catalog lookup populating
        # the local cache before the first generated assistant reply.
        local_inventory._tts_model_cache[endpoint] = (
            100.0,
            {"indic-vits-rasa-13": {
                "id": "indic-vits-rasa-13",
                "languages": ["hi-IN", "en-IN"],
                "voices": [
                    {"id": "HIN_F", "languages": ["hi-IN", "en-IN"]},
                    {"id": "ENG_IN", "languages": ["hi-IN", "en-IN"]},
                ],
            }},
        )
        assert refresh_caller_language_tts_capabilities(llm, service) == {
            "hi", "en",
        }
        assert llm._caller_language_supported_codes == {"hi", "en"}

        service._settings.voice = "HIN_M"
        assert refresh_caller_language_tts_capabilities(llm, service) == frozenset()
    finally:
        local_inventory._tts_model_cache.clear()
