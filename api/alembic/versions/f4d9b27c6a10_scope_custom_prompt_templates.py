"""Assign workspace ownership to new custom prompt templates."""

import sqlalchemy as sa
from alembic import op

revision = "f4d9b27c6a10"
down_revision = "e9c27a40b615"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "prompt_templates", sa.Column("organization_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_prompt_template_organization",
        "prompt_templates",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_prompt_templates_organization_id", "prompt_templates", ["organization_id"]
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM prompt_templates WHERE organization_id IS NOT NULL)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Cannot remove workspace ownership while private prompt templates exist"
        )
    op.drop_index("ix_prompt_templates_organization_id", table_name="prompt_templates")
    op.drop_constraint(
        "fk_prompt_template_organization", "prompt_templates", type_="foreignkey"
    )
    op.drop_column("prompt_templates", "organization_id")
