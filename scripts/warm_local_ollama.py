"""Keep configured local Ollama models loaded after startup or eviction.

This sidecar uses only the Ollama API and Python's standard library. It never
downloads a model; an administrator must install each model first.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request


BASE_URL = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434").rstrip("/")
MODELS = tuple(
    name.strip()
    for name in os.getenv("OLLAMA_WARM_MODELS", "qwen3.5:2b-q4_K_M").split(",")
    if name.strip()
)
INTERVAL_SECONDS = max(5, int(os.getenv("OLLAMA_WARM_INTERVAL_SECONDS", "30")))
WARMUP_PROMPT = "Reply briefly in Hindi. Caller: नमस्ते, मुझे एक कमरा बुक करना है।"


def _request(path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(request, timeout=120 if body is not None else 5) as response:
        return json.load(response)


def _model_names(path: str, collection: str) -> set[str]:
    return {
        str(item.get("name") or item.get("model"))
        for item in _request(path).get(collection, [])
        if item.get("name") or item.get("model")
    }


def _warm_model(model: str) -> None:
    """Load the model and warm both native and app-compatible inference paths."""
    _request(
        "/api/generate",
        {
            "model": model,
            "prompt": WARMUP_PROMPT,
            "stream": False,
            "keep_alive": -1,
            "think": False,
            "options": {
                "num_ctx": 4096,
                "num_predict": 2,
                "temperature": 0,
            },
        },
    )
    _warm_openai_stream(model)


def _warm_openai_stream(model: str) -> None:
    """Prime Ollama's OpenAI-compatible streaming path used by voice turns.

    The native generate endpoint can report the model as resident while the
    first /v1/chat/completions stream still pays cold adapter/stream setup.
    Consume a tiny warmup stream without logging its generated text.
    """
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Reply briefly in the caller's language. Do not explain.",
            },
            {"role": "user", "content": WARMUP_PROMPT},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "reasoning_effort": "none",
        "max_tokens": 2,
        "keep_alive": "8760h",
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        for _ in response:
            pass


def keep_models_warm() -> None:
    last_status: dict[str, str] = {}
    stream_warmed: set[str] = set()
    while True:
        try:
            installed = _model_names("/api/tags", "models")
            loaded = _model_names("/api/ps", "models")
            for model in MODELS:
                status = "missing" if model not in installed else "loaded"
                if model in installed and model not in loaded:
                    if loaded:
                        # Warming is a startup aid, not permission to evict a
                        # user-selected resident model on a memory-limited host.
                        # In particular, do not repeatedly fight an active call
                        # when OLLAMA_MAX_LOADED_MODELS is one.
                        status = "deferred"
                    else:
                        _warm_model(model)
                        loaded.add(model)
                        stream_warmed.add(model)
                        status = "warmed"
                elif model in installed and model not in stream_warmed:
                    # The model may already be resident from the previous
                    # sidecar. Prime the app's streaming endpoint once anyway.
                    _warm_openai_stream(model)
                    stream_warmed.add(model)
                    status = "stream warmed"
                if last_status.get(model) != status:
                    print(f"Ollama model {model}: {status}", flush=True)
                    last_status[model] = status
        except (OSError, ValueError, KeyError) as exc:
            status = f"unavailable ({type(exc).__name__})"
            if last_status.get("server") != status:
                print(f"Ollama server: {status}", flush=True)
                last_status["server"] = status
        else:
            last_status.pop("server", None)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    keep_models_warm()
