from pathlib import Path

import pytest

from api.services.release_schema import migration_compatibility


def _write_revision(directory: Path, filename: str, revision: str, parent: str | None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        f"revision = {revision!r}\ndown_revision = {parent!r}\n",
        encoding="utf-8",
    )


def test_release_schema_signs_upgrade_ancestors_but_no_untested_rollback(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "middle", "root")
    _write_revision(migrations, "003.py", "head", "middle")

    assert migration_compatibility(migrations) == {
        "head": "head",
        "upgrade_from": ["head", "middle", "root"],
        "rollback_to": [],
    }


def test_release_schema_rejects_multiple_heads(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "left", "root")
    _write_revision(migrations, "003.py", "right", "root")

    with pytest.raises(ValueError, match="one Alembic head"):
        migration_compatibility(migrations)


def test_release_schema_rejects_missing_parent(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "head", "missing")

    with pytest.raises(ValueError, match="missing revisions"):
        migration_compatibility(migrations)
