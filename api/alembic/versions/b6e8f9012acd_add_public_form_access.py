"""Add opt-in, token-authenticated public form submissions.

Revision ID: b6e8f9012acd
Revises: 0a6b9f2e3c41
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e8f9012acd"
down_revision = "0a6b9f2e3c41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "forms",
        sa.Column(
            "public_submission_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "forms",
        sa.Column("public_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "forms",
        sa.Column(
            "public_allowed_origins",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_forms_public_token_hash",
        "forms",
        ["public_token_hash"],
        unique=True,
    )
    op.alter_column("forms", "public_allowed_origins", server_default=None)
    op.alter_column("forms", "public_submission_enabled", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_forms_public_token_hash", table_name="forms")
    op.drop_column("forms", "public_allowed_origins")
    op.drop_column("forms", "public_token_hash")
    op.drop_column("forms", "public_submission_enabled")
