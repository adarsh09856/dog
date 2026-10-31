from api.routes.organization import _catalog_models_for_layer


def test_catalog_model_health_includes_cloud_and_self_hosted_models():
    catalog = {
        "cloud_llm_models": [{"id": "cloud-llm"}],
        "local_llm_models": [{"id": "local-llm"}],
        "cloud_stt_models": [{"id": "cloud-stt"}],
        "local_stt_models": [{"id": "local-stt"}],
        "cloud_tts_models": [{"id": "cloud-tts"}],
        "local_tts_models": [{"id": "local-tts"}],
        "cloud_s2s_models": [{"id": "cloud-realtime"}],
        "local_s2s_models": [{"id": "local-realtime"}],
    }

    assert [model["id"] for model in _catalog_models_for_layer(catalog, "llm")] == [
        "cloud-llm",
        "local-llm",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "stt")] == [
        "cloud-stt",
        "local-stt",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "tts")] == [
        "cloud-tts",
        "local-tts",
    ]
    assert [model["id"] for model in _catalog_models_for_layer(catalog, "realtime")] == [
        "cloud-realtime",
        "local-realtime",
    ]


def test_catalog_model_health_keeps_legacy_layer_keys():
    catalog = {"llm": [{"id": "legacy-llm"}], "stt": [], "tts": []}

    assert [model["id"] for model in _catalog_models_for_layer(catalog, "llm")] == [
        "legacy-llm"
    ]
    assert _catalog_models_for_layer(catalog, "stt") == []
