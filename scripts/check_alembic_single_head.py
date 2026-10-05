"""
Check that Alembic migrations have exactly one head revision.
"""
import os
import sys
from alembic.config import Config
from alembic.script import ScriptDirectory

def check_single_head():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ini_path = os.path.join(repo_root, "api", "alembic.ini")
    
    if not os.path.exists(ini_path):
        print(f"[ERROR] alembic.ini not found at {ini_path}")
        return 1
        
    alembic_cfg = Config(ini_path)
    # Ensure script_location is absolute
    alembic_cfg.set_main_option("script_location", os.path.join(repo_root, "api", "alembic"))
    
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    
    print(f"[INFO] Current Alembic heads ({len(heads)}): {heads}")
    if len(heads) == 1:
        print(f"[SUCCESS] Exactly one head revision found: {heads[0]}")
        return 0
    else:
        print(f"[FAILURE] Expected 1 head revision, found {len(heads)}: {heads}")
        return 1

if __name__ == "__main__":
    sys.exit(check_single_head())
