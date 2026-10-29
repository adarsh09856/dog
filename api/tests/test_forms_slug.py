"""Form slugs persist, resolve within a workspace, and remain unique there."""

import importlib.util
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import UniqueConstraint

from api.db.kodewaves_models import FormModel
from api.routes import forms
from api.services import forms as form_service


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeResult(self.results.pop(0))

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, value):
        if value.id is None:
            value.id = uuid.uuid4()

    async def rollback(self):
        return None


def _user(org_id):
    return SimpleNamespace(selected_organization_id=org_id, id=7)


def _session_factory(monkeypatch, session):
    monkeypatch.setattr(forms.kodewaves_db_client, "get_session", lambda: session)


def _statement_values(statement):
    return statement.compile().params


@pytest.mark.asyncio
async def test_create_form_persists_normalized_custom_slug(monkeypatch):
    session = FakeSession([None])
    _session_factory(monkeypatch, session)

    response = await forms.create_form(
        forms.FormCreateRequest(title="Customer Intake", slug=" Customer_Intake "),
        _user(11),
    )

    assert response["name"] == "Customer Intake"
    assert session.added[0].slug == "customer-intake"
    assert session.commits == 1
    assert _statement_values(session.statements[0])["organization_id_1"] == 11
    assert _statement_values(session.statements[0])["slug_1"] == "customer-intake"


@pytest.mark.asyncio
async def test_duplicate_slug_is_rejected_only_within_same_workspace(monkeypatch):
    conflict = SimpleNamespace(id=uuid.uuid4())
    session = FakeSession([conflict])
    _session_factory(monkeypatch, session)

    with pytest.raises(HTTPException) as error:
        await forms.create_form(
            forms.FormCreateRequest(title="Different form", slug="customer-intake"),
            _user(11),
        )

    assert error.value.status_code == 409
    assert session.added == []

    other_workspace = FakeSession([None])
    _session_factory(monkeypatch, other_workspace)
    response = await forms.create_form(
        forms.FormCreateRequest(title="Their intake", slug="customer-intake"),
        _user(12),
    )
    assert response["name"] == "Their intake"
    assert other_workspace.added[0].slug == "customer-intake"


@pytest.mark.asyncio
async def test_get_form_resolves_slug_scoped_to_workspace(monkeypatch):
    form = SimpleNamespace(
        id=uuid.uuid4(),
        name="Customer Intake",
        slug="customer-intake",
        description=None,
        fields_schema=[],
        is_active=True,
        created_at=None,
    )
    session = FakeSession([form, 0])
    _session_factory(monkeypatch, session)

    response = await forms.get_form("customer-intake", _user(11))

    assert response.slug == "customer-intake"
    values = _statement_values(session.statements[0])
    assert 11 in values.values()
    assert "customer-intake" in values.values()


@pytest.mark.asyncio
async def test_update_form_persists_new_slug_and_rejects_collision(monkeypatch):
    form = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=11,
        name="Customer Intake",
        slug="customer-intake",
        description=None,
        fields_schema=[],
        is_active=True,
    )
    session = FakeSession([form, None])
    _session_factory(monkeypatch, session)

    await forms.update_form(
        str(form.id),
        forms.FormCreateRequest(title="Customer Intake", slug="intake-v2"),
        _user(11),
    )
    assert form.slug == "intake-v2"
    assert session.commits == 1

    conflict = SimpleNamespace(id=uuid.uuid4())
    collision_session = FakeSession([form, conflict])
    _session_factory(monkeypatch, collision_session)
    with pytest.raises(HTTPException) as error:
        await forms.update_form(
            str(form.id),
            forms.FormCreateRequest(title="Customer Intake", slug="already-used"),
            _user(11),
        )
    assert error.value.status_code == 409
    assert collision_session.commits == 0


@pytest.mark.asyncio
async def test_slug_lookup_does_not_cross_workspace_boundary(monkeypatch):
    session = FakeSession([None, None])
    _session_factory(monkeypatch, session)

    with pytest.raises(HTTPException) as error:
        await forms.get_form("customer-intake", _user(12))

    assert error.value.status_code == 404
    assert 12 in _statement_values(session.statements[0]).values()


def test_form_slug_has_database_workspace_unique_constraint():
    assert any(
        isinstance(constraint, UniqueConstraint)
        and set(constraint.columns.keys()) == {"organization_id", "slug"}
        for constraint in FormModel.__table__.constraints
    )


def test_migration_backfills_duplicate_names_with_workspace_unique_slugs():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "f0a1b2c3d4e5_add_workspace_unique_form_slugs.py"
    )
    spec = importlib.util.spec_from_file_location("form_slug_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    form_id = uuid.uuid4()

    rows = migration._backfill_rows(
        [
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "organization_id": 11,
                "name": "Customer Intake",
            },
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
                "organization_id": 11,
                "name": "Customer Intake",
            },
            {"id": form_id, "organization_id": 12, "name": "Customer Intake"},
        ]
    )

    assert rows[0]["slug"] == "customer-intake"
    assert rows[1]["slug"] == "customer-intake-00000000"
    assert rows[2]["slug"] == "customer-intake"


@pytest.mark.asyncio
async def test_submit_resolves_workspace_slug_to_persisted_form_id(monkeypatch):
    form_id = uuid.uuid4()
    form = SimpleNamespace(
        id=form_id,
        is_active=True,
        fields_schema=[{"name": "email", "type": "email", "required": True}],
    )
    submitted = {}

    async def get_form(organization_id, form_identifier):
        assert organization_id == 11
        assert form_identifier == "customer-intake"
        return form

    async def create_submission(organization_id, resolved_form_id, data, **kwargs):
        submitted.update(
            organization_id=organization_id,
            form_id=resolved_form_id,
            data=data,
            kwargs=kwargs,
        )
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(form_service.form_db, "get_form", get_form)
    monkeypatch.setattr(form_service.form_db, "create_submission", create_submission)

    await form_service.submit_answers(
        11,
        "customer-intake",
        {"email": "user@example.com"},
    )

    assert submitted["form_id"] == form_id
    assert submitted["data"] == {"email": "user@example.com"}
