import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import FormModel, FormSubmissionModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/forms", tags=["forms"])


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
    slug: Optional[str] = None
    description: Optional[str] = None
    fields_schema: Optional[List[Dict[str, Any]]] = None
    fields: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = True


class SubmissionItem(BaseModel):
    id: str
    form_id: str
    data: Dict[str, Any] = {}
    submitted_data: Dict[str, Any] = {}
    created_at: str


class SubmitFormRequest(BaseModel):
    data: Dict[str, Any] = {}
    call_id: Optional[int] = None
    contact_id: Optional[str] = None


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
            f_slug = f_name.lower().replace(" ", "-")
            items.append(
                FormItem(
                    id=str(form.id),
                    name=f_name,
                    title=f_name,
                    slug=f_slug,
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
        try:
            f_uuid = uuid.UUID(form_id)
            stmt = select(FormModel).where(FormModel.id == f_uuid, FormModel.organization_id == org_id)
        except ValueError:
            stmt = select(FormModel).where(FormModel.name == form_id, FormModel.organization_id == org_id)

        result = await session.execute(stmt)
        form = result.scalar_one_or_none()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        # Get count
        c_stmt = select(func.count(FormSubmissionModel.id)).where(FormSubmissionModel.form_id == form.id)
        sub_count = (await session.execute(c_stmt)).scalar() or 0
        f_list = form.fields_schema or []

        return FormItem(
            id=str(form.id),
            name=form.name,
            title=form.name,
            slug=form.name.lower().replace(" ", "-"),
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

    async with kodewaves_db_client.get_session() as session:
        form = FormModel(
            organization_id=org_id,
            name=name,
            description=req.description,
            fields_schema=fields,
            is_active=req.is_active if req.is_active is not None else True,
        )
        session.add(form)
        await session.commit()
        await session.refresh(form)
        return {"id": str(form.id), "name": form.name, "message": "Form created successfully"}


@router.put("/{form_id}", response_model=Dict[str, Any])
async def update_form(form_id: str, req: FormCreateRequest, user: UserModel = Depends(get_user)):
    """Update a dynamic form."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            f_uuid = uuid.UUID(form_id)
            stmt = select(FormModel).where(FormModel.id == f_uuid, FormModel.organization_id == org_id)
        except ValueError:
            stmt = select(FormModel).where(FormModel.name == form_id, FormModel.organization_id == org_id)

        result = await session.execute(stmt)
        form = result.scalar_one_or_none()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        name = req.title or req.name
        if name:
            form.name = name
        if req.description is not None:
            form.description = req.description
        if req.fields is not None:
            form.fields_schema = req.fields
        elif req.fields_schema is not None:
            form.fields_schema = req.fields_schema
        if req.is_active is not None:
            form.is_active = req.is_active

        await session.commit()
        return {"id": str(form.id), "message": "Form updated successfully"}


@router.delete("/{form_id}", response_model=Dict[str, Any])
async def delete_form(form_id: str, user: UserModel = Depends(get_user)):
    """Delete a form and its submissions."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            f_uuid = uuid.UUID(form_id)
            stmt = select(FormModel).where(FormModel.id == f_uuid, FormModel.organization_id == org_id)
        except ValueError:
            stmt = select(FormModel).where(FormModel.name == form_id, FormModel.organization_id == org_id)

        result = await session.execute(stmt)
        form = result.scalar_one_or_none()
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
        try:
            f_uuid = uuid.UUID(form_id)
        except ValueError:
            return []

        stmt = (
            select(FormSubmissionModel)
            .where(FormSubmissionModel.form_id == f_uuid, FormSubmissionModel.organization_id == org_id)
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

    async with kodewaves_db_client.get_session() as session:
        try:
            f_uuid = uuid.UUID(form_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid form ID")

        stmt = select(FormModel).where(FormModel.id == f_uuid, FormModel.organization_id == org_id)
        result = await session.execute(stmt)
        form = result.scalar_one_or_none()
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        contact_uuid = None
        if req.contact_id:
            try:
                contact_uuid = uuid.UUID(req.contact_id)
            except ValueError:
                pass

        sub = FormSubmissionModel(
            form_id=f_uuid,
            organization_id=org_id,
            call_id=req.call_id,
            contact_id=contact_uuid,
            submitted_data=req.data,
        )
        session.add(sub)
        await session.commit()
        return {"id": str(sub.id), "message": "Form submission recorded successfully"}
