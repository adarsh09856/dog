"""
Provider Capability & Verification Matrix Test Harness.
Part 13.1 & 13.2 of Master Plan: Verify for every provider and layer, writing a PASS/FAIL/NO_KEY matrix table.
"""

import asyncio
import os
import sys

# Ensure repo root and pipecat paths in sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "pipecat"))
sys.path.insert(0, os.path.join(repo_root, "pipecat", "src"))

# Load test env defaults
env_example = os.path.join(repo_root, "api", ".env.example")
if os.path.exists(env_example):
    with open(env_example, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/kodewaves_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-bytes-long-1234")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ["ENVIRONMENT"] = "test"

from api.services.catalog.catalog_service import catalog_service
from api.services.catalog.normalize import normalize_provider_name
from api.services.credentials.master_credential_service import master_credential_service


PROVIDERS_TO_TEST = [
    ("google", ["llm", "tts", "s2s", "embeddings"]),
    ("openai", ["llm", "stt", "tts", "s2s", "embeddings"]),
    ("anthropic", ["llm"]),
    ("groq", ["llm", "stt"]),
    ("deepgram", ["stt", "tts"]),
    ("cartesia", ["stt", "tts"]),
    ("elevenlabs", ["stt", "tts"]),
    ("sarvam", ["llm", "stt", "tts"]),
    ("azure", ["stt", "tts", "s2s"]),
    ("navana", ["stt", "tts"]),
    ("smallest", ["stt", "tts"]),
    ("lmnt", ["tts"]),
    ("rime", ["tts"]),
    ("grok", ["llm", "s2s"]),
    ("ultravox", ["s2s"]),
    ("piper", ["tts"]),
]


async def run_matrix():
    print("=" * 80)
    print(" KODEWAVES PROVIDER VERIFICATION MATRIX (Part 13.2)")
    print("=" * 80)

    results = []

    for provider, layers in PROVIDERS_TO_TEST:
        prov_norm = normalize_provider_name(provider)
        creds = await master_credential_service.get_master_credential(prov_norm)
        has_key = bool(creds and (creds.get("api_key") or creds.get("auth_token")))

        row = {
            "provider": provider,
            "has_key": has_key,
            "llm": "n/a",
            "stt": "n/a",
            "tts": "n/a",
            "s2s": "n/a",
            "embeddings": "n/a",
        }

        for layer in ["llm", "stt", "tts", "s2s", "embeddings"]:
            if layer not in layers:
                row[layer] = "n/a"
            elif not has_key and provider != "piper":
                row[layer] = "NO_KEY"
            else:
                ok, lat, err = await catalog_service.verify_layer(prov_norm, layer, creds=creds)
                status = f"PASS ({lat}ms)" if ok else f"FAIL ({err[:25]}...)" if err else "FAIL"
                row[layer] = status

        results.append(row)

    # Format Markdown Table
    headers = ["Provider", "Key Saved", "LLM", "STT", "TTS", "S2S", "Embeddings"]
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

    table_lines = [header_line, separator_line]
    for r in results:
        key_str = "YES" if r["has_key"] else ("LOCAL" if r["provider"] == "piper" else "NO")
        line = f"| {r['provider']:<12} | {key_str:<9} | {r['llm']:<12} | {r['stt']:<12} | {r['tts']:<12} | {r['s2s']:<12} | {r['embeddings']:<12} |"
        table_lines.append(line)

    markdown_table = "\n".join(table_lines)
    print(markdown_table)
    print("=" * 80)

    # Save to reports/provider_matrix.md
    os.makedirs(os.path.join(repo_root, "reports"), exist_ok=True)
    report_path = os.path.join(repo_root, "reports", "provider_matrix.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Provider Capability & Verification Matrix\n\n")
        f.write(markdown_table + "\n")
    print(f"[SUCCESS] Provider matrix saved to {report_path}")


if __name__ == "__main__":
    asyncio.run(run_matrix())
