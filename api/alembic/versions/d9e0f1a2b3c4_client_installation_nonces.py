"""Prevent replay of signed installation owner checks.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_installation_nonces",
        sa.Column("installation_id", sa.String(100), sa.ForeignKey("client_installations.installation_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("nonce_fingerprint", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("client_installation_nonces")
