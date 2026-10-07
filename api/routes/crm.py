import csv
import io
import uuid
from typing import Any, Dict, List, Optional
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import ContactModel, LeadActivityModel, LeadStageModel
from api.db.models import UserModel
from api.services.auth.depends import get_user

router = APIRouter(prefix="/crm", tags=["crm"])


class ContactCreateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    stage_id: Optional[str] = None
    tags: List[str] = []
    custom_fields: Dict[str, Any] = {}
    notes: Optional[str] = None


class ContactItem(BaseModel):
    id: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone: str
    email: Optional[str]
    company: Optional[str]
    stage_id: Optional[str]
    tags: List[str]
    total_calls: int
    notes: Optional[str] = None
    created_at: str


class LeadStageItem(BaseModel):
    id: str
    name: str
    color: str
    order_index: int


class LeadStageUpdateRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    order_index: Optional[int] = None


class StageReorderRequest(BaseModel):
    stage_ids: List[str]


class AddNoteRequest(BaseModel):
    content: str


class LeadTimelineItem(BaseModel):
    id: str
    activity_type: str
    summary: str
    call_id: Optional[int] = None
    created_at: str


class ContactImportItem(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    stage_id: Optional[str] = None
    tags: List[str] = []


class ContactImportRequest(BaseModel):
    contacts: List[ContactImportItem]


@router.get("/stages", response_model=List[LeadStageItem])
async def list_stages(user: UserModel = Depends(get_user)):
    """List pipeline lead stages for current organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = select(LeadStageModel).where(LeadStageModel.organization_id == org_id).order_by(LeadStageModel.order_index)
        result = await session.execute(stmt)
        stages = result.scalars().all()

        # Seed default stages if none exist
        if not stages:
            defaults = [
                ("New Lead", "#3b82f6", 0),
                ("Contacted", "#eab308", 1),
                ("Qualified", "#a855f7", 2),
                ("Follow-Up", "#f97316", 3),
                ("Closed Won", "#22c55e", 4),
                ("Lost", "#ef4444", 5),
            ]
            for name, color, idx in defaults:
                s = LeadStageModel(organization_id=org_id, name=name, color=color, order_index=idx)
                session.add(s)
            await session.commit()

            stmt = select(LeadStageModel).where(LeadStageModel.organization_id == org_id).order_by(LeadStageModel.order_index)
            result = await session.execute(stmt)
            stages = result.scalars().all()

        return [
            LeadStageItem(id=str(s.id), name=s.name, color=s.color, order_index=s.order_index)
            for s in stages
        ]


@router.get("/contacts", response_model=List[ContactItem])
async def list_contacts(user: UserModel = Depends(get_user)):
    """List CRM contacts for organization."""
    org_id = user.selected_organization_id
    if not org_id:
        return []

    async with kodewaves_db_client.get_session() as session:
        stmt = select(ContactModel).where(ContactModel.organization_id == org_id).order_by(desc(ContactModel.created_at)).limit(100)
        result = await session.execute(stmt)
        contacts = result.scalars().all()
        return [
            ContactItem(
                id=str(c.id),
                first_name=c.first_name,
                last_name=c.last_name,
                phone=c.phone,
                email=c.email,
                company=c.company,
                stage_id=str(c.stage_id) if c.stage_id else None,
                tags=c.tags or [],
                total_calls=c.total_calls,
                notes=(c.custom_fields or {}).get("notes"),
                created_at=c.created_at.isoformat() if c.created_at else "",
            )
            for c in contacts
        ]


class StageCreateRequest(BaseModel):
    name: str
    color: str = "#3b82f6"
    order_index: int = 0


@router.post("/stages", response_model=Dict[str, Any])
async def create_stage(req: StageCreateRequest, user: UserModel = Depends(get_user)):
    """Add a custom pipeline lead stage."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        stage = LeadStageModel(
            organization_id=org_id,
            name=req.name,
            color=req.color,
            order_index=req.order_index,
        )
        session.add(stage)
        await session.commit()
        await session.refresh(stage)
        return {"id": str(stage.id), "name": stage.name, "message": "Stage created successfully"}


@router.post("/contacts", response_model=Dict[str, Any])
async def create_contact(req: ContactCreateRequest, user: UserModel = Depends(get_user)):
    """Create a new contact."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    try:
        contact = await kodewaves_db_client.save_contact(org_id, req.model_dump(exclude_unset=True))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stage ID")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"id": str(contact.id), "phone": contact.phone, "message": "Contact created successfully"}


@router.put("/contacts/{contact_id}", response_model=Dict[str, Any])
async def update_contact(contact_id: str, req: ContactCreateRequest, user: UserModel = Depends(get_user)):
    """Update an existing contact."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    try:
        contact = await kodewaves_db_client.save_contact(org_id, req.model_dump(exclude_unset=True), contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stage ID")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"id": str(contact.id), "message": "Contact updated successfully"}


@router.delete("/contacts/{contact_id}", response_model=Dict[str, Any])
async def delete_contact(contact_id: str, user: UserModel = Depends(get_user)):
    """Delete a contact."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            c_uuid = uuid.UUID(contact_id)
            stmt = select(ContactModel).where(ContactModel.id == c_uuid, ContactModel.organization_id == org_id)
        except ValueError:
            stmt = select(ContactModel).where(ContactModel.phone == contact_id, ContactModel.organization_id == org_id)

        result = await session.execute(stmt)
        contact = result.scalar_one_or_none()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        await session.delete(contact)
        await session.commit()
        return {"message": "Contact deleted successfully"}


@router.put("/stages/{stage_id}", response_model=Dict[str, Any])
async def update_stage(stage_id: str, req: LeadStageUpdateRequest, user: UserModel = Depends(get_user)):
    """Update pipeline lead stage name, color, or order index."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            s_uuid = uuid.UUID(stage_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid stage ID")

        stmt = select(LeadStageModel).where(LeadStageModel.id == s_uuid, LeadStageModel.organization_id == org_id)
        res = await session.execute(stmt)
        stage = res.scalar_one_or_none()
        if not stage:
            raise HTTPException(status_code=404, detail="Stage not found")

        if req.name is not None:
            stage.name = req.name
        if req.color is not None:
            stage.color = req.color
        if req.order_index is not None:
            stage.order_index = req.order_index

        await session.commit()
        return {"id": str(stage.id), "name": stage.name, "message": "Stage updated successfully"}


@router.delete("/stages/{stage_id}", response_model=Dict[str, Any])
async def delete_stage(stage_id: str, user: UserModel = Depends(get_user)):
    """Delete a pipeline lead stage and unassign linked contacts."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            s_uuid = uuid.UUID(stage_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid stage ID")

        stmt = select(LeadStageModel).where(LeadStageModel.id == s_uuid, LeadStageModel.organization_id == org_id)
        res = await session.execute(stmt)
        stage = res.scalar_one_or_none()
        if not stage:
            raise HTTPException(status_code=404, detail="Stage not found")

        from sqlalchemy import update
        await session.execute(
            update(ContactModel)
            .where(ContactModel.stage_id == s_uuid, ContactModel.organization_id == org_id)
            .values(stage_id=None)
        )

        await session.delete(stage)
        await session.commit()
        return {"message": "Stage deleted successfully"}


@router.post("/stages/reorder", response_model=Dict[str, Any])
async def reorder_stages(req: StageReorderRequest, user: UserModel = Depends(get_user)):
    """Reorder kanban stage columns."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        for index, sid in enumerate(req.stage_ids):
            try:
                s_uuid = uuid.UUID(sid)
                stmt = select(LeadStageModel).where(LeadStageModel.id == s_uuid, LeadStageModel.organization_id == org_id)
                res = await session.execute(stmt)
                st = res.scalar_one_or_none()
                if st:
                    st.order_index = index
            except ValueError:
                continue
        await session.commit()
        return {"message": "Stages reordered successfully"}


@router.post("/contacts/import-csv", response_model=Dict[str, Any])
async def import_contacts_csv(req: ContactImportRequest, user: UserModel = Depends(get_user)):
    """Bulk import contacts from CSV items."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    created = 0
    async with kodewaves_db_client.get_session() as session:
        for item in req.contacts:
            if not item.phone:
                continue
            stage_uuid = None
            if item.stage_id:
                try:
                    stage_uuid = uuid.UUID(item.stage_id)
                except ValueError:
                    pass

            contact = ContactModel(
                organization_id=org_id,
                first_name=item.first_name,
                last_name=item.last_name,
                phone=item.phone,
                email=item.email,
                company=item.company,
                stage_id=stage_uuid,
                tags=item.tags or [],
            )
            session.add(contact)
            created += 1
        await session.commit()

    return {"message": f"Successfully imported {created} contact(s)", "count": created}


@router.get("/contacts/export-csv")
async def export_contacts_csv(user: UserModel = Depends(get_user)):
    """Export all organization contacts as downloadable CSV."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        stmt = select(ContactModel).where(ContactModel.organization_id == org_id).order_by(desc(ContactModel.created_at))
        res = await session.execute(stmt)
        contacts = res.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "First Name", "Last Name", "Phone", "Email", "Company", "Tags", "Created At"])
        for c in contacts:
            writer.writerow([
                str(c.id),
                c.first_name or "",
                c.last_name or "",
                c.phone or "",
                c.email or "",
                c.company or "",
                ",".join(c.tags or []),
                c.created_at.isoformat() if c.created_at else "",
            ])

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=contacts.csv"},
        )


@router.get("/contacts/{contact_id}/timeline", response_model=List[LeadTimelineItem])
async def get_contact_timeline(contact_id: str, user: UserModel = Depends(get_user)):
    """Retrieve full activity history, call records, and notes for a contact."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    try:
        c_uuid = uuid.UUID(contact_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid contact ID")
    try:
        activities = await kodewaves_db_client.get_contact_timeline(org_id, c_uuid)
    except LookupError:
        raise HTTPException(status_code=404, detail="Contact not found")
    return [LeadTimelineItem(
        id=str(a.id), activity_type=a.activity_type, summary=a.summary,
        call_id=a.call_id, created_at=a.created_at.isoformat() if a.created_at else "",
    ) for a in activities]


@router.post("/contacts/{contact_id}/notes", response_model=Dict[str, Any])
async def add_contact_note(contact_id: str, req: AddNoteRequest, user: UserModel = Depends(get_user)):
    """Add a note to a contact's activity timeline."""
    org_id = user.selected_organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    async with kodewaves_db_client.get_session() as session:
        try:
            c_uuid = uuid.UUID(contact_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid contact ID")

        stmt = select(ContactModel).where(ContactModel.id == c_uuid, ContactModel.organization_id == org_id)
        res = await session.execute(stmt)
        contact = res.scalar_one_or_none()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")

        note = LeadActivityModel(
            contact_id=c_uuid,
            activity_type="note",
            summary=req.content,
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        return {"id": str(note.id), "message": "Note added successfully"}
