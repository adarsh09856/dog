"""Website widget CRUD backed by the standard public embed runtime."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db import widgets as widget_db
from api.db.models import UserModel
from api.routes.workflow_embed import generate_embed_script
from api.services.auth.depends import get_user
from api.services.saas_entitlements import enforce_saas_feature, require_saas_feature

router = APIRouter(prefix="/widgets", tags=["widgets"])


class WidgetItem(BaseModel):
    id: str
    workflow_id: int
    agent_id: int | None = None
    widget_name: str
    name: str | None = None
    primary_color: str = "#4f46e5"
    bubble_title: str = "Talk to our AI Agent"
    welcome_message: str | None = None
    bubble_subtitle: str | None = "Click to start voice call"
    position: str = "bottom-right"
    avatar_url: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    is_active: bool = True
    embed_snippet: str
    embed_code: str | None = None


class WidgetCreateRequest(BaseModel):
    workflow_id: int | None = Field(default=None, gt=0)
    agent_id: int | None = Field(default=None, gt=0)
    widget_name: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    primary_color: str = Field(default="#4f46e5", pattern=r"^#[0-9a-fA-F]{6}$")
    bubble_title: str | None = Field(default=None, max_length=100)
    welcome_message: str | None = Field(default=None, max_length=100)
    bubble_subtitle: str | None = Field(
        default="Click to start voice call", max_length=150
    )
    position: Literal["bottom-right", "bottom-left"] = "bottom-right"
    avatar_url: str | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    is_active: bool = True


def _organization_id(user):
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="Organization required")
    return user.selected_organization_id


def _widget_item(widget, token):
    snippet = generate_embed_script(token) if token else ""
    return WidgetItem(
        id=str(widget.id),
        workflow_id=widget.workflow_id,
        agent_id=widget.workflow_id,
        widget_name=widget.widget_name,
        name=widget.widget_name,
        primary_color=widget.primary_color,
        bubble_title=widget.bubble_title,
        welcome_message=widget.bubble_title,
        bubble_subtitle=widget.bubble_subtitle,
        position=widget.position,
        avatar_url=widget.avatar_url,
        allowed_domains=widget.allowed_domains or [],
        is_active=widget.is_active,
        embed_snippet=snippet,
        embed_code=snippet,
    )


def _widget_values(req, creating):
    supplied = req.model_dump(exclude_unset=not creating)
    values = {
        key: value
        for key, value in supplied.items()
        if key
        not in {
            "agent_id",
            "name",
            "welcome_message",
            "workflow_id",
            "widget_name",
            "bubble_title",
        }
    }
    workflow_id = req.workflow_id or req.agent_id
    if workflow_id:
        values["workflow_id"] = workflow_id
    name = req.widget_name or req.name
    title = req.bubble_title or req.welcome_message
    if name or creating:
        values["widget_name"] = name or "Website Voice Widget"
    if title or creating:
        values["bubble_title"] = title or "Talk to our AI Agent"
    return values


@router.get("", response_model=list[WidgetItem], dependencies=[Depends(require_saas_feature("widgets"))])
async def list_widgets(user: UserModel = Depends(get_user)):
    if not user.selected_organization_id:
        return []
    return [
        _widget_item(*row)
        for row in await widget_db.list_widgets(user.selected_organization_id)
    ]


@router.get("/{widget_id}", response_model=WidgetItem, dependencies=[Depends(require_saas_feature("widgets"))])
async def get_widget(widget_id: str, user: UserModel = Depends(get_user)):
    row = await widget_db.get_widget(_organization_id(user), widget_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return _widget_item(*row)


async def _save_widget(req, user, widget_id=None):
    organization_id = _organization_id(user)
    workflow_id = req.workflow_id or req.agent_id
    if not widget_id and not workflow_id:
        raise HTTPException(status_code=400, detail="Workflow / Agent ID is required")
    if workflow_id and not await db_client.get_workflow(
        workflow_id, organization_id=organization_id
    ):
        raise HTTPException(status_code=404, detail="Agent not found in this workspace")
    try:
        widget, token = await widget_db.save_widget(
            organization_id,
            user.id,
            _widget_values(req, widget_id is None),
            widget_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snippet = generate_embed_script(token)
    return {
        "id": str(widget.id),
        "widget_name": widget.widget_name,
        "embed_snippet": snippet,
        "embed_code": snippet,
        "message": "Widget updated successfully"
        if widget_id
        else "Widget created successfully",
    }


@router.post("", response_model=dict[str, Any], dependencies=[Depends(require_saas_feature("widgets"))])
async def create_widget(req: WidgetCreateRequest, user: UserModel = Depends(get_user)):
    return await _save_widget(req, user)


@router.put("/{widget_id}", response_model=dict[str, Any], dependencies=[Depends(require_saas_feature("widgets"))])
async def update_widget(
    widget_id: str, req: WidgetCreateRequest, user: UserModel = Depends(get_user)
):
    return await _save_widget(req, user, widget_id)


@router.delete("/{widget_id}", response_model=dict[str, Any], dependencies=[Depends(require_saas_feature("widgets"))])
async def delete_widget(widget_id: str, user: UserModel = Depends(get_user)):
    try:
        await widget_db.delete_widget(_organization_id(user), widget_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"message": "Widget deleted successfully"}


@router.get("/public/{widget_id}")
async def get_public_widget_config(widget_id: str):
    try:
        widget = await widget_db.get_public_widget(widget_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found or disabled")
    await enforce_saas_feature(widget.organization_id, "widgets")
    return {
        "id": str(widget.id),
        "workflow_id": widget.workflow_id,
        "primary_color": widget.primary_color,
        "bubble_title": widget.bubble_title,
        "bubble_subtitle": widget.bubble_subtitle,
        "position": widget.position,
        "avatar_url": widget.avatar_url,
    }
