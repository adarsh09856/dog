"""Add immutable client releases and staged owner-controlled rollouts.

Revision ID: 8b31d04f2a77
Revises: f2a3b4c5d6e7, 3a7b91c5d402
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b31d04f2a77"
down_revision: Union[str, Sequence[str], None] = ("f2a3b4c5d6e7", "3a7b91c5d402")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_release_catalog",
        sa.Column("release_id", sa.String(length=100), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=False, unique=True),
        sa.Column("archive_url", sa.Text(), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("archive_signature", sa.String(length=86), nullable=False),
        sa.Column("min_current_version", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("signed_envelope", sa.JSON(), nullable=False),
        sa.Column("envelope_sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("state", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("state in ('draft', 'published')", name="ck_client_release_catalog_state"),
    )

    op.create_table(
        "client_release_rollouts",
        sa.Column("rollout_id", sa.String(length=36), primary_key=True),
        sa.Column("release_id", sa.String(length=100), sa.ForeignKey("client_release_catalog.release_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="staged", nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("created_by_user_id", "idempotency_key", name="uq_client_release_rollout_idempotency"),
        sa.CheckConstraint("state in ('staged', 'active', 'paused', 'stopped', 'completed')", name="ck_client_release_rollout_state"),
    )
    op.create_index("ix_client_release_rollouts_release_id", "client_release_rollouts", ["release_id"])

    op.create_table(
        "client_release_rollout_targets",
        sa.Column("rollout_id", sa.String(length=36), sa.ForeignKey("client_release_rollouts.rollout_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("installation_id", sa.String(length=100), sa.ForeignKey("client_installations.installation_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(length=16), server_default="staged", nullable=False),
        sa.Column("current_version", sa.String(length=32), nullable=True),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status in ('staged', 'downloading', 'applying', 'applied', 'failed', 'rolled_back')",
            name="ck_client_release_rollout_target_status",
        ),
    )
    op.create_index("ix_client_release_rollout_targets_installation_id", "client_release_rollout_targets", ["installation_id"])


def downgrade() -> None:
    op.drop_index("ix_client_release_rollout_targets_installation_id", table_name="client_release_rollout_targets")
    op.drop_table("client_release_rollout_targets")
    op.drop_index("ix_client_release_rollouts_release_id", table_name="client_release_rollouts")
    op.drop_table("client_release_rollouts")
    op.drop_table("client_release_catalog")
