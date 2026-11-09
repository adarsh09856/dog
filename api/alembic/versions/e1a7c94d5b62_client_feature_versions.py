"""Add versioned client feature semantics for backward-compatible granularity.

Revision ID: e1a7c94d5b62
Revises: b6e8f9012acd
"""

from alembic import op
import sqlalchemy as sa


revision = "e1a7c94d5b62"
down_revision = "b6e8f9012acd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_installations",
        sa.Column("feature_version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("client_installations", "feature_version")
