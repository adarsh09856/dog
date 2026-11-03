"""Persist owner integrity-alert email delivery state.

Revision ID: c9d84f2a1b70
Revises: 8b31d04f2a77
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d84f2a1b70"
down_revision = "8b31d04f2a77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "client_integrity_alerts",
        sa.Column("email_status", sa.String(length=16), server_default="sent", nullable=False),
    )
    op.add_column(
        "client_integrity_alerts",
        sa.Column("email_attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "client_integrity_alerts", sa.Column("email_scheduled_for", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "client_integrity_alerts", sa.Column("email_last_attempt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "client_integrity_alerts", sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "client_integrity_alerts", sa.Column("email_last_error", sa.String(length=80), nullable=True)
    )
    op.create_check_constraint(
        "ck_client_integrity_alerts_email_status",
        "client_integrity_alerts",
        "email_status in ('pending', 'sending', 'sent', 'failed')",
    )
    # Historical alerts predate retry tracking; marking them sent avoids sending
    # a surprise burst of old integrity notifications during rollout.


def downgrade() -> None:
    op.drop_constraint(
        "ck_client_integrity_alerts_email_status", "client_integrity_alerts", type_="check"
    )
    op.drop_column("client_integrity_alerts", "email_last_error")
    op.drop_column("client_integrity_alerts", "email_sent_at")
    op.drop_column("client_integrity_alerts", "email_last_attempt_at")
    op.drop_column("client_integrity_alerts", "email_scheduled_for")
    op.drop_column("client_integrity_alerts", "email_attempt_count")
    op.drop_column("client_integrity_alerts", "email_status")
