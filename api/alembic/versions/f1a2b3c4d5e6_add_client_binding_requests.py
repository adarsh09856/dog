"""Add owner-reviewed client installation binding change requests."""

import sqlalchemy as sa
from alembic import op


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_binding_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.String(length=100), nullable=False),
        sa.Column("requested_domains", sa.JSON(), nullable=False),
        sa.Column("requested_ip_ranges", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("license_issued_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["client_installations.installation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_client_binding_requests_status",
        ),
    )
    op.create_index(
        "ix_client_binding_requests_installation_id",
        "client_binding_requests", ["installation_id"],
    )
    op.create_index("ix_client_binding_requests_status", "client_binding_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_client_binding_requests_status", table_name="client_binding_requests")
    op.drop_index("ix_client_binding_requests_installation_id", table_name="client_binding_requests")
    op.drop_table("client_binding_requests")
