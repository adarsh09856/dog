import uuid
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import BannedWordModel, FlaggedCallViolationModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/moderation", tags=["admin-moderation"])


class BannedWordItem(BaseModel):
    id: str
    word: str
    category: str
    severity: str
    auto_block: bool
    is_active: bool


class AddBannedWordRequest(BaseModel):
    word: str
    category: str = "profanity"
    severity: str = "high"
    auto_block: bool = True


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
                word=r.word,
                category=r.category,
                severity=r.severity,
                auto_block=r.auto_block,
                is_active=r.is_active,
            )
            for r in records
        ]


@router.post("/banned-words", response_model=Dict[str, Any])
async def add_banned_word(req: AddBannedWordRequest, _user=Depends(get_superuser)):
    """Add a new prohibited keyword to moderation."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(BannedWordModel).where(BannedWordModel.word == req.word.lower().strip())
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="Word already in moderation list")

        record = BannedWordModel(
            word=req.word.lower().strip(),
            category=req.category,
            severity=req.severity,
            auto_block=req.auto_block,
        )
        session.add(record)
        await session.commit()
        return {"message": f"Added '{req.word}' to banned words list"}


@router.delete("/banned-words/{word_id}", response_model=Dict[str, Any])
async def delete_banned_word(word_id: str, _user=Depends(get_superuser)):
    """Remove a prohibited keyword from moderation."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(BannedWordModel).where(BannedWordModel.id == uuid.UUID(word_id))
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="Word not found")

        await session.delete(record)
        await session.commit()
        return {"message": "Word removed from moderation"}
