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
    ContactModel,
    CreditPackageModel,
    FlaggedCallViolationModel,
    FormModel,
    FormSubmissionModel,
    GoogleCalendarCredentialModel,
    LeadActivityModel,
    LeadStageModel,
    OrganizationWalletModel,
    PlatformMasterCredentialModel,
    PromptTemplateModel,
    SaaSPlanModel,
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

    # ------------------------------------------------------------------------
    # Model Catalog
    # ------------------------------------------------------------------------
    async def list_active_models(self, category: Optional[str] = None) -> List[AIModelCatalogModel]:
        async with self.get_session() as session:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.is_active == True)
            if category:
                stmt = stmt.where(AIModelCatalogModel.category == category)
            stmt = stmt.order_by(AIModelCatalogModel.sort_order)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------------
    # Organization Wallets & Ledger
    # ------------------------------------------------------------------------
    async def get_or_create_wallet(self, organization_id: int) -> OrganizationWalletModel:
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
                wallet = OrganizationWalletModel(organization_id=organization_id, credit_balance_minutes=0)
                session.add(wallet)

            new_balance = max(0, wallet.credit_balance_minutes - minutes)
            wallet.credit_balance_minutes = new_balance
            wallet.updated_at = datetime.now(UTC)

            # Record in ledger
            ledger_entry = WalletLedgerModel(
                organization_id=organization_id,
                amount_minutes=-minutes,
                balance_after=new_balance,
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
        async with self.get_session() as session:
            stmt = select(GlobalPlatformSettingModel).where(GlobalPlatformSettingModel.key == key)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()
            return setting.value if setting else None

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
