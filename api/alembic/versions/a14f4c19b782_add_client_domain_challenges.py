"""Add owner-side DNS challenges for licensed client domains."""

import sqlalchemy as sa
from alembic import op

revision = "a14f4c19b782"
down_revision = "d72e1a506f3b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_domain_challenges",
        sa.Column("customer_id", sa.String(length=100), primary_key=True),
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("client_domain_challenges")
