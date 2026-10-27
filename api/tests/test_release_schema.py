from pathlib import Path

import pytest

from api.services.release_schema import (
    SchemaCompatibilityError,
    migration_compatibility,
    validate_database_upgrade_allowed,
)


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
