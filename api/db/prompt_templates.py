"""Shared system templates and private workspace prompt templates."""

import uuid

from sqlalchemy import or_, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import PromptTemplateModel


def _visible(organization_id, is_superuser):
    if is_superuser:
        return True
    return or_(
        PromptTemplateModel.is_system_template.is_(True),
        PromptTemplateModel.organization_id == organization_id,
    )


def _identity(template_id):
    try:
        return PromptTemplateModel.id == uuid.UUID(template_id)
    except ValueError:
        return PromptTemplateModel.title == template_id


async def list_templates(organization_id, category=None, *, is_superuser=False):
    async with kodewaves_db_client.get_session() as session:
        query = select(PromptTemplateModel).where(
            _visible(organization_id, is_superuser)
        )
        if category and category.lower() != "all":
            query = query.where(PromptTemplateModel.category == category)
        result = await session.execute(
            query.order_by(PromptTemplateModel.category, PromptTemplateModel.title)
        )
        return list(result.scalars().all())


async def create_template(organization_id, values):
    async with kodewaves_db_client.get_session() as session:
        template = PromptTemplateModel(
            organization_id=organization_id, is_system_template=False, **values
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template


async def mutate_template(
    organization_id, template_id, values=None, *, delete=False, is_superuser=False
):
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(PromptTemplateModel)
            .where(
                _identity(template_id),
                _visible(organization_id, is_superuser),
            )
            .limit(1)
            .with_for_update()
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise LookupError("Template not found")
        if template.is_system_template and not is_superuser:
            raise PermissionError(
                "Only a platform administrator can change a system prompt template"
            )
        if delete:
            await session.delete(template)
        else:
            for key, value in (values or {}).items():
                if value is not None:
                    setattr(template, key, value)
        await session.commit()
        if not delete:
            await session.refresh(template)
        return template
