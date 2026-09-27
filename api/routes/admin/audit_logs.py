from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AuditLogModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/audit-logs", tags=["admin-audit-logs"])


class AuditLogItem(BaseModel):
    id: str
    actor_email: str | None = None
    action: str
    resource_type: str
    resource_id: str
    changes: dict = {}
    ip_address: str | None = None
    created_at: str


@router.get("", response_model=List[AuditLogItem])
async def list_audit_logs(limit: int = 100, offset: int = 0, _user=Depends(get_superuser)):
    """Retrieve immutable audit log trail."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(AuditLogModel).order_by(desc(AuditLogModel.created_at)).limit(limit).offset(offset)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            AuditLogItem(
                id=str(r.id),
                actor_email=r.actor_email,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                changes=r.changes or {},
                ip_address=r.ip_address,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in records
        ]
