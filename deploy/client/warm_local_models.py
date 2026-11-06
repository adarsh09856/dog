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


def request(path: str, payload: dict, timeout: int) -> None:
    # Fixed internal endpoint, never a caller-controlled URL or shell command.
    req = urllib.request.Request(
        "http://ollama:11434" + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read(1024 * 1024))
    if result.get("error"):
        raise RuntimeError("Local model server rejected model preparation")


def main() -> None:
    model = model_name(os.getenv("CLIENT_OLLAMA_MODEL", "qwen3.5:2b-q4_K_M"))
    ready = Path("/tmp/models-ready")
    prepared = False
    while True:
        try:
            if not prepared:
                request("/api/pull", {"model": model, "stream": False}, 1800)
                prepared = True
            request("/api/generate", {
                "model": model, "prompt": "", "stream": False, "keep_alive": -1,
                "options": {"num_predict": 1},
            }, 300)
            ready.touch()
            time.sleep(30)
        except (OSError, ValueError, RuntimeError):
            ready.unlink(missing_ok=True)
            print("Local model preparation pending; retrying", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
