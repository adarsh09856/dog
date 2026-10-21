from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from api.db import appointments
from api.db.kodewaves_client import kodewaves_db_client


@pytest.fixture
def session(monkeypatch):
    value = NS(execute=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(), add=Mock(), flush=AsyncMock())
    context = AsyncMock()
    context.__aenter__.return_value = value
    monkeypatch.setattr(kodewaves_db_client, "get_session", lambda: context)
    return value


def result(value):
    return Mock(scalar_one_or_none=Mock(return_value=value))


def values(**overrides):
    return {"start_time": datetime(2026, 10, 20, 10, tzinfo=UTC), **overrides}


@pytest.mark.asyncio
async def test_foreign_contact_rejected_without_writes(session):
    session.execute.side_effect = [result(7), result(None), result(None), result(None)]
    with pytest.raises(LookupError, match="Contact not found"):
        await appointments.save_appointment(7, values(contact_id=str(uuid4())))
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    assert session.execute.call_args.args[0].compile().params["organization_id_1"] == 7


@pytest.mark.asyncio
async def test_conflict_rejected_before_contact_or_appointment_is_created(session):
    session.execute.side_effect = [result(7), result(None), result(uuid4())]
    with pytest.raises(FileExistsError, match="conflicts"):
        await appointments.save_appointment(7, values(customer_phone="synthetic"))
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_saved_duration_and_buffer_used_and_organization_locked(session):
    settings = NS(default_duration_minutes=45, buffer_minutes=10, allow_overlapping=False)
    session.execute.side_effect = [result(7), result(settings), result(None)]
    await appointments.save_appointment(7, values())
    appointment = session.add.call_args.args[0]
    assert appointment.end_time - appointment.start_time == timedelta(minutes=45)
    assert "FOR UPDATE" in str(session.execute.call_args_list[0].args[0])
    params = session.execute.call_args_list[2].args[0].compile().params
    assert params["start_time_1"] == values()["start_time"] + timedelta(minutes=55)
    assert params["end_time_1"] == values()["start_time"] - timedelta(minutes=10)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reversed_interval_rejected(session):
    session.execute.side_effect = [result(7), result(None)]
    with pytest.raises(ValueError, match="after start"):
        await appointments.save_appointment(7, values(end_time=values()["start_time"] - timedelta(minutes=1)))
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_start_preserves_duration_and_contact(session):
    appointment = NS(id=uuid4(), start_time=datetime(2026, 10, 19, 10, tzinfo=UTC),
                     end_time=datetime(2026, 10, 19, 11, tzinfo=UTC), contact_id=uuid4(),
                     title="Original", status="confirmed", notes="Keep")
    contact_id = appointment.contact_id
    session.execute.side_effect = [result(7), result(appointment), result(None), result(None)]
    await appointments.save_appointment(7, values(), str(appointment.id))
    assert appointment.end_time == values()["start_time"] + timedelta(hours=1)
    assert appointment.contact_id == contact_id
    assert appointment.title == "Original"
    assert appointment.notes == "Keep"


@pytest.mark.asyncio
async def test_foreign_appointment_cannot_be_updated(session):
    session.execute.side_effect = [result(7), result(None)]
    with pytest.raises(LookupError, match="Appointment not found"):
        await appointments.save_appointment(7, values(), str(uuid4()))
    assert session.execute.call_args.args[0].compile().params["organization_id_1"] == 7
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_customer_details_updates_the_existing_scoped_contact(session):
    contact = NS(id=uuid4(), first_name="Old", last_name="Name", phone="+919000000001", email="old@example.test")
    appointment = NS(id=uuid4(), start_time=values()["start_time"],
                     end_time=values()["start_time"] + timedelta(hours=1),
                     contact_id=contact.id, title="Original", status="confirmed", notes=None)
    session.execute.side_effect = [result(7), result(appointment), result(None), result(None), result(contact)]
    await appointments.save_appointment(7, values(
        contact_id=str(contact.id), customer_name="New Customer", customer_phone="+919000000002",
        customer_email="new@example.test",
    ), str(appointment.id))
    assert (contact.first_name, contact.last_name) == ("New", "Customer")
    assert contact.phone == "+919000000002"
    assert contact.email == "new@example.test"
    assert appointment.contact_id == contact.id
    assert session.execute.call_args.args[0].compile().params["organization_id_1"] == 7
    session.add.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_customer_edit_survives_database_reload(db_session, async_session):
    from api.db.models import OrganizationModel
    from api.db.kodewaves_models import ContactModel

    org = OrganizationModel(provider_id=f"appointment-customer-edit-{uuid4()}")
    async_session.add(org)
    await async_session.flush()
    contact = ContactModel(organization_id=org.id, first_name="Old", last_name="Name", phone="+919000000001")
    async_session.add(contact)
    await async_session.flush()
    saved = await appointments.save_appointment(org.id, values(contact_id=str(contact.id)))
    await appointments.save_appointment(org.id, values(
        contact_id=str(contact.id), customer_name="Updated Customer", customer_phone="+919000000002",
        customer_email="updated@example.test",
    ), saved["id"])
    rows = await appointments.list_appointments(org.id)
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "Updated Customer"
    assert rows[0]["customer_phone"] == "+919000000002"
    assert rows[0]["customer_email"] == "updated@example.test"
    assert rows[0]["contact_id"] == str(contact.id)


def test_request_rejects_timezone_free_times_and_invalid_status():
    from pydantic import ValidationError
    from api.routes.appointments import AppointmentCreateRequest, AppointmentSettingsItem

    with pytest.raises(ValidationError, match="timezone"):
        AppointmentCreateRequest(start_time="2026-10-20T10:00:00")
    with pytest.raises(ValidationError, match="Invalid appointment status"):
        AppointmentCreateRequest(start_time="2026-10-20T10:00:00Z", status="invented")
    with pytest.raises(ValidationError):
        AppointmentSettingsItem(default_duration_minutes=0)
    with pytest.raises(ValidationError):
        AppointmentSettingsItem(buffer_minutes=-1)
    assert AppointmentCreateRequest(start_time="2026-10-20T10:00:00Z", status="pending").status == "pending"


@pytest.mark.asyncio
async def test_route_reports_conflict_as_failure(monkeypatch):
    from fastapi import HTTPException
    from api.routes.appointments import AppointmentCreateRequest, create_appointment

    monkeypatch.setattr(appointments, "save_appointment", AsyncMock(side_effect=FileExistsError("Time unavailable")))
    with pytest.raises(HTTPException) as error:
        await create_appointment(AppointmentCreateRequest(start_time="2026-10-20T10:00:00Z"), NS(selected_organization_id=7))
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_route_returns_actual_persisted_id(monkeypatch):
    from api.routes.appointments import AppointmentCreateRequest, create_appointment

    saved_id = str(uuid4())
    save = AsyncMock(return_value={"id": saved_id, "status": "confirmed"})
    monkeypatch.setattr(appointments, "save_appointment", save)
    reply = await create_appointment(AppointmentCreateRequest(start_time="2026-10-20T10:00:00Z"), NS(selected_organization_id=7))
    assert reply["id"] == saved_id
    assert save.call_args.args[0] == 7
