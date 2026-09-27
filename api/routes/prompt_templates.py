from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import PromptTemplateModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


class PromptTemplateItem(BaseModel):
    id: str
    category: str
    title: str
    description: str
    system_prompt: str
    first_message: str
    recommended_tools: List[str]


@router.get("", response_model=List[PromptTemplateItem])
async def list_templates(category: Optional[str] = None, _user=Depends(get_user)):
    """List pre-configured voice agent prompt templates."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(PromptTemplateModel).where(PromptTemplateModel.is_system_template == True)
        if category:
            stmt = stmt.where(PromptTemplateModel.category == category)
        result = await session.execute(stmt)
        records = result.scalars().all()

        # Seed initial Indian and global industry templates if empty
        if not records:
            defaults = [
                PromptTemplateModel(
                    category="Real Estate",
                    title="Property Inquiry & Site Visit Scheduler",
                    description="Qualifies real estate leads in India, checks budget, preferred BHK, location, and books site visits.",
                    system_prompt="You are a professional real estate sales consultant for luxury apartments in India. Speak warmly, respectfully, and clearly in English or Hindi. Gather buyer preferences: 2BHK/3BHK, budget in Lakhs/Crores, possession timeline, and offer a weekend site visit booking.",
                    first_message="Namaste! Thank you for inquiring about our luxury residential project. May I know what type of configuration you are looking for—2BHK or 3BHK?",
                    recommended_tools=["google_calendar", "crm_lead"],
                ),
                PromptTemplateModel(
                    category="Healthcare",
                    title="Clinic & Diagnostic Appointment Booking",
                    description="Handles patient inquiries, identifies symptoms/department, and schedules doctor consultations.",
                    system_prompt="You are a polite, empathetic hospital appointment coordinator. Assist patients in selecting the appropriate specialist (General Medicine, Cardiology, Orthopedics) and confirming consultation timings.",
                    first_message="Hello, welcome to City Care Hospital. How may I assist with your doctor consultation or health checkup booking today?",
                    recommended_tools=["google_calendar"],
                ),
                PromptTemplateModel(
                    category="Banking & Collections",
                    title="EMI Reminder & Payment Confirmation",
                    description="Politely reminds customers of upcoming loan/credit card EMI payment due dates and offers instant payment links.",
                    system_prompt="You are a respectful customer service agent from Apex Financial Services. Remind the customer about their upcoming EMI payment date, confirm if they need any assistance, and offer to send an instant UPI payment link via SMS/WhatsApp.",
                    first_message="Hello! This is Apex Finance calling with a friendly reminder regarding your personal loan EMI due on the 5th. Would you like us to share the payment link?",
                    recommended_tools=["crm_lead"],
                ),
                PromptTemplateModel(
                    category="E-commerce",
                    title="Order Confirmation & Return Assistant",
                    description="Confirms cash-on-delivery (COD) orders, verifies shipping address, and assists with return requests.",
                    system_prompt="You are an enthusiastic e-commerce logistics representative. Confirm delivery addresses for Cash-on-Delivery orders to avoid RTO returns. Speak clearly and politely.",
                    first_message="Hi! Calling to confirm your recent Cash on Delivery order. Can you please confirm if your delivery pincode and address are correct?",
                    recommended_tools=["forms"],
                ),
            ]
            for t in defaults:
                session.add(t)
            await session.commit()

            stmt = select(PromptTemplateModel).where(PromptTemplateModel.is_system_template == True)
            result = await session.execute(stmt)
            records = result.scalars().all()

        return [
            PromptTemplateItem(
                id=str(r.id),
                category=r.category,
                title=r.title,
                description=r.description,
                system_prompt=r.system_prompt,
                first_message=r.first_message,
                recommended_tools=r.recommended_tools or [],
            )
            for r in records
        ]
