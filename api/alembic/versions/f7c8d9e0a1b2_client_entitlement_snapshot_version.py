"""Add owner-managed client entitlement snapshot version.

Revision ID: f7c8d9e0a1b2
Revises: e1a7c94d5b62
"""

from alembic import op
import sqlalchemy as sa


revision = "f7c8d9e0a1b2"
down_revision = "e1a7c94d5b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_installations",
        sa.Column("entitlement_version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("client_installations", "entitlement_version")
