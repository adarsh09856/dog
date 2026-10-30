"""Client installation entitlement status and permitted customer branding."""

import ipaddress
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

from api.constants import AUTH_PROVIDER, KODEWAVES_EDITION
from api.db.client_user_management import (
    create_workspace_user,
    list_workspace_users,
    set_workspace_user_active,
)
from api.db.client_workspace_management import (
    create_admin_workspace,
    list_admin_workspaces,
    switch_admin_workspace,
)
from api.db.kodewaves_client import kodewaves_db_client
from api.db.models import UserModel
from api.schemas.branding import PlatformBranding as ClientBranding
from api.services.auth.depends import get_superuser, get_user
from api.services.client_binding_requests import send_binding_request
from api.services.installation_license import (
    InstallationLicenseError,
    _canonical_domain,
    get_installation_binding,
    load_license,
    validate_installation_license,
)
from api.services.owner_installation_status import require_current_owner_status

router = APIRouter(prefix="/installation", tags=["installation"])


class ClientUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)


class ClientUserStatus(BaseModel):
    active: bool


class ClientWorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ClientBindingChangeRequest(BaseModel):
    domains: list[str] = Field(min_length=1, max_length=20)
    ip_ranges: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("domains")
    @classmethod
    def canonical_domains(cls, values: list[str]) -> list[str]:
        try:
            return sorted({_canonical_domain(value) for value in values})
        except (InstallationLicenseError, ValueError) as exc:
            raise ValueError("Enter valid public hostnames") from exc

    @field_validator("ip_ranges")
    @classmethod
    def canonical_ip_ranges(cls, values: list[str]) -> list[str]:
        try:
            return sorted({str(ipaddress.ip_network(value.strip(), strict=False)) for value in values})
        except (ValueError, AttributeError) as exc:
            raise ValueError("Enter valid IP addresses or CIDR ranges") from exc

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reason is required")
        return value


def _require_client_workspace(user: UserModel) -> int:
    if KODEWAVES_EDITION != "client":
        raise HTTPException(status_code=404, detail="Not found")
    if AUTH_PROVIDER != "local":
        raise HTTPException(status_code=400, detail="Local user management is unavailable with this auth provider")
    if not user.selected_organization_id:
        raise HTTPException(status_code=403, detail="Select a workspace first")
    return user.selected_organization_id


def _client_user_response(user: UserModel) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
    }


@router.get("/users")
async def client_users(_user: Annotated[UserModel, Depends(get_superuser)]) -> list[dict]:
    organization_id = _require_client_workspace(_user)
    return [_client_user_response(user) for user in await list_workspace_users(organization_id)]


@router.get("/workspaces")
async def client_workspaces(_user: Annotated[UserModel, Depends(get_superuser)]) -> list[dict]:
    _require_client_workspace(_user)
    return await list_admin_workspaces(_user.id)


@router.post("/workspaces", status_code=201)
async def create_client_workspace(
    request: ClientWorkspaceCreate,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    _require_client_workspace(_user)
    name = request.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="Workspace name is too short")
    organization_id = await create_admin_workspace(_user.id, name)
    return {"id": organization_id, "name": name}


@router.put("/workspaces/{organization_id}/select")
async def select_client_workspace(
    organization_id: int,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    _require_client_workspace(_user)
    await switch_admin_workspace(_user.id, organization_id)
    return {"selected_organization_id": organization_id}


@router.post("/users", status_code=201)
async def create_client_user(
    request: ClientUserCreate, _user: Annotated[UserModel, Depends(get_superuser)]
) -> dict:
    organization_id = _require_client_workspace(_user)
    created = await create_workspace_user(organization_id, request.email, request.password)
    return _client_user_response(created)


@router.put("/users/{user_id}/status")
async def update_client_user_status(
    user_id: int,
    request: ClientUserStatus,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    organization_id = _require_client_workspace(_user)
    if user_id == _user.id:
        raise HTTPException(status_code=403, detail="Cannot change your own account status")
    updated = await set_workspace_user_active(organization_id, user_id, active=request.active)
    return _client_user_response(updated)


@router.get("/branding", response_model=ClientBranding)
async def get_client_branding() -> ClientBranding:
    key = "client_branding" if KODEWAVES_EDITION == "client" else "branding"
    try:
        current = await kodewaves_db_client.get_setting(key, raise_on_error=True) or {}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Branding is temporarily unavailable") from exc
    return ClientBranding.model_validate(current)


@router.put("/branding", response_model=ClientBranding)
async def update_client_branding(
    branding: ClientBranding, _user: Annotated[UserModel, Depends(get_superuser)]
) -> ClientBranding:
    key = "client_branding" if KODEWAVES_EDITION == "client" else "branding"
    await kodewaves_db_client.set_setting(
        key, branding.model_dump(), category=key
    )
    return branding


@router.get("/features")
async def installation_feature_status(_user: Annotated[UserModel, Depends(get_user)]) -> dict:
    """Return only safe feature grants so every client user can adapt navigation."""
    if KODEWAVES_EDITION != "client":
        return {"edition": KODEWAVES_EDITION, "valid": True, "features": [], "limits": {}}
    try:
        license_data = load_license()
        validate_installation_license(license_data)
        owner_status = await require_current_owner_status(license_data)
    except InstallationLicenseError as exc:
        return {"edition": "client", "valid": False, "features": [], "limits": {}, "message": str(exc)}
    return {
        "edition": "client",
        "valid": True,
        "features": sorted(license_data.features),
        "limits": license_data.limits,
        "owner_status": "outage_grace" if owner_status.using_outage_grace else "current",
    }


@router.get("/license")
async def installation_license_status(_user: Annotated[UserModel, Depends(get_user)]) -> dict:
    if KODEWAVES_EDITION != "client":
        return {"edition": KODEWAVES_EDITION, "license_required": False}
    if not _user.is_superuser:
        raise HTTPException(status_code=403, detail="Client administrator access required")
    try:
        license_data = load_license()
        expected_id = os.getenv("KODEWAVES_INSTALLATION_ID", "").strip()
        if license_data.installation_id != expected_id:
            raise InstallationLicenseError("The license belongs to a different installation")
    except InstallationLicenseError as exc:
        return {
            "edition": "client",
            "valid": False,
            "binding_request_available": False,
            "message": str(exc),
        }
    try:
        domain_matches = _canonical_domain(get_installation_binding()) in license_data.domains
    except InstallationLicenseError:
        domain_matches = False
    details = {
        "edition": "client",
        "installation_id": license_data.installation_id,
        "customer_id": license_data.customer_id,
        "domains": list(license_data.domains),
        "expires_at": license_data.expires_at,
        "features": sorted(license_data.features),
        "limits": license_data.limits,
        "ip_ranges": list(license_data.ip_ranges),
        "binding_request_available": bool(
            os.getenv("KODEWAVES_INSTALLATION_KEY_FILE", "")
            and Path(os.getenv("KODEWAVES_INSTALLATION_KEY_FILE", "")).is_file()
        ),
    }
    try:
        owner_status = await require_current_owner_status(license_data)
    except InstallationLicenseError as exc:
        return {**details, "valid": False, "message": str(exc)}
    if not domain_matches:
        return {**details, "valid": False, "message": "The configured public domain is not in this installation license."}
    return {
        **details,
        "valid": True,
        "owner_status": "outage_grace" if owner_status.using_outage_grace else "current",
        "last_owner_check": owner_status.last_owner_check,
    }


@router.post("/binding-requests", status_code=201)
async def request_installation_binding_change(
    request: ClientBindingChangeRequest,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Send a signed owner-reviewed binding change request from the installation."""
    if KODEWAVES_EDITION != "client":
        raise HTTPException(status_code=404, detail="Not found")
    return await send_binding_request(request.model_dump())
