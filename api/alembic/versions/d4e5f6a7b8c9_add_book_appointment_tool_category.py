"""Add the native appointment tool category.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive and repeatable; existing tools and enum values are preserved.
    op.execute("ALTER TYPE public.tool_category ADD VALUE IF NOT EXISTS 'book_appointment'")


def downgrade() -> None:
    # PostgreSQL cannot remove a single enum value without rebuilding the type.
    # Retain it so rollback does not invalidate already-created booking tools.
    pass
