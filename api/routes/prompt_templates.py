import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
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
    recommended_tools: List[str] = []
    tags: List[str] = []
    is_featured: bool = True


class PromptTemplateCreateRequest(BaseModel):
    category: str = "General"
    title: str
    description: str
    system_prompt: str
    first_message: str
    recommended_tools: List[str] = []
    tags: List[str] = []
    is_featured: bool = False


@router.get("", response_model=List[PromptTemplateItem])
async def list_templates(category: Optional[str] = None, _user=Depends(get_user)):
    """List pre-configured voice agent prompt templates."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(PromptTemplateModel)
        if category and category.lower() != "all":
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
                    category="Banking & Finance",
                    title="EMI Reminder & Payment Confirmation",
                    description="Politely reminds customers of upcoming loan/credit card EMI payment due dates and offers instant payment links.",
                    system_prompt="You are a respectful customer service agent from Apex Financial Services. Remind the customer about their upcoming EMI payment date, confirm if they need any assistance, and offer to send an instant UPI payment link via SMS/WhatsApp.",
                    first_message="Hello! This is Apex Finance calling with a friendly reminder regarding your personal loan EMI due on the 5th. Would you like us to share the payment link?",
                    recommended_tools=["crm_lead"],
                ),
                PromptTemplateModel(
                    category="Logistics",
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

            stmt = select(PromptTemplateModel)
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
                tags=[r.category] + (r.recommended_tools or []),
                is_featured=r.is_system_template,
            )
            for r in records
        ]


@router.post("", response_model=Dict[str, Any])
async def create_template(req: PromptTemplateCreateRequest, _user=Depends(get_user)):
    """Create a new prompt template."""
    async with kodewaves_db_client.get_session() as session:
        t = PromptTemplateModel(
            category=req.category,
            title=req.title,
            description=req.description,
            system_prompt=req.system_prompt,
            first_message=req.first_message,
            recommended_tools=req.recommended_tools,
            is_system_template=False,
        )
        session.add(t)
        await session.commit()
        await session.refresh(t)
        return {"id": str(t.id), "title": t.title, "message": "Prompt template created successfully"}


@router.delete("/{template_id}", response_model=Dict[str, Any])
async def delete_template(template_id: str, _user=Depends(get_user)):
    """Delete a prompt template."""
    async with kodewaves_db_client.get_session() as session:
        try:
            t_uuid = uuid.UUID(template_id)
            stmt = select(PromptTemplateModel).where(PromptTemplateModel.id == t_uuid)
        except ValueError:
            stmt = select(PromptTemplateModel).where(PromptTemplateModel.title == template_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Template not found")

        is_super = getattr(_user, "is_superuser", False) or getattr(_user, "role", "") in ("admin", "superadmin")
        if record.is_system_template and not is_super:
            raise HTTPException(status_code=403, detail="Cannot delete a system prompt template")

        await session.delete(record)
        await session.commit()
        return {"message": "Prompt template deleted successfully"}
