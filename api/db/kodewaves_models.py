import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from api.db.models import Base

# ============================================================================
# 1. PLATFORM MASTER CREDENTIALS (Centralized Sovereign Keys)
# ============================================================================
class PlatformMasterCredentialModel(Base):
    """Admin-configured master credentials for platform-managed mode"""
    __tablename__ = "platform_master_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), unique=True, index=True, nullable=False) # 'openai', 'anthropic', 'sarvam', 'deepgram', 'elevenlabs', 'exotel', 'twilio', 'tata'
    category = Column(String(20), nullable=False)                          # 'llm', 'tts', 'stt', 'sts', 'telephony'
    credentials_encrypted = Column(Text, nullable=False)                   # Encrypted JSON string
    extra_config = Column(JSON, default=dict, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    health_status = Column(String(20), default="unknown", nullable=False)  # 'healthy', 'invalid', 'error'
    last_status = Column(String(20), default="UNTESTED", nullable=False)   # 'PASS', 'FAIL', 'UNTESTED'
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


# ============================================================================
# 2. GRANULAR AI MODEL & VOICE CATALOG (Admin Pricing, Margins, Endpoints)
# ============================================================================
class AIModelCatalogModel(Base):
    """Admin-curated AI models with token costs, margins, and plan assignments"""
    __tablename__ = "ai_model_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_identifier = Column(String(100), unique=True, nullable=False, index=True) # 'gpt-4o', 'llama-3.3-70b', 'gemini-3.5-flash'
    display_name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False, index=True)                       # 'openai', 'sarvam', 'anthropic', 'custom_openai_compatible'
    category = Column(String(20), nullable=False, index=True)                       # 'llm', 'stt', 'tts', 'sts'
    layer = Column(String(20), default="llm", nullable=False, index=True)           # 'llm', 'stt', 'tts', 'embeddings', 's2s'
    base_cost_cents_per_unit = Column(Float, default=0.0, nullable=False)
    retail_price_cents_per_unit = Column(Float, default=0.0, nullable=False)
    custom_base_url = Column(String(255), nullable=True)                            # For Ollama / vLLM / Groq custom endpoints
    allowed_plan_ids = Column(JSON, default=list, nullable=False)                   # JSON list of plan codes allowed to use this model
    is_active = Column(Boolean, default=True, index=True, nullable=False)
    enabled = Column(Boolean, default=True, index=True, nullable=False)
    recommended = Column(Boolean, default=False, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    source = Column(String(30), default="built-in", nullable=False)                 # 'built-in', 'discovered', 'custom'
    status = Column(String(20), default="UNTESTED", nullable=False)                 # 'PASS', 'FAIL', 'UNTESTED', 'UNAVAILABLE'
    latency_ms = Column(Integer, nullable=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    languages = Column(JSON, default=list, nullable=False)                          # e.g. ["hi", "en"]
    supports_tools = Column(Boolean, default=False, nullable=False)
    supports_streaming = Column(Boolean, default=True, nullable=False)
    wholesale_cost = Column(Float, default=0.0, nullable=False)
    markup_percent = Column(Float, default=0.0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class VoiceCatalogModel(Base):
    """Voice catalog per provider, tts model and language with preview testing"""
    __tablename__ = "voice_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    tts_model = Column(String(100), nullable=True, index=True)
    voice_id = Column(String(100), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    gender = Column(String(20), nullable=True)
    languages = Column(JSON, default=list, nullable=False)
    preview_url = Column(Text, nullable=True)
    preview_ok = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("provider", "tts_model", "voice_id", name="uq_voice_provider_model_voice"),
    )


class CatalogVerifyRunModel(Base):
    """History of Verify test executions and latency/error tracking"""
    __tablename__ = "catalog_verify_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    layer = Column(String(20), nullable=False, index=True)
    model_id = Column(String(100), nullable=True, index=True)
    status = Column(String(20), nullable=False)
    latency_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    tested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class OrgAIPolicyModel(Base):
    """Organization-level AI provider & capability policy"""
    __tablename__ = "org_ai_policy"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    allowed_providers = Column(JSON, default=list, nullable=False)
    local_allowed = Column(Boolean, default=True, nullable=False)
    byok_allowed = Column(Boolean, default=True, nullable=False)
    s2s_allowed = Column(Boolean, default=True, nullable=False)
    fallback_chain = Column(JSON, default=list, nullable=False)
    concurrency_cap = Column(Integer, default=5, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")


# ============================================================================
# 3. SAAS PLANS, WALLETS & TOP-UP PACKAGES
# ============================================================================
class SaaSPlanModel(Base):
    """Subscription tiers and feature entitlements"""
    __tablename__ = "saas_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)                                      # 'Starter', 'Pro', 'Enterprise'
    code = Column(String(50), unique=True, nullable=False, index=True)             # 'starter', 'pro', 'enterprise'
    description = Column(Text, nullable=True)
    monthly_price_cents = Column(Integer, default=0, nullable=False)               # In cents or paise
    annual_price_cents = Column(Integer, default=0, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)                   # 'INR' or 'USD'
    included_monthly_minutes = Column(Integer, default=60, nullable=False)
    max_agents = Column(Integer, default=3, nullable=False)
    max_concurrent_calls = Column(Integer, default=2, nullable=False)
    has_crm_access = Column(Boolean, default=True, nullable=False)
    has_appointments_access = Column(Boolean, default=True, nullable=False)
    has_forms_access = Column(Boolean, default=True, nullable=False)
    has_widget_access = Column(Boolean, default=True, nullable=False)
    allow_user_byok = Column(Boolean, default=False, nullable=False)               # Admin per-plan BYOK control
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CreditPackageModel(Base):
    """Purchasable minute top-up bundles"""
    __tablename__ = "credit_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)                                     # '500 Minutes Pack'
    minutes = Column(Integer, nullable=False)                                      # 500
    bonus_minutes = Column(Integer, default=0, nullable=False)
    price_cents = Column(Integer, nullable=False)                                  # In cents or paise
    currency = Column(String(10), default="INR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class OrganizationWalletModel(Base):
    """Organization credit minute balance"""
    __tablename__ = "organization_wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    credit_balance_minutes = Column(BigInteger, default=0, nullable=False)
    bonus_minutes = Column(BigInteger, default=0, nullable=False)
    is_frozen = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")


class WalletLedgerModel(Base):
    """Immutable audit ledger of all minute debits and top-ups"""
    __tablename__ = "wallet_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    amount_minutes = Column(Integer, nullable=False)                               # Negative for calls, positive for topups
    balance_after = Column(BigInteger, nullable=False)
    reason = Column(String(50), nullable=False, index=True)                        # 'call_usage', 'credit_purchase', 'admin_promo'
    reference_id = Column(String(100), nullable=True)                             # call run_id or payment_intent_id
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")


# ============================================================================
# 4. CRM & CONTACTS PIPELINE (AgentLabs Feature)
# ============================================================================
class LeadStageModel(Base):
    """Configurable sales pipeline stages"""
    __tablename__ = "lead_stages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False)                                      # 'New Lead', 'Contacted', 'Qualified', 'Closed'
    color = Column(String(20), default="#3b82f6", nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    organization = relationship("OrganizationModel")
    contacts = relationship("ContactModel", back_populates="stage")


class ContactModel(Base):
    """Standalone CRM contacts with interaction history"""
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("lead_stages.id", ondelete="SET NULL"), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    company = Column(String(150), nullable=True)
    tags = Column(JSON, default=list, nullable=False)
    custom_fields = Column(JSON, default=dict, nullable=False)
    total_calls = Column(Integer, default=0, nullable=False)
    last_contacted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")
    stage = relationship("LeadStageModel", back_populates="contacts")
    activities = relationship("LeadActivityModel", back_populates="contact", cascade="all, delete-orphan")


class LeadActivityModel(Base):
    """Activity history on contacts (calls, notes, stage transitions)"""
    __tablename__ = "lead_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type = Column(String(50), nullable=False)                             # 'call', 'note', 'stage_change'
    summary = Column(Text, nullable=False)
    call_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    contact = relationship("ContactModel", back_populates="activities")


# ============================================================================
# 5. APPOINTMENTS & CALENDAR BOOKING (AgentLabs Feature)
# ============================================================================
class GoogleCalendarCredentialModel(Base):
    """Google Calendar OAuth tokens per organization"""
    __tablename__ = "google_calendar_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    connected_email = Column(String(255), nullable=False)
    calendar_id = Column(String(255), default="primary", nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)

    organization = relationship("OrganizationModel")


class AppointmentSettingsModel(Base):
    """Working hours and buffer times for AI agent calendar booking"""
    __tablename__ = "appointment_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    buffer_minutes = Column(Integer, default=15, nullable=False)
    default_duration_minutes = Column(Integer, default=30, nullable=False)
    working_hours = Column(JSON, default=dict, nullable=False)                     # {"monday": {"start": "09:00", "end": "17:00", "enabled": True}}
    allow_overlapping = Column(Boolean, default=False, nullable=False)

    organization = relationship("OrganizationModel")


class AppointmentModel(Base):
    """Appointments booked by AI voice agents during customer calls"""
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    google_event_id = Column(String(255), nullable=True)
    status = Column(String(30), default="scheduled", nullable=False)               # 'scheduled', 'completed', 'cancelled'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")
    contact = relationship("ContactModel")


# ============================================================================
# 6. DYNAMIC FORMS & SUBMISSIONS (AgentLabs Feature)
# ============================================================================
class FormModel(Base):
    """Custom form definition populated by voice agents"""
    __tablename__ = "forms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    fields_schema = Column(JSON, default=list, nullable=False)                     # [{id: 'f1', label: 'Company Size', type: 'select'}]
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")
    submissions = relationship("FormSubmissionModel", back_populates="form", cascade="all, delete-orphan")


class FormSubmissionModel(Base):
    """Answers captured in real-time during conversations"""
    __tablename__ = "form_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    form_id = Column(UUID(as_uuid=True), ForeignKey("forms.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    call_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    submitted_data = Column(JSON, default=dict, nullable=False)                    # {'Company Size': '11-50'}
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    form = relationship("FormModel", back_populates="submissions")
    organization = relationship("OrganizationModel")


# ============================================================================
# 7. WEBSITE VOICE EMBED WIDGETS & PROMPT TEMPLATES (AgentLabs Feature)
# ============================================================================
class WebsiteWidgetModel(Base):
    """Embeddable WebRTC voice button for client websites"""
    __tablename__ = "website_widgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    widget_name = Column(String(100), nullable=False)
    primary_color = Column(String(20), default="#4f46e5", nullable=False)
    bubble_title = Column(String(100), default="Talk to our AI Agent", nullable=False)
    bubble_subtitle = Column(String(150), default="Click to start voice call", nullable=True)
    position = Column(String(20), default="bottom-right", nullable=False)          # 'bottom-right', 'bottom-left'
    avatar_url = Column(Text, nullable=True)
    allowed_domains = Column(JSON, default=list, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")
    workflow = relationship("WorkflowModel")


class PromptTemplateModel(Base):
    """Pre-built industry voice agent templates"""
    __tablename__ = "prompt_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(50), nullable=False, index=True)                      # 'Real Estate', 'Healthcare', 'Banking', 'Support'
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    system_prompt = Column(Text, nullable=False)
    first_message = Column(Text, nullable=False)
    recommended_tools = Column(JSON, default=list, nullable=False)
    is_system_template = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# ============================================================================
# 8. CONTENT MODERATION, GLOBAL SETTINGS & AUDIT LOGS
# ============================================================================
class BannedWordModel(Base):
    """Content moderation keywords with auto-block rules"""
    __tablename__ = "banned_words"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(50), default="profanity", nullable=False)
    severity = Column(String(20), default="high", nullable=False)                  # 'low', 'medium', 'high'
    auto_block = Column(Boolean, default=True, nullable=False)                     # Force hangup if heard
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class FlaggedCallViolationModel(Base):
    """Calls flagged by the moderation scanner"""
    __tablename__ = "flagged_call_violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    triggered_word = Column(String(100), nullable=False)
    snippet = Column(Text, nullable=False)
    speaker = Column(String(20), nullable=False)                                   # 'user' or 'agent'
    action_taken = Column(String(30), nullable=False)                              # 'logged', 'call_terminated'
    is_reviewed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    organization = relationship("OrganizationModel")
    workflow_run = relationship("WorkflowRunModel")


class GlobalPlatformSettingModel(Base):
    """Platform settings store (SMTP, Branding, Gateway credentials, Admin BYOK Toggle)"""
    __tablename__ = "global_platform_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), unique=True, nullable=False, index=True)             # 'branding', 'smtp', 'gateways', 'byok_policy'
    value = Column(JSON, nullable=False)                                           # JSON payload
    category = Column(String(50), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class AuditLogModel(Base):
    """Immutable audit log of all administrative actions"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False, index=True)                       # 'user.ban', 'key.update', 'credits.promo'
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(100), nullable=False)
    changes = Column(JSON, default=dict, nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    actor = relationship("UserModel")
