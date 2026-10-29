"""Derive the migration compatibility claims included in signed releases."""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_REVISION = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class SchemaCompatibilityError(RuntimeError):
    """The installed database revision is not approved by the signed release."""


def validate_database_upgrade_allowed(
    schema: dict[str, object], current_revisions: tuple[str, ...]
) -> None:
    """Allow a fresh DB or exactly one revision listed as upgrade-compatible."""
    allowed = schema.get("upgrade_from") if isinstance(schema, dict) else None
    if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
        raise SchemaCompatibilityError("Signed release has invalid upgrade compatibility metadata")
    if not current_revisions:
        return
    if len(current_revisions) != 1:
        raise SchemaCompatibilityError(
            f"Database has {len(current_revisions)} Alembic revisions; expected exactly one"
        )
    current = current_revisions[0]
    if current not in allowed:
        raise SchemaCompatibilityError(
            f"Database revision {current} is not approved by this signed release; "
            "restore a compatible backup or use a supported upgrade image"
        )


async def current_database_revisions(database_url: str) -> tuple[str, ...]:
    """Read Alembic's current revision without applying migrations."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            table = await connection.execute(text("SELECT to_regclass('alembic_version')"))
            if table.scalar_one_or_none() is None:
                return ()
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revisions = tuple(result.scalars().all())
            if not revisions:
                raise SchemaCompatibilityError(
                    "Database alembic_version table exists but contains no revision"
                )
            return revisions
    finally:
        await engine.dispose()


async def verify_client_schema_before_migration() -> None:
    """Verify release files, then gate DB upgrades on signed compatibility."""
    from api.constants import DATABASE_URL, KODEWAVES_EDITION

    if KODEWAVES_EDITION != "client":
        return

    from api.services.release_integrity import verify_release_before_startup

    payload = verify_release_before_startup()
    schema = payload.get("schema_compatibility") if isinstance(payload, dict) else None
    if not isinstance(schema, dict):
        raise SchemaCompatibilityError(
            "Signed client release is missing database upgrade compatibility metadata"
        )
    revisions = await current_database_revisions(DATABASE_URL)
    validate_database_upgrade_allowed(schema, revisions)


def main() -> int:
    if sys.argv[1:] == ["--preflight-deploy"]:
        from api.constants import DATABASE_URL

        revisions = asyncio.run(current_database_revisions(DATABASE_URL))
        verify_deployment_migration_history(Path(__file__).resolve().parents[1] / "alembic" / "versions", revisions)
    elif not sys.argv[1:]:
        asyncio.run(verify_client_schema_before_migration())
    else:
        raise SystemExit("Usage: python -m api.services.release_schema [--preflight-deploy]")
    return 0


def migration_compatibility(
    migrations_dir: Path, approved_upgrade_from: tuple[str, ...] | list[str] = (),
) -> dict[str, object]:
    """Sign only explicitly approved upgrade origins in the Alembic history.

    Rollback support is intentionally empty until a prior app version has been
    exercised against a migrated database. The release record must not promise
    rollback compatibility based only on the existence of a migration graph.
    """
    revisions: dict[str, tuple[str, ...]] = {}
    for source in sorted(migrations_dir.glob("*.py")):
        module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        values: dict[str, object] = {}
        for node in module.body:
            if isinstance(node, ast.Assign):
                names = [target.id for target in node.targets if isinstance(target, ast.Name)]
                for name in ("revision", "down_revision"):
                    if name in names:
                        values[name] = ast.literal_eval(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in {"revision", "down_revision"} and node.value is not None:
                    values[node.target.id] = ast.literal_eval(node.value)

        revision = values.get("revision")
        down_revision = values.get("down_revision")
        if revision is None and down_revision is None:
            continue
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise ValueError(f"Invalid Alembic revision in {source}")
        if down_revision is None:
            parents: tuple[str, ...] = ()
        elif isinstance(down_revision, str):
            parents = (down_revision,)
        elif isinstance(down_revision, (tuple, list)) and all(
            isinstance(parent, str) and _REVISION.fullmatch(parent)
            for parent in down_revision
        ):
            parents = tuple(down_revision)
        else:
            raise ValueError(f"Invalid Alembic down_revision in {source}")
        if revision in revisions:
            raise ValueError(f"Duplicate Alembic revision: {revision}")
        revisions[revision] = parents

    if not revisions:
        raise ValueError(f"No Alembic revisions found in {migrations_dir}")
    known = set(revisions)
    parents = {parent for values in revisions.values() for parent in values}
    missing = sorted(parents - known)
    if missing:
        raise ValueError(f"Alembic history references missing revisions: {missing}")
    heads = sorted(known - parents)
    if len(heads) != 1:
        raise ValueError(f"Client release requires one Alembic head; found {heads}")

    ancestors: set[str] = set()

    def include(revision: str) -> None:
        if revision in ancestors:
            return
        ancestors.add(revision)
        for parent in revisions[revision]:
            include(parent)

    include(heads[0])
    approved = set(approved_upgrade_from)
    unsupported = sorted(approved - ancestors)
    if unsupported:
        raise ValueError(f"Approved upgrade revisions are not ancestors of the release head: {unsupported}")
    return {
        "head": heads[0],
        "upgrade_from": sorted(approved | {heads[0]}),
        "rollback_to": [],
    }


def verify_deployment_migration_history(migrations_dir: Path, current_revisions: tuple[str, ...]) -> None:
    """Reject a candidate that cannot upgrade the running database history."""
    if len(current_revisions) > 1:
        raise SchemaCompatibilityError("Database has multiple Alembic revisions; refusing deployment")
    try:
        migration_compatibility(migrations_dir, current_revisions)
    except ValueError as exc:
        raise SchemaCompatibilityError(f"Candidate migration history is incompatible: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
