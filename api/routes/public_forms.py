"""Owner-managed, token-authenticated public form intake."""

from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from api.db import forms as forms_db
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.saas_entitlements import enforce_saas_feature, require_saas_feature
from api.services.call_concurrency.rate_limiter import rate_limiter

router = APIRouter(tags=["public-forms"])

MAX_PUBLIC_FORM_BODY_BYTES = 16 * 1024
MAX_PUBLIC_FORM_FIELDS = 100
MAX_PUBLIC_FORM_ORIGINS = 20
MAX_PUBLIC_FORM_FIELD_NAME = 200
MAX_PUBLIC_FORM_VALUE_BYTES = 8 * 1024
PUBLIC_FORM_IP_RATE_PER_SECOND = 5
PUBLIC_FORM_TOTAL_RATE_PER_SECOND = 40
_PUBLIC_SUBMIT_PATH = re.compile(
    r"^/api/v1/public/forms/([0-9a-fA-F-]{36})/submit$"
)


def hash_public_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_origin(value: str) -> str:
    """Validate and canonicalize an HTTP(S) origin, rejecting paths/wildcards."""
    if not isinstance(value, str) or len(value) > 255 or "*" in value:
        raise ValueError("Enter a valid website origin")
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Enter a valid website origin")
    try:
        port = parsed.port
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Enter a valid website origin") from exc
    if not hostname or any(char.isspace() for char in hostname):
        raise ValueError("Enter a valid website origin")
    if ":" in hostname:
        hostname = f"[{hostname}]"
    scheme = parsed.scheme.lower()
    if port is not None and port != (443 if scheme == "https" else 80):
        hostname = f"{hostname}:{port}"
    return f"{scheme}://{hostname}"


class PublicFormAccessRequest(BaseModel):
    enabled: bool
    allowed_origins: list[str] = Field(default_factory=list, max_length=MAX_PUBLIC_FORM_ORIGINS)
    rotate_token: bool = False

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, values):
        normalized = [normalize_origin(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Website origins must be unique")
        return normalized

    @field_validator("rotate_token")
    @classmethod
    def rotation_requires_enabled(cls, value, info):
        if value and info.data.get("enabled") is False:
            raise ValueError("A token can only be rotated while publishing")
        return value

    @model_validator(mode="after")
    def enabled_requires_allowed_origin(self):
        if self.enabled and not self.allowed_origins:
            raise ValueError("Add at least one allowed website origin before publishing")
        return self


class PublicFormAccessResponse(BaseModel):
    enabled: bool
    token_configured: bool
    allowed_origins: list[str]
    submission_token: str | None = None


class PublicSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict[str, object]

    @field_validator("data")
    @classmethod
    def bound_submission_data(cls, value):
        if len(value) > MAX_PUBLIC_FORM_FIELDS:
            raise ValueError("Too many form fields")
        for name, field_value in value.items():
            if not isinstance(name, str) or not name.strip() or len(name) > MAX_PUBLIC_FORM_FIELD_NAME:
                raise ValueError("Invalid form field")
            if not isinstance(field_value, (str, int, float, bool)) and field_value is not None:
                raise ValueError("Invalid form field value")
            if isinstance(field_value, float) and not math.isfinite(field_value):
                raise ValueError("Invalid form field value")
            if isinstance(field_value, str) and len(field_value.encode("utf-8")) > MAX_PUBLIC_FORM_VALUE_BYTES:
                raise ValueError("Form field is too large")
        return value


async def _read_bounded_json(request: Request) -> PublicSubmissionRequest:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Invalid submission")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > MAX_PUBLIC_FORM_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Invalid submission")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid submission") from exc
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUBLIC_FORM_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Invalid submission")
    try:
        payload = json.loads(body)
        return PublicSubmissionRequest.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid submission") from exc


def _request_origin(request: Request) -> str | None:
    value = request.headers.get("origin")
    if value is None:
        return None
    try:
        return normalize_origin(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Form not found") from exc


def _origin_is_allowed(form, origin: str | None) -> bool:
    if origin is None:
        return True
    allowed = form.public_allowed_origins or []
    return origin in allowed


async def _rate_limit_submission(form, request: Request) -> bool:
    remote_ip = request.client.host if request.client else "unknown"
    ip_digest = hashlib.sha256(remote_ip.encode("utf-8")).hexdigest()[:24]
    by_ip = await rate_limiter.acquire_token(
        form.organization_id,
        PUBLIC_FORM_IP_RATE_PER_SECOND,
        scope_key=f"public_forms:ip:{form.id}:{ip_digest}",
    )
    if not by_ip:
        return False
    return await rate_limiter.acquire_token(
        form.organization_id,
        PUBLIC_FORM_TOTAL_RATE_PER_SECOND,
        scope_key=f"public_forms:form:{form.id}",
    )


@router.get(
    "/forms/{form_id}/public-access",
    response_model=PublicFormAccessResponse,
    dependencies=[Depends(require_saas_feature("forms"))],
)
async def get_public_form_access(
    form_id: str,
    response: Response,
    user: UserModel = Depends(get_user),
):
    response.headers["Cache-Control"] = "no-store"
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")
    try:
        form_uuid = uuid.UUID(form_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Form not found") from exc
    settings = await forms_db.get_public_access_settings(org_id, form_uuid)
    if settings is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return PublicFormAccessResponse(**settings)


@router.put(
    "/forms/{form_id}/public-access",
    response_model=PublicFormAccessResponse,
    dependencies=[Depends(require_saas_feature("forms"))],
)
async def set_public_form_access(
    form_id: str,
    req: PublicFormAccessRequest,
    response: Response,
    user: UserModel = Depends(get_user),
):
    response.headers["Cache-Control"] = "no-store"
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")
    try:
        form_uuid = uuid.UUID(form_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Form not found") from exc
    raw_token = secrets.token_urlsafe(32) if req.enabled else None
    try:
        settings = await forms_db.set_public_access_settings(
            org_id,
            form_uuid,
            enabled=req.enabled,
            allowed_origins=req.allowed_origins,
            rotate_token=req.rotate_token,
            candidate_token_hash=hash_public_token(raw_token) if raw_token else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if settings is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return PublicFormAccessResponse(
        **{key: value for key, value in settings.items() if key != "token_created"},
        submission_token=raw_token if settings["token_created"] else None,
    )


@router.post("/public/forms/{form_id}/submit")
async def submit_public_form(
    form_id: str,
    request: Request,
):
    """Accept public form data using the one-time-shown form bearer token."""
    generic_not_found = HTTPException(status_code=404, detail="Form not found")
    token = request.headers.get("x-form-token", "")
    if not token or len(token) > 128:
        raise generic_not_found
    try:
        form_uuid = uuid.UUID(form_id)
    except (ValueError, TypeError) as exc:
        raise generic_not_found from exc
    token_hash = hash_public_token(token)
    form = await forms_db.get_public_form(form_uuid, token_hash)
    if form is None:
        raise generic_not_found
    origin = _request_origin(request)
    if not _origin_is_allowed(form, origin):
        raise generic_not_found
    await enforce_saas_feature(form.organization_id, "forms")
    if not await _rate_limit_submission(form, request):
        raise HTTPException(status_code=429, detail="Submission limit reached")
    submission_request = await _read_bounded_json(request)
    from api.services.forms import submit_public_answers

    try:
        await submit_public_answers(form, token_hash, submission_request.data)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid submission") from exc
    return JSONResponse(
        status_code=202,
        content={"message": "Thank you. Your submission was received."},
        headers={
            "Cache-Control": "no-store",
            **(
                {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
                if origin and form.public_allowed_origins
                else {}
            ),
        },
    )


class PublicFormCORSMiddleware:
    """Answer form preflights only for an enabled form's configured origin."""

    def __init__(self, app: ASGIApp, api_prefix: str = "/api/v1"):
        self.app = app
        self.api_prefix = api_prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        requested_method = headers.get("access-control-request-method", "").upper()
        path = scope.get("path", "")
        match = _PUBLIC_SUBMIT_PATH.fullmatch(path)
        if not match and self.api_prefix and path.startswith(f"{self.api_prefix}/"):
            match = _PUBLIC_SUBMIT_PATH.fullmatch(path[len(self.api_prefix) :])
        origin = headers.get("origin")
        if not match or not origin or requested_method != "POST":
            await self.app(scope, receive, send)
            return
        try:
            form_uuid = uuid.UUID(match.group(1))
            normalized = normalize_origin(origin)
        except (ValueError, TypeError):
            await Response(status_code=404)(scope, receive, send)
            return
        form = await forms_db.get_public_form(form_uuid)
        if form is None or normalized not in (form.public_allowed_origins or []):
            await Response(status_code=404)(scope, receive, send)
            return
        requested_headers = {
            item.strip().lower()
            for item in headers.get("access-control-request-headers", "").split(",")
            if item.strip()
        }
        if not requested_headers.issubset({"content-type", "x-form-token"}):
            await Response(status_code=400)(scope, receive, send)
            return
        response = Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": normalized,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Form-Token",
                "Access-Control-Max-Age": "600",
                "Vary": "Origin",
            },
        )
        await response(scope, receive, send)
