"""add public visibility to SaaS catalog plans

Revision ID: a6b7c8d9e0f1
Revises: e31f4a920b6c
Create Date: 2026-10-26 22:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "a6b7c8d9e0f1"
down_revision = "e31f4a920b6c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "saas_plans",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("saas_plans", "is_public", server_default=None)


def downgrade() -> None:
    op.drop_column("saas_plans", "is_public")
