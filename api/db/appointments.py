"""Organization-scoped appointment persistence shared by pages and agent tools."""

import uuid
from datetime import timedelta

from sqlalchemy import and_, desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    AppointmentModel,
    AppointmentSettingsModel,
    ContactModel,
)
from api.db.models import OrganizationModel


def appointment_data(appointment, contact=None):
    name = None
    if contact:
        name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None
    return {
        "id": str(appointment.id),
        "contact_id": str(appointment.contact_id) if appointment.contact_id else None,
        "title": appointment.title,
        "customer_name": name or appointment.title,
        "customer_phone": contact.phone if contact else "",
        "customer_email": contact.email if contact else None,
        "start_time": appointment.start_time.isoformat(),
        "end_time": appointment.end_time.isoformat(),
        "status": appointment.status,
        "notes": appointment.notes,
    }


async def list_appointments(organization_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(AppointmentModel, ContactModel)
            .outerjoin(
                ContactModel,
                and_(
                    AppointmentModel.contact_id == ContactModel.id,
                    ContactModel.organization_id == organization_id,
                ),
            )
            .where(AppointmentModel.organization_id == organization_id)
            .order_by(desc(AppointmentModel.start_time))
            .limit(100)
        )
        return [
            appointment_data(appointment, contact)
            for appointment, contact in result.all()
        ]


async def _lock_organization(session, organization_id):
    # Serialize calendar mutations even before a settings row exists. This also
    # prevents two simultaneous calls from both passing the overlap check.
    result = await session.execute(
        select(OrganizationModel.id)
        .where(
            OrganizationModel.id == organization_id,
        )
        .with_for_update()
    )
    if result.scalar_one_or_none() is None:
        raise LookupError("Organization not found")


async def save_appointment(organization_id, values, appointment_id=None):
    async with kodewaves_db_client.get_session() as session:
        await _lock_organization(session, organization_id)
        appointment = None
        if appointment_id:
            result = await session.execute(
                select(AppointmentModel).where(
                    AppointmentModel.id == uuid.UUID(appointment_id),
                    AppointmentModel.organization_id == organization_id,
                )
            )
            appointment = result.scalar_one_or_none()
            if appointment is None:
                raise LookupError("Appointment not found")

        result = await session.execute(
            select(AppointmentSettingsModel).where(
                AppointmentSettingsModel.organization_id == organization_id,
            )
        )
        settings = result.scalar_one_or_none()
        start = values["start_time"]
        duration = settings.default_duration_minutes if settings else 30
        end = values.get("end_time")
        if end is None:
            # Editing the start without an end preserves the existing duration.
            end = start + (
                appointment.end_time - appointment.start_time
                if appointment
                else timedelta(minutes=duration)
            )
        if end <= start:
            raise ValueError("Appointment end must be after start")
        status = values.get("status") or (
            appointment.status if appointment else "confirmed"
        )
        if status in {"scheduled", "pending", "confirmed"} and not (
            settings and settings.allow_overlapping
        ):
            buffer = timedelta(minutes=settings.buffer_minutes if settings else 15)
            query = select(AppointmentModel.id).where(
                AppointmentModel.organization_id == organization_id,
                AppointmentModel.status.in_(["scheduled", "pending", "confirmed"]),
                AppointmentModel.start_time < end + buffer,
                AppointmentModel.end_time > start - buffer,
            )
            if appointment:
                query = query.where(AppointmentModel.id != appointment.id)
            result = await session.execute(query.limit(1))
            if result.scalar_one_or_none() is not None:
                raise FileExistsError(
                    "Requested time conflicts with an existing appointment or its buffer"
                )

        contact_id = appointment.contact_id if appointment else None
        if values.get("contact_id"):
            contact_id = uuid.UUID(values["contact_id"])
            result = await session.execute(
                select(ContactModel.id).where(
                    ContactModel.id == contact_id,
                    ContactModel.organization_id == organization_id,
                )
            )
            if result.scalar_one_or_none() is None:
                raise LookupError("Contact not found")
        elif "contact_id" in values:
            contact_id = None
        if not values.get("contact_id") and values.get("customer_phone"):
            result = await session.execute(
                select(ContactModel)
                .where(
                    ContactModel.organization_id == organization_id,
                    ContactModel.phone == values["customer_phone"].strip(),
                )
                .limit(1)
            )
            contact = result.scalar_one_or_none()
            if contact is None:
                contact = ContactModel(
                    organization_id=organization_id,
                    first_name=values.get("customer_name") or "New Lead",
                    phone=values["customer_phone"].strip(),
                    email=values.get("customer_email"),
                )
                session.add(contact)
                await session.flush()
            contact_id = contact.id
        if appointment is None:
            appointment = AppointmentModel(organization_id=organization_id)
            session.add(appointment)
        appointment.contact_id = contact_id
        appointment.start_time = start
        appointment.end_time = end
        appointment.status = status
        if "title" in values or not appointment.title:
            appointment.title = values.get("title") or "Consultation"
        if "notes" in values:
            appointment.notes = values["notes"]
        await session.commit()
        await session.refresh(appointment)
        return {"id": str(appointment.id), "status": appointment.status}


async def delete_appointment(organization_id, appointment_id):
    async with kodewaves_db_client.get_session() as session:
        await _lock_organization(session, organization_id)
        result = await session.execute(
            select(AppointmentModel).where(
                AppointmentModel.id == uuid.UUID(appointment_id),
                AppointmentModel.organization_id == organization_id,
            )
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise LookupError("Appointment not found")
        await session.delete(appointment)
        await session.commit()


async def get_settings(organization_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(AppointmentSettingsModel).where(
                AppointmentSettingsModel.organization_id == organization_id,
            )
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            return {}
        return {
            field: getattr(settings, field)
            for field in (
                "buffer_minutes",
                "default_duration_minutes",
                "working_hours",
                "allow_overlapping",
            )
        }


async def save_settings(organization_id, values):
    async with kodewaves_db_client.get_session() as session:
        await _lock_organization(session, organization_id)
        result = await session.execute(
            select(AppointmentSettingsModel).where(
                AppointmentSettingsModel.organization_id == organization_id,
            )
        )
        settings = result.scalar_one_or_none()
        if settings is None:
            settings = AppointmentSettingsModel(organization_id=organization_id)
            session.add(settings)
        for key, value in values.items():
            setattr(settings, key, value)
        await session.commit()
