"""Persist a unique form slug within each workspace."""

import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def _slug_base(name: str | None) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return (slug or "form")[:100].rstrip("-") or "form"


def _backfill_rows(rows):
    """Assign stable, workspace-unique values without dropping existing forms."""
    used_by_org: dict[int, set[str]] = {}
    updates = []
    for row in rows:
        organization_id = row["organization_id"]
        used = used_by_org.setdefault(organization_id, set())
        base = _slug_base(row["name"])
        slug = base
        if slug in used:
            suffix = str(row["id"]).replace("-", "")[:8].lower()
            slug = f"{base[: 100 - len(suffix) - 1].rstrip('-')}-{suffix}"
            counter = 2
            while slug in used:
                extra = f"-{counter}"
                slug = (
                    f"{base[: 100 - len(suffix) - len(extra) - 1].rstrip('-')}"
                    f"-{suffix}{extra}"
                )
                counter += 1
        used.add(slug)
        updates.append({"id": row["id"], "slug": slug})
    return updates


def upgrade() -> None:
    op.add_column("forms", sa.Column("slug", sa.String(length=100), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, organization_id, name FROM forms "
            "ORDER BY organization_id, created_at, id"
        )
    ).mappings()
    updates = _backfill_rows(rows)
    if updates:
        bind.execute(
            sa.text("UPDATE forms SET slug = :slug WHERE id = :id"), updates
        )
    op.alter_column("forms", "slug", nullable=False)
    op.create_unique_constraint(
        "uq_forms_organization_slug", "forms", ["organization_id", "slug"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_forms_organization_slug", "forms", type_="unique")
    op.drop_column("forms", "slug")
