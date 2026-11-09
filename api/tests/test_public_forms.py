import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Response

from api.db import forms as forms_db
from api.db.kodewaves_models import FormModel
from api.routes import public_forms
from api.services import forms as forms_service
from api.services.auth import depends as auth_dependencies
from api.services import saas_entitlements


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, form):
        self.form = form
        self.statement = None
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, statement):
        self.statement = statement
        filters = {
            criterion.left.name: criterion.right.value
            for criterion in statement._where_criteria
            if hasattr(criterion, "left") and hasattr(criterion.right, "value")
        }
        if (
            self.form is not None
            and filters.get("id") == self.form.id
            and filters.get("organization_id") == self.form.organization_id
        ):
            return _Result(self.form)
        return _Result(None)

    async def commit(self):
        self.commits += 1


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


def _form(*, org_id=23):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Website contact",
        slug="website-contact",
        fields_schema=[
            {"name": "name", "label": "Name", "type": "text", "required": True},
            {"name": "email", "label": "Email", "type": "email", "required": True},
        ],
        is_active=True,
        public_submission_enabled=False,
        public_token_hash=None,
        public_allowed_origins=[],
    )


def _request(form_id, body, *, token, origin=None, content_type="application/json", client_ip="198.51.100.44"):
    body_bytes = body if isinstance(body, bytes) else json.dumps(body).encode()
    headers = [(b"content-type", content_type.encode()), (b"x-form-token", token.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": f"/api/v1/public/forms/{form_id}/submit",
        "raw_path": f"/api/v1/public/forms/{form_id}/submit".encode(),
        "query_string": b"",
        "headers": headers,
        "client": (client_ip, 12345),
        "server": ("api.example.test", 443),
    }
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    from starlette.requests import Request

    return Request(scope, receive)


def test_origin_normalization_rejects_paths_credentials_and_wildcards():
    assert public_forms.normalize_origin("HTTPS://Example.COM:443/") == "https://example.com"
    assert public_forms.normalize_origin("http://Example.com:8080") == "http://example.com:8080"
    for invalid in (
        "https://example.com/path",
        "https://user:password@example.com",
        "https://*.example.com",
        "file:///tmp",
    ):
        with pytest.raises(ValueError):
            public_forms.normalize_origin(invalid)


def test_public_submission_rejects_extra_fields_oversize_values_and_nested_data():
    with pytest.raises(Exception):
        public_forms.PublicSubmissionRequest.model_validate(
            {"data": {"name": "A"}, "call_id": 12}
        )
    with pytest.raises(Exception):
        public_forms.PublicSubmissionRequest.model_validate(
            {"data": {"name": "x" * (public_forms.MAX_PUBLIC_FORM_VALUE_BYTES + 1)}}
        )
    with pytest.raises(Exception):
        public_forms.PublicSubmissionRequest.model_validate({"data": {"array": ["x"]}})


@pytest.mark.asyncio
async def test_public_submission_enforces_streaming_body_limit():
    from fastapi import HTTPException

    request = _request(
        uuid.uuid4(),
        b"{" + b" " * public_forms.MAX_PUBLIC_FORM_BODY_BYTES,
        token="token",
    )
    with pytest.raises(HTTPException) as error:
        await public_forms._read_bounded_json(request)
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_public_answers_reject_unknown_fields_before_persisting(monkeypatch):
    form = _form()
    save_submission = AsyncMock()
    monkeypatch.setattr(forms_service.form_db, "create_public_submission", save_submission)

    with pytest.raises(ValueError, match="unknown field"):
        await forms_service.submit_public_answers(
            form,
            "token-hash",
            {"name": "Aditi", "email": "a@example.com", "tenant_id": 23},
        )
    save_submission.assert_not_awaited()


def test_rotation_is_rejected_when_publication_is_disabled():
    with pytest.raises(Exception):
        public_forms.PublicFormAccessRequest(
            enabled=False,
            rotate_token=True,
        )


def test_publication_requires_an_allowed_origin_for_browser_submissions():
    with pytest.raises(Exception, match="at least one allowed website origin"):
        public_forms.PublicFormAccessRequest(enabled=True, allowed_origins=[])
    assert public_forms.PublicFormAccessRequest(enabled=False, allowed_origins=[])


def test_originless_public_forms_do_not_accept_browser_origins():
    form = _form()
    assert public_forms._origin_is_allowed(form, None)
    assert not public_forms._origin_is_allowed(form, "https://shop.example.com")


@pytest.mark.asyncio
async def test_owner_publish_rotate_and_disable_are_org_scoped_and_token_is_one_time(monkeypatch):
    form = _form(org_id=23)
    session = _Session(form)
    monkeypatch.setattr(
        forms_db.kodewaves_db_client,
        "get_session",
        _SessionFactory(session),
    )
    owner = SimpleNamespace(selected_organization_id=23)

    first = await public_forms.set_public_form_access(
        str(form.id),
        public_forms.PublicFormAccessRequest(
            enabled=True, allowed_origins=["https://shop.example.com"]
        ),
        response=Response(),
        user=owner,
    )
    assert first.enabled is True
    assert first.token_configured is True
    assert first.submission_token
    assert form.public_token_hash == public_forms.hash_public_token(first.submission_token)
    assert first.submission_token not in form.public_token_hash
    assert "organization_id" in str(session.statement)
    assert session.statement._for_update_arg is not None

    second = await public_forms.set_public_form_access(
        str(form.id),
        public_forms.PublicFormAccessRequest(
            enabled=True,
            allowed_origins=["https://shop.example.com"],
            rotate_token=True,
        ),
        response=Response(),
        user=owner,
    )
    assert second.submission_token
    assert second.submission_token != first.submission_token
    assert form.public_token_hash == public_forms.hash_public_token(second.submission_token)

    disabled = await public_forms.set_public_form_access(
        str(form.id),
        public_forms.PublicFormAccessRequest(enabled=False),
        response=Response(),
        user=owner,
    )
    assert disabled.enabled is False
    assert disabled.submission_token is None
    assert form.public_token_hash is None


@pytest.mark.asyncio
async def test_publish_denies_cross_organization_form_lookup(monkeypatch):
    form = _form(org_id=23)
    session = _Session(form)
    monkeypatch.setattr(
        forms_db.kodewaves_db_client,
        "get_session",
        _SessionFactory(session),
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await public_forms.set_public_form_access(
            str(form.id),
            public_forms.PublicFormAccessRequest(
                enabled=True, allowed_origins=["https://shop.example.com"]
            ),
            response=Response(),
            user=SimpleNamespace(selected_organization_id=999),
        )
    assert error.value.status_code == 404
    assert form.public_token_hash is None


@pytest.mark.asyncio
async def test_public_submit_accepts_valid_token_and_hides_tenant_identifiers(monkeypatch):
    form = _form()
    token = "valid-one-time-token"
    token_hash = public_forms.hash_public_token(token)
    form.public_submission_enabled = True
    form.public_token_hash = token_hash
    form.public_allowed_origins = ["https://shop.example.com"]
    get_public_form = AsyncMock(side_effect=lambda form_id, supplied_hash=None: form if form_id == form.id and supplied_hash == form.public_token_hash else None)
    monkeypatch.setattr(public_forms.forms_db, "get_public_form", get_public_form)
    monkeypatch.setattr(public_forms, "enforce_saas_feature", AsyncMock())
    monkeypatch.setattr(public_forms, "_rate_limit_submission", AsyncMock(return_value=True))
    save_submission = AsyncMock()
    monkeypatch.setattr(forms_service, "submit_public_answers", save_submission)

    result = await public_forms.submit_public_form(
        str(form.id),
        _request(
            form.id,
            {"data": {"name": "Aditi", "email": "a@example.com"}},
            token=token,
            origin="https://shop.example.com",
        ),
    )
    assert result.status_code == 202
    assert result.body == b'{"message":"Thank you. Your submission was received."}'
    assert result.headers["access-control-allow-origin"] == "https://shop.example.com"
    assert str(form.organization_id).encode() not in result.body
    save_submission.assert_awaited_once_with(form, token_hash, {"name": "Aditi", "email": "a@example.com"})


@pytest.mark.asyncio
async def test_public_submit_rejects_invalid_rotated_token_and_disallowed_origin(monkeypatch):
    form = _form()
    form.public_submission_enabled = True
    form.public_token_hash = public_forms.hash_public_token("new-token")
    form.public_allowed_origins = ["https://shop.example.com"]
    get_public_form = AsyncMock(side_effect=lambda form_id, supplied_hash=None: form if supplied_hash == form.public_token_hash else None)
    monkeypatch.setattr(public_forms.forms_db, "get_public_form", get_public_form)
    save_submission = AsyncMock()
    monkeypatch.setattr(forms_service, "submit_public_answers", save_submission)

    from fastapi import HTTPException

    for old_token, origin in (("old-token", "https://shop.example.com"), ("new-token", "https://attacker.example")):
        with pytest.raises(HTTPException) as error:
            await public_forms.submit_public_form(
                str(form.id),
                _request(
                    form.id,
                    {"data": {"name": "Aditi", "email": "a@example.com"}},
                    token=old_token,
                    origin=origin,
                ),
            )
        assert error.value.status_code == 404
    save_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_submit_rate_limit_blocks_persistence(monkeypatch):
    form = _form()
    token = "rate-limited-token"
    token_hash = public_forms.hash_public_token(token)
    form.public_submission_enabled = True
    form.public_token_hash = token_hash
    monkeypatch.setattr(
        public_forms.forms_db,
        "get_public_form",
        AsyncMock(return_value=form),
    )
    monkeypatch.setattr(public_forms, "enforce_saas_feature", AsyncMock())
    monkeypatch.setattr(public_forms, "_rate_limit_submission", AsyncMock(return_value=False))
    save_submission = AsyncMock()
    monkeypatch.setattr(forms_service, "submit_public_answers", save_submission)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await public_forms.submit_public_form(
            str(form.id),
            _request(form.id, {"data": {"name": "Aditi"}}, token=token),
        )
    assert error.value.status_code == 429
    save_submission.assert_not_awaited()


@pytest.mark.asyncio
async def test_tenant_member_can_read_only_the_selected_organization_form(monkeypatch):
    app = FastAPI()
    app.include_router(public_forms.router, prefix="/api/v1")
    tenant = SimpleNamespace(is_superuser=False, is_active=True, selected_organization_id=23)
    original_get_user = auth_dependencies.get_user
    form = _form(org_id=23)
    session = _Session(form)
    monkeypatch.setattr(
        forms_db.kodewaves_db_client,
        "get_session",
        _SessionFactory(session),
    )

    async def dependency_get_tenant():
        return tenant

    app.dependency_overrides[original_get_user] = dependency_get_tenant

    monkeypatch.setattr(
        auth_dependencies,
        "get_user",
        AsyncMock(return_value=tenant),
    )
    monkeypatch.setattr(saas_entitlements, "enforce_saas_feature", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        allowed = await client.get(f"/api/v1/forms/{form.id}/public-access")
        tenant.selected_organization_id = 999
        isolated = await client.get(f"/api/v1/forms/{form.id}/public-access")
    assert allowed.status_code == 200
    assert allowed.json() == {
        "enabled": False,
        "token_configured": False,
        "allowed_origins": [],
        "submission_token": None,
    }
    assert isolated.status_code == 404
    assert "organization_id" in str(session.statement)
