from pathlib import Path

import pytest

from api.services.release_schema import (
    SchemaCompatibilityError,
    migration_compatibility,
    validate_database_upgrade_allowed,
    verify_deployment_migration_history,
)


def _write_revision(directory: Path, filename: str, revision: str, parent: str | None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        f"revision = {revision!r}\ndown_revision = {parent!r}\n",
        encoding="utf-8",
    )


def test_release_schema_only_signs_explicitly_approved_upgrade_origins(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "middle", "root")
    _write_revision(migrations, "003.py", "head", "middle")

    assert migration_compatibility(migrations) == {
        "head": "head",
        "upgrade_from": ["head"],
        "rollback_to": [],
    }
    assert migration_compatibility(migrations, ["root"]) == {
        "head": "head",
        "upgrade_from": ["head", "root"],
        "rollback_to": [],
    }
    with pytest.raises(ValueError, match="not ancestors"):
        migration_compatibility(migrations, ["unrelated"])


def test_release_schema_authorizes_only_explicitly_tested_rollback_origins(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "middle", "root")
    _write_revision(migrations, "003.py", "head", "middle")

    assert migration_compatibility(migrations, ["root", "middle"], ["middle"]) == {
        "head": "head",
        "upgrade_from": ["head", "middle", "root"],
        "rollback_to": ["middle"],
    }
    with pytest.raises(ValueError, match="not ancestors"):
        migration_compatibility(migrations, ["root"], ["unrelated"])
    with pytest.raises(ValueError, match="also be explicitly approved upgrade origins"):
        migration_compatibility(migrations, ["root"], ["middle"])


def test_release_schema_rejects_multiple_heads(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "left", "root")
    _write_revision(migrations, "003.py", "right", "root")

    with pytest.raises(ValueError, match="one Alembic head"):
        migration_compatibility(migrations)


def test_deploy_preflight_rejects_database_revision_missing_from_candidate(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "root", None)
    _write_revision(migrations, "002.py", "head", "root")
    verify_deployment_migration_history(migrations, ())
    verify_deployment_migration_history(migrations, ("root",))
    verify_deployment_migration_history(migrations, ("head",))
    with pytest.raises(SchemaCompatibilityError, match="not ancestors"):
        verify_deployment_migration_history(migrations, ("newer-production-revision",))
    with pytest.raises(SchemaCompatibilityError, match="multiple Alembic revisions"):
        verify_deployment_migration_history(migrations, ("root", "head"))


def test_release_schema_rejects_missing_parent(tmp_path):
    migrations = tmp_path / "versions"
    _write_revision(migrations, "001.py", "head", "missing")

    with pytest.raises(ValueError, match="missing revisions"):
        migration_compatibility(migrations)


def test_repository_migration_graph_has_single_head_and_joins_both_release_lines():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "api" / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "api" / "alembic"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["e1a7c94d5b62"]
    client_features = script.get_revision("e1a7c94d5b62")
    assert client_features.down_revision == "b6e8f9012acd"
    public_forms = script.get_revision("b6e8f9012acd")
    assert public_forms.down_revision == "0a6b9f2e3c41"
    website_sources = script.get_revision("0a6b9f2e3c41")
    assert website_sources.down_revision == "c9d84f2a1b70"
    alert_delivery = script.get_revision("c9d84f2a1b70")
    assert alert_delivery.down_revision == "8b31d04f2a77"
    release_merge = script.get_revision("8b31d04f2a77")
    assert set(release_merge.down_revision) == {"f2a3b4c5d6e7", "3a7b91c5d402"}


def test_database_upgrade_allows_fresh_and_signed_ancestor_revisions():
    schema = {"head": "head", "upgrade_from": ["head", "middle", "root"], "rollback_to": []}

    validate_database_upgrade_allowed(schema, ())
    validate_database_upgrade_allowed(schema, ("root",))
    validate_database_upgrade_allowed(schema, ("head",))


@pytest.mark.parametrize("revisions", [("unknown",), ("root", "head")])
def test_database_upgrade_rejects_unsupported_or_ambiguous_revisions(revisions):
    schema = {"head": "head", "upgrade_from": ["head", "root"], "rollback_to": []}

    with pytest.raises(SchemaCompatibilityError):
        validate_database_upgrade_allowed(schema, revisions)


@pytest.mark.asyncio
async def test_database_revision_reader_uses_alembic_version_table(monkeypatch):
    from contextlib import asynccontextmanager

    from api.services import release_schema

    statements = []

    class Result:
        def __init__(self, value=None, values=()):
            self.value = value
            self.values = values

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return self

        def all(self):
            return list(self.values)

    class Connection:
        async def execute(self, statement):
            statements.append(str(statement))
            if "to_regclass" in str(statement):
                return Result("alembic_version")
            return Result(values=("root",))

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield Connection()

        async def dispose(self):
            return None

    monkeypatch.setattr(release_schema, "create_async_engine", lambda *_args, **_kwargs: Engine())

    assert await release_schema.current_database_revisions("postgresql+asyncpg://example") == ("root",)
    assert "to_regclass('alembic_version')" in statements[0]
    assert "version_num FROM alembic_version" in statements[1]


@pytest.mark.asyncio
async def test_database_revision_reader_rejects_existing_empty_version_table(monkeypatch):
    from contextlib import asynccontextmanager

    from api.services import release_schema

    class Result:
        def __init__(self, value=None, values=()):
            self.value = value
            self.values = values

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return self

        def all(self):
            return list(self.values)

    class Connection:
        async def execute(self, statement):
            if "to_regclass" in str(statement):
                return Result("alembic_version")
            return Result(values=())

    class Engine:
        @asynccontextmanager
        async def connect(self):
            yield Connection()

        async def dispose(self):
            return None

    monkeypatch.setattr(release_schema, "create_async_engine", lambda *_args, **_kwargs: Engine())

    with pytest.raises(SchemaCompatibilityError, match="exists but contains no revision"):
        await release_schema.current_database_revisions("postgresql+asyncpg://example")
