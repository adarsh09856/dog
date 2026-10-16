"""Workspace-scoped website widgets and their independent public embed tokens."""

import secrets
import uuid

from sqlalchemy import and_, desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import WebsiteWidgetModel
from api.db.models import EmbedTokenModel, WorkflowModel


def _identity(widget_id):
    try:
        return WebsiteWidgetModel.id == uuid.UUID(widget_id)
    except ValueError:
        return WebsiteWidgetModel.widget_name == widget_id


def _query(organization_id):
    return (
        select(WebsiteWidgetModel, EmbedTokenModel)
        .outerjoin(
            EmbedTokenModel,
            and_(
                EmbedTokenModel.id == WebsiteWidgetModel.embed_token_id,
                EmbedTokenModel.organization_id == organization_id,
            ),
        )
        .where(WebsiteWidgetModel.organization_id == organization_id)
    )


async def list_widgets(organization_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            _query(organization_id).order_by(desc(WebsiteWidgetModel.created_at))
        )
        return list(result.all())


async def get_widget(organization_id, widget_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            _query(organization_id).where(_identity(widget_id)).limit(1)
        )
        return result.first()


async def save_widget(organization_id, user_id, values, widget_id=None):
    async with kodewaves_db_client.get_session() as session:
        widget = None
        if widget_id:
            result = await session.execute(
                select(WebsiteWidgetModel)
                .where(
                    WebsiteWidgetModel.organization_id == organization_id,
                    _identity(widget_id),
                )
                .limit(1)
                .with_for_update()
            )
            widget = result.scalar_one_or_none()
            if widget is None:
                raise LookupError("Widget not found")
        workflow_id = values.get("workflow_id") or (
            widget.workflow_id if widget else None
        )
        result = await session.execute(
            select(WorkflowModel.id).where(
                WorkflowModel.id == workflow_id,
                WorkflowModel.organization_id == organization_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise LookupError("Agent not found in this workspace")
        if widget is None:
            widget = WebsiteWidgetModel(
                organization_id=organization_id, workflow_id=workflow_id
            )
            session.add(widget)
        for key, value in values.items():
            setattr(widget, key, value)
        await session.flush()
        token = None
        if widget.embed_token_id:
            result = await session.execute(
                select(EmbedTokenModel).where(
                    EmbedTokenModel.id == widget.embed_token_id,
                    EmbedTokenModel.organization_id == organization_id,
                )
            )
            token = result.scalar_one_or_none()
        if token is None:
            token = EmbedTokenModel(
                token=f"emb_{secrets.token_urlsafe(32)}",
                workflow_id=workflow_id,
                organization_id=organization_id,
                created_by=user_id,
                usage_count=0,
            )
            session.add(token)
            await session.flush()
            widget.embed_token_id = token.id
        token.workflow_id = workflow_id
        token.is_active = widget.is_active
        token.allowed_domains = widget.allowed_domains or []
        token.settings = {
            "websiteWidgetId": str(widget.id),
            "widgetType": "voice",
            "embedMode": "floating",
            "buttonText": widget.bubble_title,
            "callToActionText": widget.bubble_subtitle or "",
            "buttonColor": widget.primary_color,
            "position": widget.position,
        }
        await session.commit()
        await session.refresh(widget)
        await session.refresh(token)
        return widget, token


async def delete_widget(organization_id, widget_id):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(WebsiteWidgetModel)
            .where(
                WebsiteWidgetModel.organization_id == organization_id,
                _identity(widget_id),
            )
            .limit(1)
            .with_for_update()
        )
        widget = result.scalar_one_or_none()
        if widget is None:
            raise LookupError("Widget not found")
        if widget.embed_token_id:
            result = await session.execute(
                select(EmbedTokenModel).where(
                    EmbedTokenModel.id == widget.embed_token_id,
                    EmbedTokenModel.organization_id == organization_id,
                )
            )
            token = result.scalar_one_or_none()
            if token is not None:
                token.is_active = False
        await session.delete(widget)
        await session.commit()


async def get_public_widget(widget_id):
    try:
        widget_uuid = uuid.UUID(widget_id)
    except ValueError as exc:
        raise ValueError("Invalid widget ID") from exc
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(WebsiteWidgetModel).where(
                WebsiteWidgetModel.id == widget_uuid,
                WebsiteWidgetModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()
