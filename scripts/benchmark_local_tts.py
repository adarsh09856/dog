"""Measure uncached first-audio latency from a local OpenAI-compatible TTS server.

Example:
    python scripts/benchmark_local_tts.py --url http://localhost:8000/v1/audio/speech \
        --model indus-pocket-tts --voice Inaya --text 'नमस्ते, कैसे मदद करूँ?'

Run this on the inference host while other production services are active. It
does not retain caller data or generated audio. Vary the text to avoid a cache
hit and compare p95 under expected call concurrency before choosing a model.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.request


def measure(url: str, model: str, voice: str, phrase: str, timeout: float) -> dict:
    body = json.dumps({
        "model": model,
        "voice": voice,
        "input": phrase,
        "response_format": "pcm",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, body, headers={"Content-Type": "application/json"}, method="POST"
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        first = response.read(1)
        first_audio_ms = round((time.perf_counter() - started) * 1000)
        if not first:
            raise RuntimeError("TTS returned an empty audio stream")
        total_bytes = 1
        while chunk := response.read(8192):
            total_bytes += len(chunk)
    return {
        "first_audio_ms": first_audio_ms,
        "complete_ms": round((time.perf_counter() - started) * 1000),
        "audio_bytes": total_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure uncached first-audio latency from a local TTS endpoint"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--voice", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if not args.url.startswith(("http://localhost:", "http://127.0.0.1:", "http://[::1]:")):
        parser.error("Use a loopback URL; run this on the inference host")

    samples = [
        measure(args.url, args.model, args.voice, args.text, args.timeout)
        for _ in range(args.runs)
    ]
    firsts = sorted(sample["first_audio_ms"] for sample in samples)
    p95 = firsts[math.ceil(0.95 * len(firsts)) - 1]
    print(json.dumps({
        "model": args.model,
        "voice": args.voice,
        "runs": samples,
        "first_audio_p50_ms": statistics.median(firsts),
        "first_audio_p95_ms": p95,
        "first_audio_p95_under_800ms": p95 < 800,
    }, indent=2))


if __name__ == "__main__":
    main()
