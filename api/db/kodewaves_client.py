import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.base_client import BaseDBClient
from api.db.kodewaves_models import (
    AIModelCatalogModel,
    AppointmentModel,
    AppointmentSettingsModel,
    AuditLogModel,
    BannedWordModel,
    CatalogVerifyRunModel,
    ContactModel,
    CreditPackageModel,
    FlaggedCallViolationModel,
    FormModel,
    FormSubmissionModel,
    GoogleCalendarCredentialModel,
    LeadActivityModel,
    LeadStageModel,
    OrgAIPolicyModel,
    OrganizationWalletModel,
    PlatformMasterCredentialModel,
    PromptTemplateModel,
    SaaSPlanModel,
    VoiceCatalogModel,
    WalletLedgerModel,
    WebsiteWidgetModel,
    GlobalPlatformSettingModel,
)


class KodewavesDBClient(BaseDBClient):
    """Database client for Kodewaves sovereign platform and AgentLabs features."""

    def get_session(self):
        """Context manager returning an active AsyncSession."""
        return self.async_session()

    async def get_wallet(self, organization_id: int) -> Optional[OrganizationWalletModel]:
        """Retrieve the wallet record for an organization."""
        async with self.get_session() as session:
            stmt = select(OrganizationWalletModel).where(
                OrganizationWalletModel.organization_id == organization_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ------------------------------------------------------------------------
    # Master Credentials
    # ------------------------------------------------------------------------
    async def get_master_credential(self, provider: str) -> Optional[PlatformMasterCredentialModel]:
        async with self.get_session() as session:
            stmt = select(PlatformMasterCredentialModel).where(
                PlatformMasterCredentialModel.provider == provider,
                PlatformMasterCredentialModel.is_enabled == True,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_master_credentials(self) -> List[PlatformMasterCredentialModel]:
        async with self.get_session() as session:
            stmt = select(PlatformMasterCredentialModel).order_by(PlatformMasterCredentialModel.provider)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_master_credential(
        self,
        provider: str,
        category: str,
        credentials_encrypted: str,
        is_enabled: bool = True,
        health_status: str = "healthy",
    ) -> PlatformMasterCredentialModel:
        async with self.get_session() as session:
            stmt = select(PlatformMasterCredentialModel).where(PlatformMasterCredentialModel.provider == provider)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                record.category = category
                if credentials_encrypted:
                    record.credentials_encrypted = credentials_encrypted
                record.is_enabled = is_enabled
                record.health_status = health_status
                record.updated_at = datetime.now(UTC)
            else:
                record = PlatformMasterCredentialModel(
                    provider=provider,
                    category=category,
                    credentials_encrypted=credentials_encrypted,
                    is_enabled=is_enabled,
                    health_status=health_status,
                )
                session.add(record)

            await session.commit()
            await session.refresh(record)
            return record

    async def update_master_credential_health(self, provider: str, health_status: str) -> bool:
        """Update health status of master credentials without modifying credentials or category."""
        async with self.get_session() as session:
            stmt = select(PlatformMasterCredentialModel).where(
                PlatformMasterCredentialModel.provider == provider.lower().strip()
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                record.health_status = health_status
                record.updated_at = datetime.now(UTC)
                await session.commit()
                return True
            return False

    # ------------------------------------------------------------------------
    # Model Catalog (Truth Layer)
    # ------------------------------------------------------------------------
    async def list_models(
        self,
        layer: Optional[str] = None,
        provider: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[AIModelCatalogModel]:
        async with self.get_session() as session:
            stmt = select(AIModelCatalogModel)
            if enabled_only:
                stmt = stmt.where((AIModelCatalogModel.is_active == True) & (AIModelCatalogModel.enabled == True))
            if layer:
                stmt = stmt.where((AIModelCatalogModel.layer == layer) | (AIModelCatalogModel.category == layer))
            if provider:
                stmt = stmt.where(AIModelCatalogModel.provider == provider.lower().strip())
            stmt = stmt.order_by(AIModelCatalogModel.sort_order, AIModelCatalogModel.display_name)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_active_models(self, category: Optional[str] = None) -> List[AIModelCatalogModel]:
        return await self.list_models(layer=category, enabled_only=True)

    async def get_model(self, model_identifier: str) -> Optional[AIModelCatalogModel]:
        async with self.get_session() as session:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == model_identifier)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def upsert_model(
        self,
        model_identifier: str,
        display_name: str,
        provider: str,
        layer: str,
        enabled: bool = True,
        recommended: bool = False,
        is_default: bool = False,
        source: str = "built-in",
        status: str = "UNTESTED",
        latency_ms: Optional[int] = None,
        languages: Optional[List[str]] = None,
        supports_tools: bool = False,
        supports_streaming: bool = True,
        wholesale_cost: float = 0.0,
        markup_percent: float = 0.0,
        custom_base_url: Optional[str] = None,
    ) -> AIModelCatalogModel:
        async with self.get_session() as session:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == model_identifier)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            if model:
                model.display_name = display_name
                model.provider = provider.lower().strip()
                model.layer = layer
                model.category = layer
                model.enabled = enabled
                model.is_active = enabled
                model.recommended = recommended
                model.is_default = is_default
                model.source = source
                model.status = status
                if latency_ms is not None:
                    model.latency_ms = latency_ms
                if languages is not None:
                    model.languages = languages
                model.supports_tools = supports_tools
                model.supports_streaming = supports_streaming
                model.wholesale_cost = wholesale_cost
                model.markup_percent = markup_percent
                if custom_base_url is not None:
                    model.custom_base_url = custom_base_url
            else:
                model = AIModelCatalogModel(
                    model_identifier=model_identifier,
                    display_name=display_name,
                    provider=provider.lower().strip(),
                    category=layer,
                    layer=layer,
                    enabled=enabled,
                    is_active=enabled,
                    recommended=recommended,
                    is_default=is_default,
                    source=source,
                    status=status,
                    latency_ms=latency_ms,
                    languages=languages or [],
                    supports_tools=supports_tools,
                    supports_streaming=supports_streaming,
                    wholesale_cost=wholesale_cost,
                    markup_percent=markup_percent,
                    custom_base_url=custom_base_url,
                )
                session.add(model)
            await session.commit()
            await session.refresh(model)
            return model

    # ------------------------------------------------------------------------
    # Voice Catalog (Truth Layer)
    # ------------------------------------------------------------------------
    async def list_voices(
        self,
        provider: Optional[str] = None,
        tts_model: Optional[str] = None,
        language: Optional[str] = None,
        active_only: bool = True,
    ) -> List[VoiceCatalogModel]:
        async with self.get_session() as session:
            stmt = select(VoiceCatalogModel)
            if active_only:
                stmt = stmt.where(VoiceCatalogModel.is_active == True)
            if provider:
                stmt = stmt.where(VoiceCatalogModel.provider == provider.lower().strip())
            if tts_model:
                stmt = stmt.where(VoiceCatalogModel.tts_model == tts_model)
            result = await session.execute(stmt)
            voices = list(result.scalars().all())
            if language:
                lang_clean = language.lower().strip()
                voices = [v for v in voices if any(lang_clean in str(l).lower() for l in (v.languages or []))]
            return voices

    async def upsert_voice(
        self,
        provider: str,
        voice_id: str,
        name: str,
        tts_model: Optional[str] = None,
        gender: Optional[str] = None,
        languages: Optional[List[str]] = None,
        preview_url: Optional[str] = None,
        preview_ok: bool = True,
        is_active: bool = True,
    ) -> VoiceCatalogModel:
        async with self.get_session() as session:
            stmt = select(VoiceCatalogModel).where(
                VoiceCatalogModel.provider == provider.lower().strip(),
                VoiceCatalogModel.tts_model == tts_model,
                VoiceCatalogModel.voice_id == voice_id,
            )
            result = await session.execute(stmt)
            voice = result.scalar_one_or_none()

            if voice:
                voice.name = name
                voice.gender = gender
                if languages is not None:
                    voice.languages = languages
                if preview_url:
                    voice.preview_url = preview_url
                voice.preview_ok = preview_ok
                voice.is_active = is_active
                voice.updated_at = datetime.now(UTC)
            else:
                voice = VoiceCatalogModel(
                    provider=provider.lower().strip(),
                    tts_model=tts_model,
                    voice_id=voice_id,
                    name=name,
                    gender=gender,
                    languages=languages or [],
                    preview_url=preview_url,
                    preview_ok=preview_ok,
                    is_active=is_active,
                )
                session.add(voice)
            await session.commit()
            await session.refresh(voice)
            return voice

    # ------------------------------------------------------------------------
    # Verification Runs & Org Policy
    # ------------------------------------------------------------------------
    async def record_verify_run(
        self,
        provider: str,
        layer: str,
        status: str,
        latency_ms: Optional[int] = None,
        model_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> CatalogVerifyRunModel:
        async with self.get_session() as session:
            run = CatalogVerifyRunModel(
                provider=provider.lower().strip(),
                layer=layer.lower().strip(),
                model_id=model_id,
                status=status.upper().strip(),
                latency_ms=latency_ms,
                error_message=error_message,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run

    async def get_org_ai_policy(self, organization_id: int) -> Optional[OrgAIPolicyModel]:
        async with self.get_session() as session:
            stmt = select(OrgAIPolicyModel).where(OrgAIPolicyModel.organization_id == organization_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def upsert_org_ai_policy(
        self,
        organization_id: int,
        allowed_providers: Optional[List[str]] = None,
        local_allowed: bool = True,
        byok_allowed: bool = True,
        s2s_allowed: bool = True,
        fallback_chain: Optional[List[dict]] = None,
        concurrency_cap: int = 5,
    ) -> OrgAIPolicyModel:
        async with self.get_session() as session:
            stmt = select(OrgAIPolicyModel).where(OrgAIPolicyModel.organization_id == organization_id)
            result = await session.execute(stmt)
            policy = result.scalar_one_or_none()
            if policy:
                if allowed_providers is not None:
                    policy.allowed_providers = allowed_providers
                policy.local_allowed = local_allowed
                policy.byok_allowed = byok_allowed
                policy.s2s_allowed = s2s_allowed
                if fallback_chain is not None:
                    policy.fallback_chain = fallback_chain
                policy.concurrency_cap = concurrency_cap
                policy.updated_at = datetime.now(UTC)
            else:
                policy = OrgAIPolicyModel(
                    organization_id=organization_id,
                    allowed_providers=allowed_providers or [],
                    local_allowed=local_allowed,
                    byok_allowed=byok_allowed,
                    s2s_allowed=s2s_allowed,
                    fallback_chain=fallback_chain or [],
                    concurrency_cap=concurrency_cap,
                )
                session.add(policy)
            await session.commit()
            await session.refresh(policy)
            return policy

    # ------------------------------------------------------------------------
    # Organization Wallets & Ledger
    # ------------------------------------------------------------------------
    async def get_or_create_wallet(self, organization_id: int) -> Optional[OrganizationWalletModel]:
        try:
            async with self.get_session() as session:
                stmt = select(OrganizationWalletModel).where(OrganizationWalletModel.organization_id == organization_id)
                result = await session.execute(stmt)
                wallet = result.scalar_one_or_none()

                if not wallet:
                    wallet = OrganizationWalletModel(
                        organization_id=organization_id,
                        credit_balance_minutes=60, # 60 free trial minutes
                        bonus_minutes=0,
                    )
                    session.add(wallet)
                    await session.commit()
                    await session.refresh(wallet)

                return wallet
        except Exception:
            return None

    async def deduct_minutes(
        self,
        organization_id: int,
        minutes: int,
        reason: str = "call_usage",
        reference_id: Optional[str] = None,
    ) -> OrganizationWalletModel:
        async with self.get_session() as session:
            stmt = select(OrganizationWalletModel).where(OrganizationWalletModel.organization_id == organization_id)
            result = await session.execute(stmt)
            wallet = result.scalar_one_or_none()

            if not wallet:
                wallet = OrganizationWalletModel(organization_id=organization_id, credit_balance_minutes=0, bonus_minutes=0)
                session.add(wallet)

            credit_bal = wallet.credit_balance_minutes or 0
            bonus_bal = wallet.bonus_minutes or 0

            remaining_to_deduct = minutes
            if credit_bal >= remaining_to_deduct:
                wallet.credit_balance_minutes = credit_bal - remaining_to_deduct
                remaining_to_deduct = 0
            else:
                remaining_to_deduct -= credit_bal
                wallet.credit_balance_minutes = 0
                wallet.bonus_minutes = max(0, bonus_bal - remaining_to_deduct)

            total_remaining = (wallet.credit_balance_minutes or 0) + (wallet.bonus_minutes or 0)
            wallet.updated_at = datetime.now(UTC)

            # Record in ledger
            ledger_entry = WalletLedgerModel(
                organization_id=organization_id,
                amount_minutes=-minutes,
                balance_after=total_remaining,
                reason=reason,
                reference_id=reference_id,
            )
            session.add(ledger_entry)

            await session.commit()
            await session.refresh(wallet)
            return wallet

    async def add_minutes(
        self,
        organization_id: int,
        minutes: int,
        reason: str = "credit_purchase",
        reference_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> OrganizationWalletModel:
        async with self.get_session() as session:
            stmt = select(OrganizationWalletModel).where(OrganizationWalletModel.organization_id == organization_id)
            result = await session.execute(stmt)
            wallet = result.scalar_one_or_none()

            if not wallet:
                wallet = OrganizationWalletModel(organization_id=organization_id, credit_balance_minutes=0)
                session.add(wallet)

            new_balance = wallet.credit_balance_minutes + minutes
            wallet.credit_balance_minutes = new_balance
            wallet.updated_at = datetime.now(UTC)

            ledger_entry = WalletLedgerModel(
                organization_id=organization_id,
                amount_minutes=minutes,
                balance_after=new_balance,
                reason=reason,
                reference_id=reference_id,
                notes=notes,
            )
            session.add(ledger_entry)

            await session.commit()
            await session.refresh(wallet)
            return wallet

    # ------------------------------------------------------------------------
    # CRM & Contacts
    # ------------------------------------------------------------------------
    async def list_contacts(self, organization_id: int, limit: int = 100, offset: int = 0) -> List[ContactModel]:
        async with self.get_session() as session:
            stmt = (
                select(ContactModel)
                .where(ContactModel.organization_id == organization_id)
                .order_by(desc(ContactModel.created_at))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------------
    # Platform Settings
    # ------------------------------------------------------------------------
    async def get_setting(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            async with self.get_session() as session:
                stmt = select(GlobalPlatformSettingModel).where(GlobalPlatformSettingModel.key == key)
                result = await session.execute(stmt)
                setting = result.scalar_one_or_none()
                return setting.value if setting else None
        except Exception:
            return None

    async def set_setting(self, key: str, value: Dict[str, Any], category: str = "general") -> GlobalPlatformSettingModel:
        async with self.get_session() as session:
            stmt = select(GlobalPlatformSettingModel).where(GlobalPlatformSettingModel.key == key)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = value
                setting.category = category
                setting.updated_at = datetime.now(UTC)
            else:
                setting = GlobalPlatformSettingModel(key=key, value=value, category=category)
                session.add(setting)

            await session.commit()
            await session.refresh(setting)
            return setting

    # ------------------------------------------------------------------------
    # Audit Logs
    # ------------------------------------------------------------------------
    async def record_audit_log(
        self,
        actor_id: Optional[int],
        actor_email: Optional[str],
        action: str,
        resource_type: str,
        resource_id: str,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLogModel:
        async with self.get_session() as session:
            entry = AuditLogModel(
                actor_id=actor_id,
                actor_email=actor_email,
                action=action,
                resource_type=resource_type,
                resource_id=str(resource_id),
                changes=changes or {},
                ip_address=ip_address,
            )
            session.add(entry)
            await session.commit()
            return entry


kodewaves_db_client = KodewavesDBClient()
