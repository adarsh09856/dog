from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.db import appointments as appointment_db
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentItem(BaseModel):
    id: str
    contact_id: str | None = None
    title: str
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_email: str | None = None
    start_time: str
    end_time: str
    status: str = "scheduled"
    notes: str | None = None


class AppointmentCreateRequest(BaseModel):
    contact_id: str | None = None
    title: str | None = Field(default="Consultation", max_length=200)
    customer_name: str | None = Field(default=None, max_length=100)
    customer_phone: str | None = Field(default=None, max_length=30)
    customer_email: str | None = Field(default=None, max_length=255)
    start_time: datetime
    end_time: datetime | None = None
    status: str | None = "confirmed"
    notes: str | None = None

    @field_validator("start_time", "end_time")
    @classmethod
    def require_timezone(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Appointment times must include a timezone offset")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in {
            "scheduled",
            "confirmed",
            "completed",
            "cancelled",
        }:
            raise ValueError("Invalid appointment status")
        return value


class AppointmentSettingsItem(BaseModel):
    buffer_minutes: int = Field(default=15, ge=0, le=1440)
    default_duration_minutes: int = Field(default=30, ge=1, le=1440)
    working_hours: dict[str, Any] = Field(default_factory=dict)
    allow_overlapping: bool = False


def organization_id(user):
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="Organization required")
    return user.selected_organization_id


async def persist_appointment(req, user, appointment_id=None):
    try:
        result = await appointment_db.save_appointment(
            organization_id(user),
            req.model_dump(exclude_unset=True),
            appointment_id,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        **result,
        "message": "Appointment updated successfully"
        if appointment_id
        else "Appointment booked successfully",
    }


@router.get("", response_model=list[AppointmentItem])
async def list_appointments(user: UserModel = Depends(get_user)):
    return await appointment_db.list_appointments(organization_id(user))


@router.post("", response_model=dict[str, Any])
async def create_appointment(
    req: AppointmentCreateRequest, user: UserModel = Depends(get_user)
):
    return await persist_appointment(req, user)


@router.put("/{appointment_id}", response_model=dict[str, Any])
async def update_appointment(
    appointment_id: str,
    req: AppointmentCreateRequest,
    user: UserModel = Depends(get_user),
):
    return await persist_appointment(req, user, appointment_id)


@router.delete("/{appointment_id}", response_model=dict[str, Any])
async def delete_appointment(appointment_id: str, user: UserModel = Depends(get_user)):
    try:
        await appointment_db.delete_appointment(organization_id(user), appointment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid appointment ID format"
        ) from exc
    return {"message": "Appointment deleted successfully"}


@router.get("/settings", response_model=AppointmentSettingsItem)
async def get_settings(user: UserModel = Depends(get_user)):
    return AppointmentSettingsItem(
        **await appointment_db.get_settings(organization_id(user))
    )


@router.post("/settings", response_model=dict[str, Any])
async def update_settings(
    req: AppointmentSettingsItem, user: UserModel = Depends(get_user)
):
    try:
        await appointment_db.save_settings(organization_id(user), req.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": "Calendar settings updated successfully"}
