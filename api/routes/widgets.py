import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import WebsiteWidgetModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/widgets", tags=["widgets"])


class WidgetItem(BaseModel):
    id: str
    workflow_id: int
    agent_id: Optional[int] = None
    widget_name: str
    name: Optional[str] = None
    primary_color: str = "#4f46e5"
    bubble_title: str = "Talk to our AI Agent"
    welcome_message: Optional[str] = None
    bubble_subtitle: Optional[str] = "Click to start voice call"
    position: str = "bottom-right"
    avatar_url: Optional[str] = None
    allowed_domains: List[str] = []
    is_active: bool = True
    embed_snippet: str
    embed_code: Optional[str] = None


class WidgetCreateRequest(BaseModel):
    workflow_id: Optional[int] = None
    agent_id: Optional[int] = None
    widget_name: Optional[str] = None
    name: Optional[str] = None
    primary_color: str = "#4f46e5"
    bubble_title: Optional[str] = None
    welcome_message: Optional[str] = None
    bubble_subtitle: Optional[str] = "Click to start voice call"
    position: str = "bottom-right"
    avatar_url: Optional[str] = None
    allowed_domains: List[str] = []
    is_active: bool = True


def _make_embed_snippet(widget_id: str) -> str:
    return (
        f'<script src="https://cdn.kodewaves.ai/widget.js" '
        f'data-widget-id="{widget_id}" async></script>'
    )


@router.get("", response_model=List[WidgetItem])
async def list_widgets(user: UserModel = Depends(get_user)):
    """List embeddable website voice widgets for the organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(WebsiteWidgetModel)
            .where(WebsiteWidgetModel.organization_id == org_id)
            .order_by(desc(WebsiteWidgetModel.created_at))
        )
        result = await session.execute(stmt)
        widgets = result.scalars().all()
        return [
            WidgetItem(
                id=str(w.id),
                workflow_id=w.workflow_id,
                agent_id=w.workflow_id,
                widget_name=w.widget_name,
                name=w.widget_name,
                primary_color=w.primary_color,
                bubble_title=w.bubble_title,
                welcome_message=w.bubble_title,
                bubble_subtitle=w.bubble_subtitle,
                position=w.position,
                avatar_url=w.avatar_url,
                allowed_domains=w.allowed_domains or [],
                is_active=w.is_active,
                embed_snippet=_make_embed_snippet(str(w.id)),
                embed_code=_make_embed_snippet(str(w.id)),
            )
            for w in widgets
        ]


@router.get("/{widget_id}", response_model=WidgetItem)
async def get_widget(widget_id: str, user: UserModel = Depends(get_user)):
    """Retrieve details of a single website widget."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            w_uuid = uuid.UUID(widget_id)
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.id == w_uuid, WebsiteWidgetModel.organization_id == org_id)
        except ValueError:
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.widget_name == widget_id, WebsiteWidgetModel.organization_id == org_id)

        result = await session.execute(stmt)
        w = result.scalar_one_or_none()
        if not w:
            raise HTTPException(status_code=404, detail="Widget not found")

        return WidgetItem(
            id=str(w.id),
            workflow_id=w.workflow_id,
            agent_id=w.workflow_id,
            widget_name=w.widget_name,
            name=w.widget_name,
            primary_color=w.primary_color,
            bubble_title=w.bubble_title,
            welcome_message=w.bubble_title,
            bubble_subtitle=w.bubble_subtitle,
            position=w.position,
            avatar_url=w.avatar_url,
            allowed_domains=w.allowed_domains or [],
            is_active=w.is_active,
            embed_snippet=_make_embed_snippet(str(w.id)),
            embed_code=_make_embed_snippet(str(w.id)),
        )


@router.post("", response_model=Dict[str, Any])
async def create_widget(req: WidgetCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new embeddable voice widget."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    wf_id = req.workflow_id or req.agent_id
    if not wf_id:
        raise HTTPException(status_code=400, detail="Workflow / Agent ID is required")

    name = req.widget_name or req.name or "Website Voice Widget"
    title = req.bubble_title or req.welcome_message or "Talk to our AI Agent"

    async with kodewaves_db_client.get_session() as session:
        widget = WebsiteWidgetModel(
            organization_id=org_id,
            workflow_id=wf_id,
            widget_name=name,
            primary_color=req.primary_color,
            bubble_title=title,
            bubble_subtitle=req.bubble_subtitle,
            position=req.position,
            avatar_url=req.avatar_url,
            allowed_domains=req.allowed_domains,
            is_active=req.is_active,
        )
        session.add(widget)
        await session.commit()
        await session.refresh(widget)
        return {
            "id": str(widget.id),
            "widget_name": widget.widget_name,
            "embed_snippet": _make_embed_snippet(str(widget.id)),
            "embed_code": _make_embed_snippet(str(widget.id)),
            "message": "Widget created successfully",
        }


@router.put("/{widget_id}", response_model=Dict[str, Any])
async def update_widget(widget_id: str, req: WidgetCreateRequest, user: UserModel = Depends(get_user)):
    """Update an existing website widget."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            w_uuid = uuid.UUID(widget_id)
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.id == w_uuid, WebsiteWidgetModel.organization_id == org_id)
        except ValueError:
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.widget_name == widget_id, WebsiteWidgetModel.organization_id == org_id)

        result = await session.execute(stmt)
        w = result.scalar_one_or_none()
        if not w:
            raise HTTPException(status_code=404, detail="Widget not found")

        wf_id = req.workflow_id or req.agent_id
        if wf_id:
            w.workflow_id = wf_id

        name = req.widget_name or req.name
        if name:
            w.widget_name = name

        title = req.bubble_title or req.welcome_message
        if title:
            w.bubble_title = title

        if req.primary_color:
            w.primary_color = req.primary_color
        if req.bubble_subtitle is not None:
            w.bubble_subtitle = req.bubble_subtitle
        if req.position:
            w.position = req.position
        if req.avatar_url is not None:
            w.avatar_url = req.avatar_url
        if req.allowed_domains is not None:
            w.allowed_domains = req.allowed_domains
        if req.is_active is not None:
            w.is_active = req.is_active

        await session.commit()
        return {"id": str(w.id), "message": "Widget updated successfully"}


@router.delete("/{widget_id}", response_model=Dict[str, Any])
async def delete_widget(widget_id: str, user: UserModel = Depends(get_user)):
    """Delete a website widget."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            w_uuid = uuid.UUID(widget_id)
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.id == w_uuid, WebsiteWidgetModel.organization_id == org_id)
        except ValueError:
            stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.widget_name == widget_id, WebsiteWidgetModel.organization_id == org_id)

        result = await session.execute(stmt)
        w = result.scalar_one_or_none()
        if not w:
            raise HTTPException(status_code=404, detail="Widget not found")

        await session.delete(w)
        await session.commit()
        return {"message": "Widget deleted successfully"}


@router.get("/public/{widget_id}")
async def get_public_widget_config(widget_id: str):
    """Public endpoint called by the embed widget script to load UI theme and workflow connection."""
    async with kodewaves_db_client.get_session() as session:
        try:
            w_uuid = uuid.UUID(widget_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid widget ID")

        stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.id == w_uuid)
        result = await session.execute(stmt)
        widget = result.scalar_one_or_none()
        if not widget or not widget.is_active:
            raise HTTPException(status_code=404, detail="Widget not found or disabled")

        return {
            "id": str(widget.id),
            "workflow_id": widget.workflow_id,
            "primary_color": widget.primary_color,
            "bubble_title": widget.bubble_title,
            "bubble_subtitle": widget.bubble_subtitle,
            "position": widget.position,
            "avatar_url": widget.avatar_url,
        }
