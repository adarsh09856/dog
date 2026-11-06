#!/usr/bin/env python3
"""Download the configured local LLM once, then keep it resident off the call path."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path


def model_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise ValueError("CLIENT_OLLAMA_MODEL must be an Ollama model identifier")
    return value


def post_json(path: str, payload: dict, timeout: int) -> dict:
    # Fixed internal endpoint, never a caller-controlled URL or shell command.
    req = urllib.request.Request(
        "http://ollama:11434" + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read(1024 * 1024))
    if not isinstance(result, dict):
        raise RuntimeError("Local model server returned an invalid response")
    if result.get("error"):
        raise RuntimeError("Local model server rejected model preparation")
    return result


def get_json(path: str, timeout: int) -> dict:
    req = urllib.request.Request("http://ollama:11434" + path)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read(1024 * 1024))
    if not isinstance(result, dict):
        raise RuntimeError("Local model server returned an invalid response")
    return result


def model_digest(response: dict, model: str, expected_digest: str) -> str:
    """Return the immutable digest for the exact installed Ollama tag."""
    models = response.get("models")
    if not isinstance(models, list):
        raise RuntimeError("Local model server did not report installed model assets")
    matches = [entry for entry in models if isinstance(entry, dict) and entry.get("name") == model]
    if len(matches) != 1:
        raise RuntimeError("The configured Ollama model tag is not installed exactly once")
    digest = matches[0].get("digest")
    if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
        digest = "sha256:" + digest
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("The configured Ollama model has no valid immutable digest")
    if digest != expected_digest:
        raise RuntimeError("Installed Ollama model digest does not match the signed release")
    return digest


def main() -> None:
    model = model_name(os.getenv("CLIENT_OLLAMA_MODEL", "qwen3.5:2b-q4_K_M"))
    expected_digest = os.getenv("CLIENT_OLLAMA_MODEL_DIGEST", "").strip()
    ready = Path("/tmp/models-ready")
    prepared = False
    while True:
        try:
            if not prepared:
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
                    raise ValueError("CLIENT_OLLAMA_MODEL_DIGEST must be a signed sha256 digest")
                post_json("/api/pull", {"model": model, "stream": False}, 1800)
                prepared = True
            model_digest(get_json("/api/tags", 30), model, expected_digest)
            post_json("/api/generate", {
                "model": model, "prompt": "", "stream": False, "keep_alive": -1,
                "options": {"num_predict": 1},
            }, 300)
            model_digest(get_json("/api/tags", 30), model, expected_digest)
            ready.touch()
            time.sleep(30)
        except (OSError, ValueError, RuntimeError):
            ready.unlink(missing_ok=True)
            print("Local model preparation pending; retrying", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
