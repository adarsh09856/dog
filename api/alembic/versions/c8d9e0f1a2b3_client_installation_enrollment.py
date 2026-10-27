"""Store a one-time enrollment token fingerprint and client public key.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_installations", sa.Column("installation_public_key", sa.String(43), nullable=True))
    op.add_column("client_installations", sa.Column("enrollment_token_fingerprint", sa.String(64), nullable=True))
    op.add_column("client_installations", sa.Column("enrollment_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_installations", sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("client_installations", "enrolled_at")
    op.drop_column("client_installations", "enrollment_expires_at")
    op.drop_column("client_installations", "enrollment_token_fingerprint")
    op.drop_column("client_installations", "installation_public_key")
