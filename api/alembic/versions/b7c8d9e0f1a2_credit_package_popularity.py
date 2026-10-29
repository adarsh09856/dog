"""Persist owner-selected credit package popularity.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_packages",
        sa.Column("is_popular", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Preserve the previously displayed badge on existing offers.
    op.execute("UPDATE credit_packages SET is_popular = (bonus_minutes > 0)")


def downgrade() -> None:
    op.drop_column("credit_packages", "is_popular")
