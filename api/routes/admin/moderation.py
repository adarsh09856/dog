import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import BannedWordModel, FlaggedCallViolationModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/moderation", tags=["admin-moderation"])


class BannedWordItem(BaseModel):
    id: str
    keyword: str
    word: str
    category: str
    severity: str
    action: str = "terminate"
    auto_block: bool = True
    is_active: bool = True
    created_at: Optional[str] = None


class AddBannedWordRequest(BaseModel):
    keyword: Optional[str] = None
    word: Optional[str] = None
    category: str = "profanity"
    severity: str = "high"
    action: str = "terminate"
    auto_block: bool = True


class ViolationItem(BaseModel):
    id: str
    workflow_run_id: int
    organization_id: int
    violation_type: str
    matched_text: str
    action_taken: str
    snippet: Optional[str] = ""
    is_reviewed: bool = False
    created_at: str


class UpdateViolationRequest(BaseModel):
    is_reviewed: bool = True


@router.get("/banned-words", response_model=List[BannedWordItem])
async def list_banned_words(_user=Depends(get_superuser)):
    """List all content moderation banned words."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(BannedWordModel).order_by(BannedWordModel.word)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            BannedWordItem(
                id=str(r.id),
                keyword=r.word,
                word=r.word,
                category=r.category,
                severity=r.severity,
                action="terminate" if r.auto_block else "flag",
                auto_block=r.auto_block,
                is_active=r.is_active,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in records
        ]


@router.post("/banned-words", response_model=Dict[str, Any])
async def add_banned_word(req: AddBannedWordRequest, _user=Depends(get_superuser)):
    """Add a new prohibited keyword to moderation."""
    word_text = req.keyword or req.word
    if not word_text or not word_text.strip():
        raise HTTPException(status_code=400, detail="Word/keyword cannot be empty")

    clean_word = word_text.lower().strip()
    auto_block_val = req.auto_block if req.action != "flag" else False

    async with kodewaves_db_client.get_session() as session:
        stmt = select(BannedWordModel).where(BannedWordModel.word == clean_word)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Word already in moderation list")

        record = BannedWordModel(
            word=clean_word,
            category=req.category,
            severity=req.severity,
            auto_block=auto_block_val,
        )
        session.add(record)
        await session.commit()
        return {"message": f"Added '{clean_word}' to banned words list", "id": str(record.id)}


@router.delete("/banned-words/{word_id}", response_model=Dict[str, Any])
async def delete_banned_word(word_id: str, _user=Depends(get_superuser)):
    """Remove a prohibited keyword from moderation."""
    async with kodewaves_db_client.get_session() as session:
        try:
            w_uuid = uuid.UUID(word_id)
            stmt = select(BannedWordModel).where(BannedWordModel.id == w_uuid)
        except ValueError:
            stmt = select(BannedWordModel).where(BannedWordModel.word == word_id)

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Word not found")

        await session.delete(record)
        await session.commit()
        return {"message": "Word removed from moderation"}


@router.get("/violations", response_model=List[ViolationItem])
async def list_violations(
    limit: int = 50,
    is_reviewed: Optional[bool] = None,
    _user=Depends(get_superuser),
):
    """List flagged speech moderation violations from calls."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(FlaggedCallViolationModel)
        if is_reviewed is not None:
            stmt = stmt.where(FlaggedCallViolationModel.is_reviewed == is_reviewed)
        stmt = stmt.order_by(desc(FlaggedCallViolationModel.created_at)).limit(limit)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            ViolationItem(
                id=str(r.id),
                workflow_run_id=r.workflow_run_id,
                organization_id=r.organization_id,
                violation_type=r.speaker,
                matched_text=r.triggered_word,
                action_taken=r.action_taken,
                snippet=r.snippet or "",
                is_reviewed=r.is_reviewed,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in records
        ]


@router.patch("/violations/{violation_id}", response_model=Dict[str, Any])
async def update_violation(
    violation_id: str,
    req: UpdateViolationRequest,
    _user=Depends(get_superuser),
):
    """Update or resolve a moderation violation incident."""
    async with kodewaves_db_client.get_session() as session:
        try:
            v_uuid = uuid.UUID(violation_id)
            stmt = select(FlaggedCallViolationModel).where(FlaggedCallViolationModel.id == v_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid violation UUID")

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Violation not found")

        record.is_reviewed = req.is_reviewed
        await session.commit()
        status_text = "reviewed/resolved" if req.is_reviewed else "unreviewed"
        return {"message": f"Violation marked as {status_text}", "id": str(record.id), "is_reviewed": record.is_reviewed}


@router.delete("/violations/{violation_id}", response_model=Dict[str, Any])
async def delete_violation(violation_id: str, _user=Depends(get_superuser)):
    """Delete a moderation violation incident log."""
    async with kodewaves_db_client.get_session() as session:
        try:
            v_uuid = uuid.UUID(violation_id)
            stmt = select(FlaggedCallViolationModel).where(FlaggedCallViolationModel.id == v_uuid)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid violation UUID")

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Violation not found")

        await session.delete(record)
        await session.commit()
        return {"message": "Violation log deleted successfully"}

