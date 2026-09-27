import uuid
from typing import Any, Dict, List, Optional
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import ContactModel, LeadActivityModel, LeadStageModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/crm", tags=["crm"])


class ContactCreateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    stage_id: Optional[str] = None
    tags: List[str] = []
    custom_fields: Dict[str, Any] = {}


class ContactItem(BaseModel):
    id: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone: str
    email: Optional[str]
    company: Optional[str]
    stage_id: Optional[str]
    tags: List[str]
    total_calls: int
    created_at: str


class LeadStageItem(BaseModel):
    id: str
    name: str
    color: str
    order_index: int


@router.get("/stages", response_model=List[LeadStageItem])
async def list_stages(user: UserModel = Depends(get_user)):
    """List pipeline lead stages for current organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = select(LeadStageModel).where(LeadStageModel.organization_id == org_id).order_by(LeadStageModel.order_index)
        result = await session.execute(stmt)
        stages = result.scalars().all()

        # Seed default stages if none exist
        if not stages:
            defaults = [
                ("New Lead", "#3b82f6", 0),
                ("Contacted", "#eab308", 1),
                ("Qualified", "#a855f7", 2),
                ("Follow-Up", "#f97316", 3),
                ("Closed Won", "#22c55e", 4),
                ("Lost", "#ef4444", 5),
            ]
            for name, color, idx in defaults:
                s = LeadStageModel(organization_id=org_id, name=name, color=color, order_index=idx)
                session.add(s)
            await session.commit()

            stmt = select(LeadStageModel).where(LeadStageModel.organization_id == org_id).order_by(LeadStageModel.order_index)
            result = await session.execute(stmt)
            stages = result.scalars().all()

        return [
            LeadStageItem(id=str(s.id), name=s.name, color=s.color, order_index=s.order_index)
            for s in stages
        ]


@router.get("/contacts", response_model=List[ContactItem])
async def list_contacts(user: UserModel = Depends(get_user)):
    """List CRM contacts for organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = select(ContactModel).where(ContactModel.organization_id == org_id).order_by(desc(ContactModel.created_at)).limit(100)
        result = await session.execute(stmt)
        contacts = result.scalars().all()
        return [
            ContactItem(
                id=str(c.id),
                first_name=c.first_name,
                last_name=c.last_name,
                phone=c.phone,
                email=c.email,
                company=c.company,
                stage_id=str(c.stage_id) if c.stage_id else None,
                tags=c.tags or [],
                total_calls=c.total_calls,
                created_at=c.created_at.isoformat() if c.created_at else "",
            )
            for c in contacts
        ]


@router.post("/contacts", response_model=Dict[str, Any])
async def create_contact(req: ContactCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new contact."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        contact = ContactModel(
            organization_id=org_id,
            first_name=req.first_name,
            last_name=req.last_name,
            phone=req.phone,
            email=req.email,
            company=req.company,
            stage_id=uuid.UUID(req.stage_id) if req.stage_id else None,
            tags=req.tags,
            custom_fields=req.custom_fields,
        )
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return {"id": str(contact.id), "phone": contact.phone, "message": "Contact created successfully"}
