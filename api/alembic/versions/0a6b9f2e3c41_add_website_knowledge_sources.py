"""Add organization-scoped website knowledge sources.

Revision ID: 0a6b9f2e3c41
Revises: c9d84f2a1b70
"""

from alembic import op
import sqlalchemy as sa


revision = "0a6b9f2e3c41"
down_revision = "c9d84f2a1b70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_website_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_uuid", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=2048), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("available_to_all_agents", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("refresh_interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("max_pages", sa.Integer(), server_default="50", nullable=False),
        sa.Column("last_refresh_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("etag", sa.String(length=256), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("pending_etag", sa.String(length=256), nullable=True),
        sa.Column("pending_content_hash", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_base_documents.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status in ('pending', 'crawling', 'indexing', 'ready', 'paused', 'error', 'deleted')", name="ck_kb_website_sources_status"),
        sa.CheckConstraint("refresh_interval_hours between 1 and 720", name="ck_kb_website_sources_refresh_interval"),
        sa.CheckConstraint("max_pages between 1 and 100", name="ck_kb_website_sources_max_pages"),
    )
    op.create_index("ix_kb_website_sources_source_uuid", "knowledge_base_website_sources", ["source_uuid"], unique=True)
    op.create_index("ix_kb_website_sources_due", "knowledge_base_website_sources", ["is_active", "next_refresh_at"])
    op.create_index("ix_kb_website_sources_org", "knowledge_base_website_sources", ["organization_id"])
    op.create_index(
        "uq_kb_website_sources_org_origin_active",
        "knowledge_base_website_sources",
        ["organization_id", "origin"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_kb_website_sources_org_origin_active", table_name="knowledge_base_website_sources")
    op.drop_index("ix_kb_website_sources_org", table_name="knowledge_base_website_sources")
    op.drop_index("ix_kb_website_sources_due", table_name="knowledge_base_website_sources")
    op.drop_index("ix_kb_website_sources_source_uuid", table_name="knowledge_base_website_sources")
    op.drop_table("knowledge_base_website_sources")
