"""add kodewaves saas and agentlabs models

Revision ID: f1a89c3d4b2e
Revises: e7254d2c6c18
Create Date: 2026-09-27 17:15:00.000000

"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f1a89c3d4b2e"
down_revision: Union[str, None] = "3a7b91c5d402"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. platform_master_credentials
    op.create_table(
        "platform_master_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("health_status", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pmc_provider", "platform_master_credentials", ["provider"], unique=True)

    # 2. ai_model_catalog
    op.create_table(
        "ai_model_catalog",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("model_identifier", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("base_cost_cents_per_unit", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("retail_price_cents_per_unit", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("custom_base_url", sa.String(length=255), nullable=True),
        sa.Column("allowed_plan_ids", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_amc_model_id", "ai_model_catalog", ["model_identifier"], unique=True)
    op.create_index("ix_amc_provider", "ai_model_catalog", ["provider"])
    op.create_index("ix_amc_category", "ai_model_catalog", ["category"])

    # 3. saas_plans
    op.create_table(
        "saas_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("monthly_price_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("annual_price_cents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
        sa.Column("included_monthly_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("max_agents", sa.Integer(), server_default="3", nullable=False),
        sa.Column("max_concurrent_calls", sa.Integer(), server_default="2", nullable=False),
        sa.Column("has_crm_access", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("has_appointments_access", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("has_forms_access", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("has_widget_access", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("allow_user_byok", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_saas_plans_code", "saas_plans", ["code"], unique=True)

    # 4. credit_packages
    op.create_table(
        "credit_packages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("bonus_minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. organization_wallets
    op.create_table(
        "organization_wallets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credit_balance_minutes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("bonus_minutes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_org_wallets_org_id", "organization_wallets", ["organization_id"], unique=True)

    # 6. wallet_ledger
    op.create_table(
        "wallet_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_minutes", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wallet_ledger_org_id", "wallet_ledger", ["organization_id"])
    op.create_index("ix_wallet_ledger_reason", "wallet_ledger", ["reason"])

    # 7. lead_stages
    op.create_table(
        "lead_stages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("color", sa.String(length=20), server_default="#3b82f6", nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index("ix_lead_stages_org_id", "lead_stages", ["organization_id"])

    # 8. contacts
    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", UUID(as_uuid=True), sa.ForeignKey("lead_stages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=150), nullable=True),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("custom_fields", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("total_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contacts_org_id", "contacts", ["organization_id"])
    op.create_index("ix_contacts_phone", "contacts", ["phone"])

    # 9. lead_activities
    op.create_table(
        "lead_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_activities_contact_id", "lead_activities", ["contact_id"])

    # 10. google_calendar_credentials
    op.create_table(
        "google_calendar_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("connected_email", sa.String(length=255), nullable=False),
        sa.Column("calendar_id", sa.String(length=255), server_default="primary", nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gcc_org_id", "google_calendar_credentials", ["organization_id"], unique=True)

    # 11. appointment_settings
    op.create_table(
        "appointment_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buffer_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("default_duration_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("working_hours", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("allow_overlapping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_appt_settings_org_id", "appointment_settings", ["organization_id"], unique=True)

    # 12. appointments
    op.create_table(
        "appointments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("google_event_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="scheduled", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointments_org_id", "appointments", ["organization_id"])

    # 13. forms
    op.create_table(
        "forms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields_schema", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_forms_org_id", "forms", ["organization_id"])

    # 14. form_submissions
    op.create_table(
        "form_submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("form_id", UUID(as_uuid=True), sa.ForeignKey("forms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_data", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_form_submissions_form_id", "form_submissions", ["form_id"])
    op.create_index("ix_form_submissions_org_id", "form_submissions", ["organization_id"])

    # 15. website_widgets
    op.create_table(
        "website_widgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("widget_name", sa.String(length=100), nullable=False),
        sa.Column("primary_color", sa.String(length=20), server_default="#4f46e5", nullable=False),
        sa.Column("bubble_title", sa.String(length=100), server_default="Talk to our AI Agent", nullable=False),
        sa.Column("bubble_subtitle", sa.String(length=150), server_default="Click to start voice call", nullable=True),
        sa.Column("position", sa.String(length=20), server_default="bottom-right", nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("allowed_domains", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_website_widgets_org_id", "website_widgets", ["organization_id"])

    # 16. prompt_templates
    op.create_table(
        "prompt_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("first_message", sa.Text(), nullable=False),
        sa.Column("recommended_tools", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("is_system_template", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prompt_templates_category", "prompt_templates", ["category"])

    # 17. banned_words
    op.create_table(
        "banned_words",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), server_default="profanity", nullable=False),
        sa.Column("severity", sa.String(length=20), server_default="high", nullable=False),
        sa.Column("auto_block", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_banned_words_word", "banned_words", ["word"], unique=True)

    # 18. flagged_call_violations
    op.create_table(
        "flagged_call_violations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_word", sa.String(length=100), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("speaker", sa.String(length=20), nullable=False),
        sa.Column("action_taken", sa.String(length=30), nullable=False),
        sa.Column("is_reviewed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fcv_run_id", "flagged_call_violations", ["workflow_run_id"])
    op.create_index("ix_fcv_org_id", "flagged_call_violations", ["organization_id"])

    # 19. global_platform_settings
    op.create_table(
        "global_platform_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gps_key", "global_platform_settings", ["key"], unique=True)
    op.create_index("ix_gps_category", "global_platform_settings", ["category"])

    # 20. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=False),
        sa.Column("changes", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("global_platform_settings")
    op.drop_table("flagged_call_violations")
    op.drop_table("banned_words")
    op.drop_table("prompt_templates")
    op.drop_table("website_widgets")
    op.drop_table("form_submissions")
    op.drop_table("forms")
    op.drop_table("appointments")
    op.drop_table("appointment_settings")
    op.drop_table("google_calendar_credentials")
    op.drop_table("lead_activities")
    op.drop_table("contacts")
    op.drop_table("lead_stages")
    op.drop_table("wallet_ledger")
    op.drop_table("organization_wallets")
    op.drop_table("credit_packages")
    op.drop_table("saas_plans")
    op.drop_table("ai_model_catalog")
    op.drop_table("platform_master_credentials")
