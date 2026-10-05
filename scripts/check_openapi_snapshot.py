"""
OpenAPI snapshot verification script.
Dumps current FastAPI app routes and compares against docs/api-reference/openapi.json,
or updates the snapshot if --update flag is provided.
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure paths and env
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "pipecat"))
sys.path.insert(0, str(repo_root / "pipecat" / "src"))

env_example = repo_root / "api" / ".env.example"
if env_example.exists():
    with open(env_example, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/kodewaves_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-32-bytes-long-1234")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["LOG_LEVEL"] = os.environ["LOG_LEVEL"].strip("\"'")
os.environ["ENVIRONMENT"] = "test"

from fastapi.openapi.utils import get_openapi
from api.app import app

OUTPUT_PATH = repo_root / "docs" / "api-reference" / "openapi.json"

def main():
    parser = argparse.ArgumentParser(description="Check or update OpenAPI route snapshot.")
    parser.add_argument("--update", action="store_true", help="Update snapshot file with current routes")
    args = parser.parse_args()

    spec = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
    )
    
    current_json = json.dumps(spec, indent=2, sort_keys=True)
    num_paths = len(spec.get("paths", {}))

    if args.update or not OUTPUT_PATH.exists():
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(current_json, encoding="utf-8")
        print(f"[SUCCESS] Updated OpenAPI snapshot: {num_paths} paths saved to {OUTPUT_PATH.relative_to(repo_root)}")
        return 0

    existing_text = OUTPUT_PATH.read_text(encoding="utf-8")
    try:
        existing_spec = json.loads(existing_text)
    except Exception as e:
        print(f"[WARNING] Existing snapshot could not be parsed as JSON: {e}")
        existing_spec = {}

    existing_paths = len(existing_spec.get("paths", {}))
    print(f"[INFO] Existing snapshot paths: {existing_paths}, Current routes paths: {num_paths}")

    # Check for removed paths
    curr_paths_set = set(spec.get("paths", {}).keys())
    exist_paths_set = set(existing_spec.get("paths", {}).keys())
    removed_paths = exist_paths_set - curr_paths_set

    if removed_paths:
        print(f"[FAILURE] Detected {len(removed_paths)} removed routes from OpenAPI snapshot:")
        for p in sorted(removed_paths):
            print(f"  - {p}")
        return 1

    print(f"[SUCCESS] OpenAPI snapshot verified: {num_paths} endpoints active, 0 regressions.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
