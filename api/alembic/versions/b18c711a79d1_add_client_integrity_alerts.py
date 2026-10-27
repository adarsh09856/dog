"""Add deduplicated owner integrity notifications for client installations."""

import sqlalchemy as sa
from alembic import op

revision = "b18c711a79d1"
down_revision = "a14f4c19b782"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_integrity_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("installation_id", sa.String(length=100), sa.ForeignKey("client_installations.installation_id"), nullable=False),
        sa.Column("event_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("component", sa.String(length=500), nullable=False),
        sa.Column("expected_sha256", sa.String(length=64), nullable=True),
        sa.Column("observed_sha256", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("installation_id", "event_fingerprint", name="uq_client_integrity_alert_event"),
    )
    op.create_index("ix_client_integrity_alerts_installation_id", "client_integrity_alerts", ["installation_id"])
    op.create_index("ix_client_integrity_alerts_acknowledged_at", "client_integrity_alerts", ["acknowledged_at"])


def downgrade():
    op.drop_index("ix_client_integrity_alerts_acknowledged_at", table_name="client_integrity_alerts")
    op.drop_index("ix_client_integrity_alerts_installation_id", table_name="client_integrity_alerts")
    op.drop_table("client_integrity_alerts")
