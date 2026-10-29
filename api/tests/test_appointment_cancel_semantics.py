"""Cancelling a calendar booking preserves the workspace audit record."""

import uuid
from types import SimpleNamespace

import pytest

from api.db import appointments


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, appointment):
        self.appointment = appointment
        self.committed = False
        self.deleted = False
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.appointment)

    async def commit(self):
        self.committed = True

    async def delete(self, _value):
        self.deleted = True


@pytest.mark.asyncio
async def test_cancel_marks_appointment_cancelled_without_deleting_history(monkeypatch):
    appointment_id = uuid.uuid4()
    appointment = SimpleNamespace(id=appointment_id, status="confirmed")
    session = _Session(appointment)
    monkeypatch.setattr(appointments.kodewaves_db_client, "get_session", lambda: session)

    await appointments.delete_appointment(organization_id=42, appointment_id=str(appointment_id))

    assert appointment.status == "cancelled"
    assert session.committed
    assert not session.deleted
