from datetime import datetime, timedelta, UTC
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AppointmentModel, AppointmentSettingsModel, ContactModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentItem(BaseModel):
    id: str
    contact_id: Optional[str] = None
    title: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    start_time: str
    end_time: str
    status: str = "scheduled"
    notes: Optional[str] = None


class AppointmentCreateRequest(BaseModel):
    contact_id: Optional[str] = None
    title: Optional[str] = "Consultation"
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    status: Optional[str] = "confirmed"
    notes: Optional[str] = None


class AppointmentSettingsItem(BaseModel):
    buffer_minutes: int = 15
    default_duration_minutes: int = 30
    working_hours: Dict[str, Any] = {}
    allow_overlapping: bool = False


@router.get("", response_model=List[AppointmentItem])
async def list_appointments(user: UserModel = Depends(get_user)):
    """List appointments for the organization with contact metadata."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(AppointmentModel, ContactModel)
            .outerjoin(ContactModel, AppointmentModel.contact_id == ContactModel.id)
            .where(AppointmentModel.organization_id == org_id)
            .order_by(desc(AppointmentModel.start_time))
            .limit(100)
        )
        result = await session.execute(stmt)
        rows = result.all()
        items = []
        for appt, contact in rows:
            cust_name = None
            cust_phone = None
            cust_email = None
            if contact:
                cust_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None
                cust_phone = contact.phone
                cust_email = contact.email

            items.append(
                AppointmentItem(
                    id=str(appt.id),
                    contact_id=str(appt.contact_id) if appt.contact_id else None,
                    title=appt.title,
                    customer_name=cust_name or appt.title,
                    customer_phone=cust_phone or "",
                    customer_email=cust_email,
                    start_time=appt.start_time.isoformat(),
                    end_time=appt.end_time.isoformat() if appt.end_time else appt.start_time.isoformat(),
                    status=appt.status,
                    notes=appt.notes,
                )
            )
        return items


@router.post("", response_model=Dict[str, Any])
async def create_appointment(req: AppointmentCreateRequest, user: UserModel = Depends(get_user)):
    """Book an appointment (called by voice agents or users)."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        # Determine contact_id or create contact if customer details are provided
        target_contact_id = None
        if req.contact_id:
            try:
                target_contact_id = uuid.UUID(req.contact_id)
            except ValueError:
                pass
        elif req.customer_phone:
            # Look up contact by phone
            c_stmt = select(ContactModel).where(
                ContactModel.organization_id == org_id,
                ContactModel.phone == req.customer_phone.strip(),
            )
            c_res = await session.execute(c_stmt)
            existing_c = c_res.scalar_one_or_none()
            if existing_c:
                target_contact_id = existing_c.id
            else:
                new_c = ContactModel(
                    organization_id=org_id,
                    first_name=req.customer_name or "New Lead",
                    phone=req.customer_phone.strip(),
                    email=req.customer_email,
                )
                session.add(new_c)
                await session.flush()
                target_contact_id = new_c.id

        start_dt = datetime.fromisoformat(req.start_time)
        if req.end_time:
            end_dt = datetime.fromisoformat(req.end_time)
        else:
            end_dt = start_dt + timedelta(minutes=30)

        title = req.title or (f"Call with {req.customer_name}" if req.customer_name else "Consultation")

        appt = AppointmentModel(
            organization_id=org_id,
            contact_id=target_contact_id,
            title=title,
            start_time=start_dt,
            end_time=end_dt,
            status=req.status or "confirmed",
            notes=req.notes,
        )
        session.add(appt)
        await session.commit()
        await session.refresh(appt)
        return {"id": str(appt.id), "status": appt.status, "message": "Appointment booked successfully"}


@router.put("/{appointment_id}", response_model=Dict[str, Any])
async def update_appointment(appointment_id: str, req: AppointmentCreateRequest, user: UserModel = Depends(get_user)):
    """Update an existing appointment."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            a_uuid = uuid.UUID(appointment_id)
            stmt = select(AppointmentModel).where(AppointmentModel.id == a_uuid, AppointmentModel.organization_id == org_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid appointment ID format")

        result = await session.execute(stmt)
        appt = result.scalar_one_or_none()
        if not appt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        if req.title:
            appt.title = req.title
        if req.status:
            appt.status = req.status
        if req.notes is not None:
            appt.notes = req.notes
        if req.start_time:
            appt.start_time = datetime.fromisoformat(req.start_time)
        if req.end_time:
            appt.end_time = datetime.fromisoformat(req.end_time)

        await session.commit()
        return {"id": str(appt.id), "status": appt.status, "message": "Appointment updated successfully"}


@router.delete("/{appointment_id}", response_model=Dict[str, Any])
async def delete_appointment(appointment_id: str, user: UserModel = Depends(get_user)):
    """Cancel and delete an appointment booking."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            a_uuid = uuid.UUID(appointment_id)
            stmt = select(AppointmentModel).where(AppointmentModel.id == a_uuid, AppointmentModel.organization_id == org_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid appointment ID format")

        result = await session.execute(stmt)
        appt = result.scalar_one_or_none()
        if not appt:
            raise HTTPException(status_code=404, detail="Appointment not found")

        await session.delete(appt)
        await session.commit()
        return {"message": "Appointment deleted successfully"}


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


@router.post("/settings", response_model=Dict[str, Any])
async def update_settings(req: AppointmentSettingsItem, user: UserModel = Depends(get_user)):
    """Update appointment calendar settings."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        stmt = select(AppointmentSettingsModel).where(AppointmentSettingsModel.organization_id == org_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            record = AppointmentSettingsModel(
                organization_id=org_id,
                buffer_minutes=req.buffer_minutes,
                default_duration_minutes=req.default_duration_minutes,
                working_hours=req.working_hours,
                allow_overlapping=req.allow_overlapping,
            )
            session.add(record)
        else:
            record.buffer_minutes = req.buffer_minutes
            record.default_duration_minutes = req.default_duration_minutes
            record.working_hours = req.working_hours
            record.allow_overlapping = req.allow_overlapping

        await session.commit()
        return {"message": "Calendar settings updated successfully"}
