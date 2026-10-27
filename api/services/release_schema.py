"""Derive the migration compatibility claims included in signed releases."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REVISION = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def migration_compatibility(migrations_dir: Path) -> dict[str, object]:
    """Return the sole Alembic head and its known upgrade ancestors.

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
    return {
        "head": heads[0],
        "upgrade_from": sorted(ancestors),
        "rollback_to": [],
    }
