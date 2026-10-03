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
        # Gemini Models (NEW — Added in Kodewaves v2)
        {
            "model_identifier": "gemini-2.5-flash",
            "display_name": "Gemini 2.5 Flash",
            "provider": "google",
            "category": "llm",
            "base_cost_cents_per_unit": 0.15,
            "retail_price_cents_per_unit": 0.35,
            "sort_order": 5,
        },
        {
            "model_identifier": "gemini-2.5-pro",
            "display_name": "Gemini 2.5 Pro",
            "provider": "google",
            "category": "llm",
            "base_cost_cents_per_unit": 1.25,
            "retail_price_cents_per_unit": 2.00,
            "sort_order": 6,
        },
        {
            "model_identifier": "gemini-tts",
            "display_name": "Gemini AI Studio TTS",
            "provider": "google_gemini_tts",
            "category": "tts",
            "base_cost_cents_per_unit": 0.30,
            "retail_price_cents_per_unit": 0.60,
            "sort_order": 23,
        },
        # Navana Indic Models (NEW — Added in Kodewaves v2)
        {
            "model_identifier": "navana-hi-banking-v2-8khz",
            "display_name": "Navana Hindi STT (Banking)",
            "provider": "navana",
            "category": "stt",
            "base_cost_cents_per_unit": 0.15,
            "retail_price_cents_per_unit": 0.40,
            "sort_order": 12,
        },
        {
            "model_identifier": "navana-hi-tts",
            "display_name": "Navana Hindi TTS",
            "provider": "navana",
            "category": "tts",
            "base_cost_cents_per_unit": 0.15,
            "retail_price_cents_per_unit": 0.40,
            "sort_order": 24,
        },
        # Local CPU Models (Speaches + Ollama + Piper — Zero Cloud Cost)
        {
            "model_identifier": "speaches-whisper-tiny",
            "display_name": "Speaches Whisper Tiny (Local CPU STT)",
            "provider": "speaches",
            "category": "stt",
            "base_cost_cents_per_unit": 0.00,
            "retail_price_cents_per_unit": 0.00,
            "sort_order": 13,
        },
        {
            "model_identifier": "faster-whisper-base",
            "display_name": "Faster-Whisper Base (Local CPU STT - English & Hindi)",
            "provider": "speaches",
            "category": "stt",
            "base_cost_cents_per_unit": 0.00,
            "retail_price_cents_per_unit": 0.00,
            "sort_order": 14,
        },
        {
            "model_identifier": "piper-hindi",
            "display_name": "Piper TTS (Native Hindi & Indic ONNX)",
            "provider": "piper",
            "category": "tts",
            "base_cost_cents_per_unit": 0.00,
            "retail_price_cents_per_unit": 0.00,
            "sort_order": 25,
        },
        {
            "model_identifier": "speaches-kokoro-82m",
            "display_name": "Speaches Kokoro-82M (Local CPU TTS)",
            "provider": "speaches",
            "category": "tts",
            "base_cost_cents_per_unit": 0.00,
            "retail_price_cents_per_unit": 0.00,
            "sort_order": 26,
        },
        {
            "model_identifier": "ollama-qwen2.5:0.5b",
            "display_name": "Ollama Qwen2.5 0.5B (Local CPU LLM)",
            "provider": "ollama",
            "category": "llm",
            "base_cost_cents_per_unit": 0.00,
            "retail_price_cents_per_unit": 0.00,
            "sort_order": 7,
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


async def seed_prompt_templates():
    """Seed industry prompt templates so the gallery is ready on first login."""
    from api.db.kodewaves_models import PromptTemplateModel

    print("[SEED] Seeding Industry Voice Prompt Templates...")
    default_templates = [
        {
            "category": "Real Estate",
            "title": "Property Inquiry Handler",
            "description": "Handles inbound property inquiries, captures lead details, and schedules site visits.",
            "system_prompt": (
                "You are a professional real estate assistant for {{company_name}}. "
                "Help callers with property inquiries, pricing, and schedule site visits. "
                "Be warm, knowledgeable, and always capture caller name and phone number."
            ),
            "first_message": "Hello! Thank you for calling {{company_name}}. I can help you find your perfect property. Are you looking to buy or rent?",
            "is_system_template": True,
        },
        {
            "category": "Banking & Finance",
            "title": "Loan Inquiry Assistant",
            "description": "Handles loan inquiries, collects basic financial info, and routes to loan officers.",
            "system_prompt": (
                "You are a banking assistant for {{company_name}}. Help callers understand "
                "loan products, EMI calculations, and eligibility. Never ask for sensitive data "
                "like Aadhaar, PAN, or bank passwords over the phone. Route complex cases to a human officer."
            ),
            "first_message": "Welcome to {{company_name}} loan services! How can I help you today? Are you interested in a home loan, personal loan, or business loan?",
            "is_system_template": True,
        },
        {
            "category": "Healthcare",
            "title": "Appointment Booking Assistant",
            "description": "Books doctor appointments, handles rescheduling, and provides clinic information.",
            "system_prompt": (
                "You are a medical receptionist for {{company_name}} clinic. Help patients "
                "book, reschedule, or cancel appointments. Collect patient name, contact, "
                "and reason for visit. Be empathetic and professional."
            ),
            "first_message": "Hello! This is {{company_name}} clinic. I can help you schedule an appointment with one of our doctors. Would you like to book a new appointment?",
            "is_system_template": True,
        },
        {
            "category": "Logistics",
            "title": "Delivery Status Tracker",
            "description": "Provides shipment tracking, handles delivery complaints, and reschedules deliveries.",
            "system_prompt": (
                "You are a logistics support agent for {{company_name}}. Help callers "
                "track their shipments, report delivery issues, and reschedule deliveries. "
                "Always ask for the order ID or tracking number first."
            ),
            "first_message": "Hi! Thank you for calling {{company_name}} delivery support. Could you please share your order ID or tracking number so I can look up your shipment?",
            "is_system_template": True,
        },
    ]

    async with kodewaves_db_client.get_session() as session:
        for t in default_templates:
            stmt = select(PromptTemplateModel).where(PromptTemplateModel.title == t["title"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(PromptTemplateModel(**t))
        await session.commit()
    print("[SUCCESS] Industry Prompt Templates verified.")


def seed_local_ai_model():
    """Pre-pull a lightweight LLM model into Ollama so Local CPU AI is ready to use."""
    import json
    import os
    import urllib.error
    import urllib.request

    endpoint = os.getenv("OLLAMA_ENDPOINT", "http://ollama:11434")
    print(f"[SEED] Pre-pulling lightweight Ollama LLM model (qwen2.5:0.5b) via {endpoint}...")
    try:
        req = urllib.request.Request(
            f"{endpoint}/api/pull",
            data=json.dumps({"name": "qwen2.5:0.5b", "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as response:
            if response.status == 200:
                print("[SUCCESS] Ollama qwen2.5:0.5b model ready for Local CPU inference.")
            else:
                print(f"[WARN] Ollama model pull returned status {response.status}")
    except Exception as e:
        print(f"[WARN] Ollama model pull skipped (will download on first user request): {e}")


async def seed_superadmin_user():
    import os
    admin_email = os.getenv("ADMIN_EMAIL", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    if admin_email and admin_password:
        print(f"[SEED] Ensuring Superadmin account for '{admin_email}'...")
        from scripts.create_superuser import create_or_promote_superuser
        try:
            await create_or_promote_superuser(admin_email, admin_password, name="Super Admin")
            print(f"[SUCCESS] Superadmin '{admin_email}' verified and operational.")
        except Exception as e:
            print(f"[WARN] Superadmin seeding notice: {e}")
    else:
        # Check if at least one superuser exists in the database
        async with db_client.async_session() as session:
            stmt = select(UserModel).where(UserModel.is_superuser == True).limit(1)
            res = await session.execute(stmt)
            existing_super = res.scalar_one_or_none()
            if existing_super:
                print(f"[INFO] Active Superadmin account exists: '{existing_super.email}'")
            else:
                print("[WARN] No Superadmin account found in database and ADMIN_EMAIL/ADMIN_PASSWORD not set in environment.")
                print("[TIP] Run `python -m scripts.create_superuser --email admin@example.com --password secret` to create one.")


async def main():
    print("=================================================================")
    print("🚀 Starting Kodewaves Sovereign Platform Bootstrap Seeder...")
    print("=================================================================")
    await seed_global_settings()
    await seed_saas_plans()
    await seed_credit_packages()
    await seed_ai_model_catalog()
    await seed_banned_words()
    await seed_prompt_templates()
    await seed_wallets_for_existing_orgs()
    await seed_superadmin_user()
    seed_local_ai_model()
    print("=================================================================")
    print("🎉 Sovereign Platform Bootstrap Completed Successfully!")
    print("   ✅ Global Settings, Plans, Packages, Models, Templates, Wallets")
    print("   ✅ Superadmin Privileges, Content Moderation, Prompt Gallery")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(main())

