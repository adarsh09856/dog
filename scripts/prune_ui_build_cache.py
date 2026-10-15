"""Bound explicitly marked Kodewaves UI build cache without pruning other projects."""

import argparse
import json
import re
import subprocess


MARKER = "KODEWAVES_UI_BUILD=1 npm run build"


def cache_bytes(value: str) -> int:
    match = re.fullmatch(r"([0-9.]+)\s*(B|kB|MB|GB|TB)", value)
    if not match:
        raise ValueError(f"Unknown Docker cache size: {value!r}")
    return int(float(match[1]) * {"B": 1, "kB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}[match[2]])


def select_records(records: list[dict], budget_bytes: int) -> list[str]:
    """Retain newest marked build snapshots up to the application-only budget."""
    candidates = [r for r in records if MARKER in r.get("Description", "")
                  and r.get("Reclaimable") is True and r.get("Shared") is False]
    # Validate every size before returning a destructive selection.
    sizes = {r["ID"]: cache_bytes(r["Size"]) for r in candidates}
    total = sum(sizes.values())
    selected = []
    for record in sorted(candidates, key=lambda r: r["CreatedAt"]):
        if total <= budget_bytes:
            break
        identifier = record["ID"]
        if not re.fullmatch(r"[a-zA-Z0-9]+", identifier):
            raise ValueError("Unexpected Docker cache identifier")
        selected.append(identifier)
        total -= sizes[identifier]
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-gb", type=float, default=8)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not 0 < args.max_gb < float("inf"):
        parser.error("--max-gb must be positive and finite")
    result = subprocess.run(["docker", "buildx", "du", "--format=json"],
                            check=True, capture_output=True, text=True, timeout=30)
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    selected = select_records(records, int(args.max_gb * 1000**3))
    print(f"Kodewaves UI cache: {len(selected)} excess private snapshots selected.")
    if args.apply and selected:
        expression = "id~=^(" + "|".join(selected) + ")$"
        subprocess.run(["docker", "buildx", "prune", "--force", "--filter", expression],
                       check=True, timeout=180)


if __name__ == "__main__":
    main()
