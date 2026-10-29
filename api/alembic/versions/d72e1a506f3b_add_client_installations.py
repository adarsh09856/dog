"""Add owner-side client installation issuance records."""

import sqlalchemy as sa
from alembic import op

revision = "d72e1a506f3b"
down_revision = "f4d9b27c6a10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_installations",
        sa.Column("installation_id", sa.String(length=100), primary_key=True),
        sa.Column("customer_id", sa.String(length=100), nullable=False),
        sa.Column("domains", sa.JSON(), nullable=False),
        sa.Column("ip_ranges", sa.JSON(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("issued_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("integrity_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_installations_customer_id", "client_installations", ["customer_id"])


def downgrade():
    op.drop_index("ix_client_installations_customer_id", table_name="client_installations")
    op.drop_table("client_installations")
