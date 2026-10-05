"""add truth layer catalog tables and extensions

Revision ID: b2c3d4e5f6a7
Revises: f4b18c7d9a01
Create Date: 2026-10-05 18:00:00.000000

"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f4b18c7d9a01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    # 1. Extend platform_master_credentials if table exists
    if "platform_master_credentials" in tables:
        pmc_cols = [c["name"] for c in inspector.get_columns("platform_master_credentials")]
        if "extra_config" not in pmc_cols:
            op.add_column(
                "platform_master_credentials",
                sa.Column("extra_config", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
            )
        if "last_status" not in pmc_cols:
            op.add_column(
                "platform_master_credentials",
                sa.Column("last_status", sa.String(length=20), server_default="UNTESTED", nullable=False),
            )

    # 2. Extend ai_model_catalog if table exists
    if "ai_model_catalog" in tables:
        amc_cols = [c["name"] for c in inspector.get_columns("ai_model_catalog")]
        if "layer" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("layer", sa.String(length=20), server_default="llm", nullable=False),
            )
            # Backfill layer from category if category exists
            if "category" in amc_cols:
                op.execute("UPDATE ai_model_catalog SET layer = category WHERE layer = 'llm' AND category IS NOT NULL")
        if "enabled" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            )
        if "recommended" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("recommended", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            )
        if "is_default" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            )
        if "source" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("source", sa.String(length=30), server_default="built-in", nullable=False),
            )
        if "status" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("status", sa.String(length=20), server_default="UNTESTED", nullable=False),
            )
        if "latency_ms" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("latency_ms", sa.Integer(), nullable=True),
            )
        if "last_verified_at" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "last_error" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("last_error", sa.Text(), nullable=True),
            )
        if "languages" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("languages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
            )
        if "supports_tools" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("supports_tools", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            )
        if "supports_streaming" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("supports_streaming", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            )
        if "wholesale_cost" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("wholesale_cost", sa.Float(), server_default="0.0", nullable=False),
            )
        if "markup_percent" not in amc_cols:
            op.add_column(
                "ai_model_catalog",
                sa.Column("markup_percent", sa.Float(), server_default="0.0", nullable=False),
            )

        amc_indexes = [idx["name"] for idx in inspector.get_indexes("ai_model_catalog")]
        if "ix_amc_layer" not in amc_indexes:
            op.create_index("ix_amc_layer", "ai_model_catalog", ["layer"])
        if "ix_amc_enabled" not in amc_indexes:
            op.create_index("ix_amc_enabled", "ai_model_catalog", ["enabled"])

    # 3. Create voice_catalog table
    if "voice_catalog" not in tables:
        op.create_table(
            "voice_catalog",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("tts_model", sa.String(length=100), nullable=True),
            sa.Column("voice_id", sa.String(length=100), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("gender", sa.String(length=20), nullable=True),
            sa.Column("languages", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
            sa.Column("preview_url", sa.Text(), nullable=True),
            sa.Column("preview_ok", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("provider", "tts_model", "voice_id", name="uq_voice_provider_model_voice"),
        )
        op.create_index("ix_voice_catalog_provider", "voice_catalog", ["provider"])
        op.create_index("ix_voice_catalog_tts_model", "voice_catalog", ["tts_model"])
        op.create_index("ix_voice_catalog_voice_id", "voice_catalog", ["voice_id"])
        op.create_index("ix_voice_catalog_is_active", "voice_catalog", ["is_active"])

    # 4. Create catalog_verify_runs table
    if "catalog_verify_runs" not in tables:
        op.create_table(
            "catalog_verify_runs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("layer", sa.String(length=20), nullable=False),
            sa.Column("model_id", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("tested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_cvr_provider", "catalog_verify_runs", ["provider"])
        op.create_index("ix_cvr_layer", "catalog_verify_runs", ["layer"])
        op.create_index("ix_cvr_model_id", "catalog_verify_runs", ["model_id"])
        op.create_index("ix_cvr_tested_at", "catalog_verify_runs", ["tested_at"])

    # 5. Create org_ai_policy table
    if "org_ai_policy" not in tables:
        op.create_table(
            "org_ai_policy",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False),
            sa.Column("allowed_providers", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
            sa.Column("local_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("byok_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("s2s_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("fallback_chain", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
            sa.Column("concurrency_cap", sa.Integer(), server_default="5", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_org_ai_policy_org_id", "org_ai_policy", ["organization_id"], unique=True)

    # 6. Performance indexes
    if "workflow_runs" in tables:
        wf_indexes = [idx["name"] for idx in inspector.get_indexes("workflow_runs")]
        if "idx_workflow_runs_workflow_created" not in wf_indexes:
            op.create_index("idx_workflow_runs_workflow_created", "workflow_runs", ["workflow_id", "created_at"])

    if "wallet_ledger" in tables:
        wl_indexes = [idx["name"] for idx in inspector.get_indexes("wallet_ledger")]
        if "idx_wallet_ledger_org_created" not in wl_indexes:
            op.create_index("idx_wallet_ledger_org_created", "wallet_ledger", ["organization_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    tables = inspector.get_table_names()

    if "org_ai_policy" in tables:
        op.drop_table("org_ai_policy")

    if "catalog_verify_runs" in tables:
        op.drop_table("catalog_verify_runs")

    if "voice_catalog" in tables:
        op.drop_table("voice_catalog")
