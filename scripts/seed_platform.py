"""
Kodewaves Sovereign Platform — Initial Seed Data & Bootstrap Script
Idempotently initializes:
1. Global Platform Settings (Branding, BYOK policy, Wallet policy, SMTP)
2. SaaS Subscription Plans (Starter, Professional, Enterprise)
3. Credit Top-up Packages (500m, 2000m, 5000m, 10000m)
4. AI Model & Telephony Catalog (OpenAI, Anthropic, Sarvam, Deepgram, ElevenLabs, Cartesia)
5. Standard Content Moderation Words
6. Organization Wallets for superadmin and existing tenants
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, List
from sqlalchemy import select

from api.db import db_client
from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    AIModelCatalogModel,
    BannedWordModel,
    CreditPackageModel,
    GlobalPlatformSettingModel,
    OrganizationWalletModel,
    SaaSPlanModel,
    WalletLedgerModel,
)
from api.db.models import OrganizationModel, UserModel


async def seed_global_settings():
    print("[SEED] Seeding Global Platform Settings...")
    default_settings = [
        {
            "key": "branding",
            "category": "branding",
            "value": {
                "platform_name": "Kodewaves Sovereign Platform",
                "company_name": "Kodewaves Inc.",
                "logo_url": "/logo.png",
                "favicon_url": "/favicon.ico",
                "primary_color": "#0284c7",
                "support_email": "support@kodewaves.in",
            },
        },
        {
            "key": "byok_policy",
            "category": "byok",
            "value": {
                "allow_user_byok": True,
                "enforce_platform_keys": False,
                "supported_providers": ["openai", "anthropic", "sarvam", "elevenlabs", "deepgram", "cartesia", "twilio", "exotel"],
            },
        },
        {
            "key": "wallet_policy",
            "category": "wallet",
            "value": {
                "initial_bonus_minutes": 60,
                "low_balance_threshold": 15,
                "auto_recharge_enabled": False,
                "currency": "INR",
            },
        },
        {
            "key": "smtp",
            "category": "smtp",
            "value": {
                "host": "",
                "port": 587,
                "username": "",
                "password": "",
                "use_tls": True,
                "from_email": "no-reply@kodewaves.in",
                "is_active": False,
            },
        },
    ]

    async with kodewaves_db_client.get_session() as session:
        for item in default_settings:
            stmt = select(GlobalPlatformSettingModel).where(GlobalPlatformSettingModel.key == item["key"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                setting = GlobalPlatformSettingModel(
                    key=item["key"],
                    category=item["category"],
                    value=item["value"],
                )
                session.add(setting)
        await session.commit()
    print("[SUCCESS] Global Platform Settings verified.")


async def seed_saas_plans():
    print("[SEED] Seeding SaaS Subscription Plans...")
    default_plans = [
        {
            "name": "Starter",
            "code": "starter",
            "description": "Perfect for testing, solo operators, and pilots.",
            "monthly_price_cents": 249900,  # ₹2,499
            "annual_price_cents": 2499000,
            "currency": "INR",
            "included_monthly_minutes": 500,
            "max_agents": 3,
            "max_concurrent_calls": 2,
            "has_crm_access": True,
            "has_appointments_access": True,
            "has_forms_access": True,
            "has_widget_access": True,
            "allow_user_byok": True,
            "is_default": True,
            "is_active": True,
        },
        {
            "name": "Professional",
            "code": "pro",
            "description": "For growing businesses scaling voice automation.",
            "monthly_price_cents": 799900,  # ₹7,999
            "annual_price_cents": 7999000,
            "currency": "INR",
            "included_monthly_minutes": 2000,
            "max_agents": 10,
            "max_concurrent_calls": 10,
            "has_crm_access": True,
            "has_appointments_access": True,
            "has_forms_access": True,
            "has_widget_access": True,
            "allow_user_byok": True,
            "is_default": False,
            "is_active": True,
        },
        {
            "name": "Enterprise",
            "code": "enterprise",
            "description": "High concurrency, custom sovereign LLM endpoints, dedicated SLA.",
            "monthly_price_cents": 2499900,  # ₹24,999
            "annual_price_cents": 24999000,
            "currency": "INR",
            "included_monthly_minutes": 10000,
            "max_agents": 50,
            "max_concurrent_calls": 50,
            "has_crm_access": True,
            "has_appointments_access": True,
            "has_forms_access": True,
            "has_widget_access": True,
            "allow_user_byok": True,
            "is_default": False,
            "is_active": True,
        },
    ]

    async with kodewaves_db_client.get_session() as session:
        for p in default_plans:
            stmt = select(SaaSPlanModel).where(SaaSPlanModel.code == p["code"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                plan = SaaSPlanModel(**p)
                session.add(plan)
        await session.commit()
    print("[SUCCESS] SaaS Plans verified.")


async def seed_credit_packages():
    print("[SEED] Seeding Minute Top-up Bundles...")
    default_packages = [
        {"name": "500 Minutes Pack", "minutes": 500, "bonus_minutes": 0, "price_cents": 150000, "currency": "INR", "sort_order": 1},
        {"name": "2,000 Minutes Pack", "minutes": 2000, "bonus_minutes": 100, "price_cents": 550000, "currency": "INR", "sort_order": 2},
        {"name": "5,000 Minutes Pack", "minutes": 5000, "bonus_minutes": 500, "price_cents": 1250000, "currency": "INR", "sort_order": 3},
        {"name": "10,000 Minutes Pack", "minutes": 10000, "bonus_minutes": 1500, "price_cents": 2200000, "currency": "INR", "sort_order": 4},
    ]

    async with kodewaves_db_client.get_session() as session:
        for pkg in default_packages:
            stmt = select(CreditPackageModel).where(CreditPackageModel.name == pkg["name"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                bundle = CreditPackageModel(**pkg)
                session.add(bundle)
        await session.commit()
    print("[SUCCESS] Credit Packages verified.")


async def seed_ai_model_catalog():
    print("[SEED] Seeding Master AI Model & Voice Catalog...")
    default_models = [
        # LLMs
        {
            "model_identifier": "gpt-4o",
            "display_name": "GPT-4o (Omni)",
            "provider": "openai",
            "category": "llm",
            "base_cost_cents_per_unit": 0.50,
            "retail_price_cents_per_unit": 1.00,
            "sort_order": 1,
        },
        {
            "model_identifier": "gpt-4o-mini",
            "display_name": "GPT-4o Mini",
            "provider": "openai",
            "category": "llm",
            "base_cost_cents_per_unit": 0.10,
            "retail_price_cents_per_unit": 0.25,
            "sort_order": 2,
        },
        {
            "model_identifier": "claude-3-5-sonnet",
            "display_name": "Claude 3.5 Sonnet",
            "provider": "anthropic",
            "category": "llm",
            "base_cost_cents_per_unit": 0.60,
            "retail_price_cents_per_unit": 1.20,
            "sort_order": 3,
        },
        {
            "model_identifier": "sarvam-2b",
            "display_name": "Sarvam-2B (Indic Sovereign)",
            "provider": "sarvam",
            "category": "llm",
            "base_cost_cents_per_unit": 0.05,
            "retail_price_cents_per_unit": 0.15,
            "sort_order": 4,
        },
        # STT
        {
            "model_identifier": "deepgram-nova-2",
            "display_name": "Deepgram Nova-2",
            "provider": "deepgram",
            "category": "stt",
            "base_cost_cents_per_unit": 0.43,
            "retail_price_cents_per_unit": 0.80,
            "sort_order": 10,
        },
        {
            "model_identifier": "sarvam-saarika",
            "display_name": "Sarvam Saarika (10+ Indian Languages)",
            "provider": "sarvam",
            "category": "stt",
            "base_cost_cents_per_unit": 0.20,
            "retail_price_cents_per_unit": 0.50,
            "sort_order": 11,
        },
        # TTS
        {
            "model_identifier": "elevenlabs-turbo-v2-5",
            "display_name": "ElevenLabs Turbo v2.5",
            "provider": "elevenlabs",
            "category": "tts",
            "base_cost_cents_per_unit": 1.50,
            "retail_price_cents_per_unit": 2.50,
            "sort_order": 20,
        },
        {
            "model_identifier": "cartesia-sonic",
            "display_name": "Cartesia Sonic (Ultra-low latency)",
            "provider": "cartesia",
            "category": "tts",
            "base_cost_cents_per_unit": 0.50,
            "retail_price_cents_per_unit": 1.00,
            "sort_order": 21,
        },
        {
            "model_identifier": "sarvam-bulbul",
            "display_name": "Sarvam Bulbul (Indic TTS)",
            "provider": "sarvam",
            "category": "tts",
            "base_cost_cents_per_unit": 0.20,
            "retail_price_cents_per_unit": 0.50,
            "sort_order": 22,
        },
    ]

    async with kodewaves_db_client.get_session() as session:
        for m in default_models:
            stmt = select(AIModelCatalogModel).where(AIModelCatalogModel.model_identifier == m["model_identifier"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if not existing:
                item = AIModelCatalogModel(
                    model_identifier=m["model_identifier"],
                    display_name=m["display_name"],
                    provider=m["provider"],
                    category=m["category"],
                    base_cost_cents_per_unit=m["base_cost_cents_per_unit"],
                    retail_price_cents_per_unit=m["retail_price_cents_per_unit"],
                    allowed_plan_ids=["starter", "pro", "enterprise"],
                    is_active=True,
                    sort_order=m["sort_order"],
                )
                session.add(item)
        await session.commit()
    print("[SUCCESS] AI Model Catalog verified.")


async def seed_banned_words():
    print("[SEED] Seeding Standard Content Moderation Filter...")
    standard_words = ["scam", "credit card number", "cvv", "atm pin", "bank password", "otp verify"]
    async with kodewaves_db_client.get_session() as session:
        for w in standard_words:
            stmt = select(BannedWordModel).where(BannedWordModel.word == w)
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(BannedWordModel(word=w))
        await session.commit()
    print("[SUCCESS] Content Moderation Keywords verified.")


async def seed_wallets_for_existing_orgs():
    print("[SEED] Ensuring Wallets Exist For All Organizations...")
    async with db_client.async_session() as session:
        stmt = select(OrganizationModel)
        res = await session.execute(stmt)
        orgs = res.scalars().all()

    for org in orgs:
        wallet = await kodewaves_db_client.get_wallet(org.id)
        if not wallet or (wallet.credit_balance_minutes == 0 and wallet.bonus_minutes == 0):
            # Give initial operational balance (1000 minutes) to superadmin/first org
            await kodewaves_db_client.add_minutes(
                organization_id=org.id,
                minutes=1000,
                reason="admin_promo",
                notes="Platform initial deployment bootstrap bonus",
            )
            print(f"[SUCCESS] Initialized wallet for org {org.id} with 1,000 minutes.")


async def main():
    print("=================================================================")
    print("🚀 Starting Kodewaves Sovereign Platform Bootstrap Seeder...")
    print("=================================================================")
    await seed_global_settings()
    await seed_saas_plans()
    await seed_credit_packages()
    await seed_ai_model_catalog()
    await seed_banned_words()
    await seed_wallets_for_existing_orgs()
    print("=================================================================")
    print("🎉 Sovereign Platform Bootstrap Completed Successfully!")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())
