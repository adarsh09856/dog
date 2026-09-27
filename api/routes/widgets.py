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
    widget_name: str
    primary_color: str
    bubble_title: str
    bubble_subtitle: Optional[str] = None
    position: str
    avatar_url: Optional[str] = None
    allowed_domains: List[str]
    is_active: bool
    embed_snippet: str


class WidgetCreateRequest(BaseModel):
    workflow_id: int
    widget_name: str
    primary_color: str = "#4f46e5"
    bubble_title: str = "Talk to our AI Agent"
    bubble_subtitle: Optional[str] = "Click to start voice call"
    position: str = "bottom-right"
    avatar_url: Optional[str] = None
    allowed_domains: List[str] = []


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
                widget_name=w.widget_name,
                primary_color=w.primary_color,
                bubble_title=w.bubble_title,
                bubble_subtitle=w.bubble_subtitle,
                position=w.position,
                avatar_url=w.avatar_url,
                allowed_domains=w.allowed_domains or [],
                is_active=w.is_active,
                embed_snippet=_make_embed_snippet(str(w.id)),
            )
            for w in widgets
        ]


@router.post("", response_model=Dict[str, Any])
async def create_widget(req: WidgetCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new embeddable voice widget."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        widget = WebsiteWidgetModel(
            organization_id=org_id,
            workflow_id=req.workflow_id,
            widget_name=req.widget_name,
            primary_color=req.primary_color,
            bubble_title=req.bubble_title,
            bubble_subtitle=req.bubble_subtitle,
            position=req.position,
            avatar_url=req.avatar_url,
            allowed_domains=req.allowed_domains,
        )
        session.add(widget)
        await session.commit()
        await session.refresh(widget)
        return {
            "id": str(widget.id),
            "widget_name": widget.widget_name,
            "embed_snippet": _make_embed_snippet(str(widget.id)),
            "message": "Widget created successfully",
        }


@router.get("/public/{widget_id}")
async def get_public_widget_config(widget_id: str):
    """Public endpoint called by the embed widget script to load UI theme and workflow connection."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(WebsiteWidgetModel).where(WebsiteWidgetModel.id == uuid.UUID(widget_id))
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
