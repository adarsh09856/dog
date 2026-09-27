import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AppointmentModel, AppointmentSettingsModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentItem(BaseModel):
    id: str
    contact_id: Optional[str] = None
    title: str
    start_time: str
    end_time: str
    status: str
    notes: Optional[str] = None


class AppointmentCreateRequest(BaseModel):
    contact_id: Optional[str] = None
    title: str
    start_time: str
    end_time: str
    notes: Optional[str] = None


class AppointmentSettingsItem(BaseModel):
    buffer_minutes: int = 15
    default_duration_minutes: int = 30
    working_hours: Dict[str, Any] = {}
    allow_overlapping: bool = False


@router.get("", response_model=List[AppointmentItem])
async def list_appointments(user: UserModel = Depends(get_user)):
    """List appointments for the organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(AppointmentModel)
            .where(AppointmentModel.organization_id == org_id)
            .order_by(desc(AppointmentModel.start_time))
            .limit(100)
        )
        result = await session.execute(stmt)
        appts = result.scalars().all()
        return [
            AppointmentItem(
                id=str(a.id),
                contact_id=str(a.contact_id) if a.contact_id else None,
                title=a.title,
                start_time=a.start_time.isoformat(),
                end_time=a.end_time.isoformat(),
                status=a.status,
                notes=a.notes,
            )
            for a in appts
        ]


@router.post("", response_model=Dict[str, Any])
async def create_appointment(req: AppointmentCreateRequest, user: UserModel = Depends(get_user)):
    """Book an appointment (called by voice agents or users)."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        appt = AppointmentModel(
            organization_id=org_id,
            contact_id=uuid.UUID(req.contact_id) if req.contact_id else None,
            title=req.title,
            start_time=datetime.fromisoformat(req.start_time),
            end_time=datetime.fromisoformat(req.end_time),
            notes=req.notes,
        )
        session.add(appt)
        await session.commit()
        return {"id": str(appt.id), "status": "scheduled", "message": "Appointment booked successfully"}


@router.get("/settings", response_model=AppointmentSettingsItem)
async def get_settings(user: UserModel = Depends(get_user)):
    """Get appointment calendar settings."""
    org_id = user.selected_organization_id
    if not org_id:
        return AppointmentSettingsItem()

    async with kodewaves_db_client.get_session() as session:
        stmt = select(AppointmentSettingsModel).where(AppointmentSettingsModel.organization_id == org_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return AppointmentSettingsItem()

        return AppointmentSettingsItem(
            buffer_minutes=record.buffer_minutes,
            default_duration_minutes=record.default_duration_minutes,
            working_hours=record.working_hours or {},
            allow_overlapping=record.allow_overlapping,
        )
