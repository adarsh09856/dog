"""Allow bounded overlap when renewing a signed client installation license."""

import sqlalchemy as sa
from alembic import op

revision = "c29e8a75d41b"
down_revision = "b18c711a79d1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("client_installations", sa.Column("previous_token_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("client_installations", sa.Column("previous_token_valid_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_installations", sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("client_installations", sa.Column("renewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))


def downgrade():
    op.drop_column("client_installations", "renewed_by_user_id")
    op.drop_column("client_installations", "renewed_at")
    op.drop_column("client_installations", "previous_token_valid_until")
    op.drop_column("client_installations", "previous_token_fingerprint")
