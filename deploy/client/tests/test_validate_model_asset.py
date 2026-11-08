import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "validate_install.py"
SPEC = importlib.util.spec_from_file_location("client_validate_install", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validate_install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_install)


def test_cloud_only_package_does_not_require_model_asset():
    assert validate_install.validate_model_asset({}, {}, self_hosted=False) == []


def test_cloud_only_env_template_does_not_select_a_local_model_by_default():
    template = SCRIPT.with_name(".env.example").read_text(encoding="utf-8")
    assert "CLIENT_OLLAMA_MODEL=\n" in template


def test_self_hosted_package_requires_signed_model_asset():
    assert validate_install.validate_model_asset({}, {}, self_hosted=True) == [
        "signed release manifest is missing the self-hosted Ollama model asset"
    ]


def test_self_hosted_package_requires_exact_model_name_and_digest():
    payload = {"model_assets": {"ollama": {
        "name": "qwen3.5:2b-q4_K_M", "digest": "sha256:" + "a" * 64,
    }}}
    assert validate_install.validate_model_asset(payload, {
        "CLIENT_OLLAMA_MODEL": "qwen3.5:2b-q4_K_M",
        "CLIENT_OLLAMA_MODEL_DIGEST": "sha256:" + "b" * 64,
    }, self_hosted=True) == [
        "CLIENT_OLLAMA_MODEL and CLIENT_OLLAMA_MODEL_DIGEST must match the signed release manifest"
    ]
