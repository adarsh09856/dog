"""
Smoke test to ensure api.app can be imported cleanly without missing dependencies or syntax errors.
"""
import os
import sys

# Ensure repository root and pipecat are in sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "pipecat"))
sys.path.insert(0, os.path.join(repo_root, "pipecat", "src"))

# Load environment defaults if not already set
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
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["LOG_LEVEL"] = os.environ["LOG_LEVEL"].strip("\"'")
os.environ["ENVIRONMENT"] = "test"

def test_import_app():
    try:
        import api.app
        print("[SUCCESS] api.app successfully imported!")
        return 0
    except Exception as e:
        import traceback
        print("[FAILURE] Failed to import api.app:")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_import_app())
