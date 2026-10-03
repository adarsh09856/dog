from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AuditLogModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/audit-logs", tags=["admin-audit-logs"])


class AuditLogItem(BaseModel):
    id: str
    actor_email: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: str
    target_resource: Optional[str] = None
    changes: Dict[str, Any] = {}
    details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    created_at: str


@router.get("", response_model=List[AuditLogItem])
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    actor: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    _user=Depends(get_superuser),
):
    """Retrieve immutable audit log trail with optional filters."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(AuditLogModel)

        if actor and actor.strip():
            stmt = stmt.where(AuditLogModel.actor_email.ilike(f"%{actor.strip()}%"))
        if action and action.strip():
            stmt = stmt.where(AuditLogModel.action.ilike(f"%{action.strip()}%"))
        if resource_type and resource_type.strip():
            stmt = stmt.where(AuditLogModel.resource_type == resource_type.strip())
        if date_from and date_from.strip():
            try:
                dt_from = datetime.fromisoformat(date_from.strip().replace("Z", "+00:00"))
                stmt = stmt.where(AuditLogModel.created_at >= dt_from)
            except Exception:
                pass
        if date_to and date_to.strip():
            try:
                dt_to = datetime.fromisoformat(date_to.strip().replace("Z", "+00:00"))
                stmt = stmt.where(AuditLogModel.created_at <= dt_to)
            except Exception:
                pass

        stmt = stmt.order_by(desc(AuditLogModel.created_at)).limit(limit).offset(offset)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            AuditLogItem(
                id=str(r.id),
                actor_email=r.actor_email,
                user_email=r.actor_email,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                target_resource=f"{r.resource_type}:{r.resource_id}",
                changes=r.changes or {},
                details=r.changes or {},
                ip_address=r.ip_address,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in records
        ]

