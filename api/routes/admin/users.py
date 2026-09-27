from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import OrganizationWalletModel, SaaSPlanModel
from api.db.models import OrganizationModel, UserModel
from api.services.auth.depends import get_superuser

router = APIRouter(prefix="/users", tags=["admin-users"])


class UserAdminResponse(BaseModel):
    id: int
    email: Optional[str] = None
    provider_id: str
    is_superuser: bool
    created_at: Optional[str] = None
    organization_id: Optional[int] = None
    wallet_balance_minutes: int = 0
    plan_name: str = "Free Trial"


class PromoMinutesRequest(BaseModel):
    minutes: int
    notes: Optional[str] = None


@router.get("", response_model=List[UserAdminResponse])
async def list_admin_users(limit: int = 50, offset: int = 0, _user=Depends(get_superuser)):
    """List all users with their primary organization and wallet balance."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).order_by(desc(UserModel.created_at)).limit(limit).offset(offset)
        result = await session.execute(stmt)
        users = result.scalars().all()

        response = []
        for u in users:
            # Get primary org
            org_stmt = select(OrganizationModel).join(UserModel.organizations).where(UserModel.id == u.id)
            org_res = await session.execute(org_stmt)
            org = org_res.scalar_one_or_none()

            wallet_mins = 0
            if org:
                wallet_stmt = select(OrganizationWalletModel).where(OrganizationWalletModel.organization_id == org.id)
                wallet_res = await session.execute(wallet_stmt)
                wallet = wallet_res.scalar_one_or_none()
                if wallet:
                    wallet_mins = wallet.credit_balance_minutes + wallet.bonus_minutes

            response.append(
                UserAdminResponse(
                    id=u.id,
                    email=u.email,
                    provider_id=u.provider_id,
                    is_superuser=u.is_superuser,
                    created_at=u.created_at.isoformat() if u.created_at else None,
                    organization_id=org.id if org else None,
                    wallet_balance_minutes=wallet_mins,
                    plan_name="Starter Plan",
                )
            )

        return response


@router.post("/{organization_id}/promo-minutes", response_model=Dict[str, Any])
async def grant_promo_minutes(organization_id: int, req: PromoMinutesRequest, user=Depends(get_superuser)):
    """Grant bonus promo minutes to an organization."""
    if req.minutes <= 0:
        raise HTTPException(status_code=400, detail="Minutes must be greater than zero.")

    wallet = await kodewaves_db_client.add_minutes(
        organization_id=organization_id,
        minutes=req.minutes,
        reason="admin_promo",
        notes=f"Granted by admin {user.email or user.id}: {req.notes or 'No reason provided'}",
    )
    return {
        "organization_id": organization_id,
        "granted_minutes": req.minutes,
        "new_balance": wallet.credit_balance_minutes,
    }
