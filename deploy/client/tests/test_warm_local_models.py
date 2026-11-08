import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "warm_local_models.py"
SPEC = importlib.util.spec_from_file_location("warm_local_models", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
warm_local_models = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(warm_local_models)


def test_model_digest_matches_exact_ollama_tag():
    digest = "a" * 64
    response = {"models": [
        {"name": "other:latest", "digest": "b" * 64},
        {"name": "qwen3.5:2b-q4_K_M", "digest": digest},
    ]}

    assert warm_local_models.model_digest(
        response, "qwen3.5:2b-q4_K_M", f"sha256:{digest}"
    ) == f"sha256:{digest}"


@pytest.mark.parametrize("response", [
    {"models": [{"name": "qwen3.5:2b-q4_K_M", "digest": "not-a-digest"}]},
    {"models": [{"name": "qwen3.5:2b-q4_K_M", "digest": "b" * 64}]},
    {"models": [{"name": "qwen3.5:2b-q4_K_M:latest", "digest": "a" * 64}]},
])
def test_model_digest_rejects_mutable_or_unexpected_model(response):
    with pytest.raises(RuntimeError):
        warm_local_models.model_digest(
            response, "qwen3.5:2b-q4_K_M", "sha256:" + "a" * 64
        )
