import uuid
import re
import unicodedata
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import FormModel, FormSubmissionModel
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.saas_entitlements import require_saas_feature

router = APIRouter(
    prefix="/forms",
    tags=["forms"],
    dependencies=[Depends(require_saas_feature("forms"))],
)


class FormItem(BaseModel):
    id: str
    name: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    fields_schema: List[Dict[str, Any]] = []
    fields: List[Dict[str, Any]] = []
    is_active: bool = True
    submission_count: int = 0
    created_at: str


class FormCreateRequest(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    slug: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    fields_schema: Optional[List[Dict[str, Any]]] = None
    fields: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = True

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, value):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Slug must be text")
        value = re.sub(r"[\s_]+", "-", value.strip().lower())
        value = re.sub(r"-+", "-", value).strip("-")
        if not value or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError(
                "Slug may contain lowercase letters, numbers, and single hyphens"
            )
        if len(value) > 100:
            raise ValueError("Slug must be at most 100 characters")
        return value

    @field_validator("fields", "fields_schema")
    @classmethod
    def unique_field_keys(cls, value):
        keys = set()
        for field in value or []:
            key = field.get("name") or field.get("id") or field.get("label")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Each form field needs a name")
            if key in keys:
                raise ValueError("Form field names must be unique")
            keys.add(key)
        return value


class SubmissionItem(BaseModel):
    id: str
    form_id: str
    data: Dict[str, Any] = {}
    submitted_data: Dict[str, Any] = {}
    created_at: str


class SubmitFormRequest(BaseModel):
    data: Dict[str, Any] = {}
    call_id: Optional[int] = Field(default=None, gt=0)
    contact_id: Optional[str] = None


def _default_slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    return (slug or "form")[:100].rstrip("-") or "form"


async def _find_form(session, org_id: int, form_identifier: str):
    """Resolve UUIDs and workspace slugs, retaining the legacy name lookup."""
    try:
        form_uuid = uuid.UUID(form_identifier)
    except ValueError:
        form_uuid = None
    if form_uuid is not None:
        result = await session.execute(
            select(FormModel).where(
                FormModel.id == form_uuid, FormModel.organization_id == org_id
            )
        )
        return result.scalar_one_or_none()

    result = await session.execute(
        select(FormModel).where(
            FormModel.slug == form_identifier,
            FormModel.organization_id == org_id,
        )
    )
    form = result.scalar_one_or_none()
    if form is not None:
        return form
    result = await session.execute(
        select(FormModel).where(
            FormModel.name == form_identifier,
            FormModel.organization_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def _ensure_slug_available(session, org_id: int, slug: str, exclude_id=None):
    stmt = select(FormModel.id).where(
        FormModel.organization_id == org_id,
        FormModel.slug == slug,
    )
    if exclude_id is not None:
        stmt = stmt.where(FormModel.id != exclude_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="A form with this slug already exists in this workspace",
        )


@router.get("", response_model=List[FormItem])
async def list_forms(user: UserModel = Depends(get_user)):
    """List dynamic forms for the organization with real submission counts."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(
                FormModel,
                func.count(FormSubmissionModel.id).label("sub_count")
            )
            .outerjoin(FormSubmissionModel, FormModel.id == FormSubmissionModel.form_id)
            .where(FormModel.organization_id == org_id)
            .group_by(FormModel.id)
            .order_by(desc(FormModel.created_at))
        )
        result = await session.execute(stmt)
        rows = result.all()
        items = []
        for form, sub_count in rows:
            f_list = form.fields_schema or []
            f_name = form.name
            items.append(
                FormItem(
                    id=str(form.id),
                    name=f_name,
                    title=f_name,
                    slug=form.slug,
                    description=form.description,
                    fields_schema=f_list,
                    fields=f_list,
                    is_active=form.is_active,
                    submission_count=sub_count or 0,
                    created_at=form.created_at.isoformat() if form.created_at else "",
                )
            )
        return items


@router.get("/{form_id}", response_model=FormItem)
async def get_form(form_id: str, user: UserModel = Depends(get_user)):
    """Retrieve details of a single form."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        form = await _find_form(session, org_id, form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        # Get count
        c_stmt = select(func.count(FormSubmissionModel.id)).where(
            FormSubmissionModel.form_id == form.id,
            FormSubmissionModel.organization_id == org_id,
        )
        sub_count = (await session.execute(c_stmt)).scalar() or 0
        f_list = form.fields_schema or []

        return FormItem(
            id=str(form.id),
            name=form.name,
            title=form.name,
            slug=form.slug,
            description=form.description,
            fields_schema=f_list,
            fields=f_list,
            is_active=form.is_active,
            submission_count=sub_count,
            created_at=form.created_at.isoformat() if form.created_at else "",
        )


@router.post("", response_model=Dict[str, Any])
async def create_form(req: FormCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new dynamic voice form."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    name = req.title or req.name
    if not name:
        raise HTTPException(status_code=400, detail="Form title or name is required")

    fields = req.fields if req.fields is not None else (req.fields_schema or [])
    slug = req.slug or _default_slug(name)

    async with kodewaves_db_client.get_session() as session:
        await _ensure_slug_available(session, org_id, slug)
        form = FormModel(
            organization_id=org_id,
            name=name,
            slug=slug,
            description=req.description,
            fields_schema=fields,
            is_active=req.is_active if req.is_active is not None else True,
        )
        session.add(form)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="A form with this slug already exists in this workspace",
            ) from exc
        await session.refresh(form)
        return {
            "id": str(form.id),
            "name": form.name,
            "slug": form.slug,
            "message": "Form created successfully",
        }


@router.put("/{form_id}", response_model=Dict[str, Any])
async def update_form(form_id: str, req: FormCreateRequest, user: UserModel = Depends(get_user)):
    """Update a dynamic form."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        form = await _find_form(session, org_id, form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        name = req.title or req.name
        if name:
            form.name = name
        if "slug" in req.model_fields_set and req.slug is not None:
            await _ensure_slug_available(session, org_id, req.slug, exclude_id=form.id)
            form.slug = req.slug
        if req.description is not None:
            form.description = req.description
        if req.fields is not None:
            form.fields_schema = req.fields
        elif req.fields_schema is not None:
            form.fields_schema = req.fields_schema
        if "is_active" in req.model_fields_set and req.is_active is not None:
            form.is_active = req.is_active

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="A form with this slug already exists in this workspace",
            ) from exc
        return {"id": str(form.id), "slug": form.slug, "message": "Form updated successfully"}


@router.delete("/{form_id}", response_model=Dict[str, Any])
async def delete_form(form_id: str, user: UserModel = Depends(get_user)):
    """Delete a form and its submissions."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        form = await _find_form(session, org_id, form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        await session.delete(form)
        await session.commit()
        return {"message": "Form deleted successfully"}


@router.get("/{form_id}/submissions", response_model=List[SubmissionItem])
async def list_submissions(form_id: str, user: UserModel = Depends(get_user)):
    """List submissions captured by voice agents for a form."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        form = await _find_form(session, org_id, form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        stmt = (
            select(FormSubmissionModel)
            .where(FormSubmissionModel.form_id == form.id, FormSubmissionModel.organization_id == org_id)
            .order_by(desc(FormSubmissionModel.created_at))
            .limit(100)
        )
        result = await session.execute(stmt)
        subs = result.scalars().all()
        return [
            SubmissionItem(
                id=str(s.id),
                form_id=str(s.form_id),
                data=s.submitted_data or {},
                submitted_data=s.submitted_data or {},
                created_at=s.created_at.isoformat() if s.created_at else "",
            )
            for s in subs
        ]


@router.post("/{form_id}/submit", response_model=Dict[str, Any])
async def submit_form(form_id: str, req: SubmitFormRequest, user: UserModel = Depends(get_user)):
    """Submit responses to a dynamic form (called by voice agents or API)."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    from api.services.forms import submit_answers

    try:
        submission = await submit_answers(
            org_id, form_id, req.data, contact_id=req.contact_id, call_id=req.call_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": str(submission.id), "message": "Form submission recorded successfully"}
