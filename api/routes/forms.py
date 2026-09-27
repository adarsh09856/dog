import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import FormModel, FormSubmissionModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/forms", tags=["forms"])


class FormItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    fields_schema: List[Dict[str, Any]]
    is_active: bool
    created_at: str


class FormCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    fields_schema: List[Dict[str, Any]]


class SubmissionItem(BaseModel):
    id: str
    form_id: str
    submitted_data: Dict[str, Any]
    created_at: str


@router.get("", response_model=List[FormItem])
async def list_forms(user: UserModel = Depends(get_user)):
    """List dynamic forms for the organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = select(FormModel).where(FormModel.organization_id == org_id).order_by(desc(FormModel.created_at))
        result = await session.execute(stmt)
        forms = result.scalars().all()
        return [
            FormItem(
                id=str(f.id),
                name=f.name,
                description=f.description,
                fields_schema=f.fields_schema or [],
                is_active=f.is_active,
                created_at=f.created_at.isoformat() if f.created_at else "",
            )
            for f in forms
        ]


@router.post("", response_model=Dict[str, Any])
async def create_form(req: FormCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new dynamic form."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        form = FormModel(
            organization_id=org_id,
            name=req.name,
            description=req.description,
            fields_schema=req.fields_schema,
        )
        session.add(form)
        await session.commit()
        return {"id": str(form.id), "name": form.name, "message": "Form created successfully"}


@router.get("/{form_id}/submissions", response_model=List[SubmissionItem])
async def list_submissions(form_id: str, user: UserModel = Depends(get_user)):
    """List submissions captured by voice agents for a form."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = (
            select(FormSubmissionModel)
            .where(FormSubmissionModel.form_id == uuid.UUID(form_id), FormSubmissionModel.organization_id == org_id)
            .order_by(desc(FormSubmissionModel.created_at))
            .limit(100)
        )
        result = await session.execute(stmt)
        subs = result.scalars().all()
        return [
            SubmissionItem(
                id=str(s.id),
                form_id=str(s.form_id),
                submitted_data=s.submitted_data or {},
                created_at=s.created_at.isoformat() if s.created_at else "",
            )
            for s in subs
        ]
