"""Prompt template endpoints with workspace ownership and shared system defaults."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import prompt_templates as template_db
from api.services.auth.depends import get_user

router = APIRouter(prefix="/prompt-templates", tags=["prompt-templates"])


class PromptTemplateItem(BaseModel):
    id: str
    category: str
    title: str
    description: str
    system_prompt: str
    first_message: str
    recommended_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_featured: bool = True


class PromptTemplateCreateRequest(BaseModel):
    category: str = Field(default="General", min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=150)
    description: str
    system_prompt: str = Field(min_length=1)
    first_message: str
    recommended_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_featured: bool = False


class PromptTemplateUpdateRequest(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    system_prompt: str | None = Field(default=None, min_length=1)
    first_message: str | None = None
    recommended_tools: list[str] | None = None


def _organization_id(user):
    if not user.selected_organization_id:
        raise HTTPException(status_code=400, detail="Organization required")
    return user.selected_organization_id


def _item(template):
    return PromptTemplateItem(
        id=str(template.id),
        category=template.category,
        title=template.title,
        description=template.description,
        system_prompt=template.system_prompt,
        first_message=template.first_message,
        recommended_tools=template.recommended_tools or [],
        tags=[template.category] + (template.recommended_tools or []),
        is_featured=template.is_system_template,
    )


@router.get("", response_model=list[PromptTemplateItem])
async def list_templates(category: str | None = None, _user=Depends(get_user)):
    records = await template_db.list_templates(
        _organization_id(_user),
        category,
        is_superuser=bool(getattr(_user, "is_superuser", False)),
    )
    return [_item(record) for record in records]


@router.post("", response_model=dict[str, Any])
async def create_template(req: PromptTemplateCreateRequest, _user=Depends(get_user)):
    record = await template_db.create_template(
        _organization_id(_user),
        req.model_dump(exclude={"tags", "is_featured"}),
    )
    return {
        "id": str(record.id),
        "title": record.title,
        "message": "Prompt template created successfully",
    }


async def _mutate(template_id, user, values=None, *, delete=False):
    try:
        return await template_db.mutate_template(
            _organization_id(user),
            template_id,
            values,
            delete=delete,
            is_superuser=bool(getattr(user, "is_superuser", False)),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/{template_id}", response_model=dict[str, Any])
async def delete_template(template_id: str, _user=Depends(get_user)):
    await _mutate(template_id, _user, delete=True)
    return {"message": "Prompt template deleted successfully"}


@router.put("/{template_id}", response_model=dict[str, Any])
async def update_template(
    template_id: str, req: PromptTemplateUpdateRequest, _user=Depends(get_user)
):
    record = await _mutate(template_id, _user, req.model_dump(exclude_unset=True))
    return {
        "id": str(record.id),
        "title": record.title,
        "message": "Prompt template updated successfully",
    }
