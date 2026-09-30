import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc, func, select, or_

from api.db import db_client
from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import OrganizationWalletModel, SaaSPlanModel, WalletLedgerModel
from api.db.models import OrganizationModel, UserModel, WorkflowRunModel
from api.services.auth.depends import get_superuser
from api.services.organization_bootstrap import ensure_organization_bootstrapped
from api.utils.auth import create_jwt_token, hash_password

router = APIRouter(prefix="/users", tags=["admin-users"])


class UserAdminResponse(BaseModel):
    id: int
    email: Optional[str] = None
    provider_id: str
    is_superuser: bool
    is_active: bool = True
    has_local_ai_access: bool = False
    is_wallet_frozen: bool = False
    max_concurrent_calls: int = 2
    max_agents: int = 10
    enable_campaigns: bool = True
    enable_crm: bool = True
    enable_widgets: bool = True
    enable_appointments: bool = True
    enable_forms: bool = True
    enable_byok: bool = True
    created_at: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    wallet_balance_minutes: int = 0
    plan_name: str = "Starter"
    total_calls: int = 0


class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    is_superuser: bool = False
    has_local_ai_access: bool = False
    plan_code: Optional[str] = "starter"
    initial_minutes: int = 60
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    is_superuser: Optional[bool] = None
    is_active: Optional[bool] = None
    has_local_ai_access: Optional[bool] = None
    plan_name: Optional[str] = None
    wallet_balance_minutes: Optional[int] = None
    is_wallet_frozen: Optional[bool] = None
    max_concurrent_calls: Optional[int] = None
    max_agents: Optional[int] = None
    enable_campaigns: Optional[bool] = None
    enable_crm: Optional[bool] = None
    enable_widgets: Optional[bool] = None
    enable_appointments: Optional[bool] = None
    enable_forms: Optional[bool] = None
    enable_byok: Optional[bool] = None



class PromoMinutesRequest(BaseModel):
    minutes: int
    notes: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    new_password: str


class UserStatusRequest(BaseModel):
    is_active: bool


@router.get("", response_model=List[UserAdminResponse])
async def list_admin_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _user=Depends(get_superuser),
):
    """List all users with their organization, wallet balance, call count, and status."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).order_by(desc(UserModel.created_at))

        # Search filter
        if search:
            search_clean = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(UserModel.email).like(search_clean),
                    func.lower(UserModel.provider_id).like(search_clean),
                )
            )

        # Role filter
        if role == "admin":
            stmt = stmt.where(UserModel.is_superuser == True)
        elif role == "user":
            stmt = stmt.where(UserModel.is_superuser == False)

        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        users = result.scalars().all()

        response = []
        for u in users:
            # Primary organization
            org_stmt = select(OrganizationModel).join(UserModel.organizations).where(UserModel.id == u.id)
            org_res = await session.execute(org_stmt)
            org = org_res.scalar_one_or_none()

            wallet_mins = 0
            is_frozen = False
            if org:
                wallet_stmt = select(OrganizationWalletModel).where(OrganizationWalletModel.organization_id == org.id)
                wallet_res = await session.execute(wallet_stmt)
                wallet = wallet_res.scalar_one_or_none()
                if wallet:
                    wallet_mins = wallet.credit_balance_minutes + wallet.bonus_minutes
                    is_frozen = wallet.is_frozen

            # Total calls count for user's workflows
            call_count = 0
            if org:
                calls_stmt = select(func.count(WorkflowRunModel.id)).join(
                    WorkflowRunModel.workflow
                ).where(WorkflowRunModel.workflow.has(organization_id=org.id))
                call_res = await session.execute(calls_stmt)
                call_count = call_res.scalar() or 0

            is_active_val = getattr(u, "is_active", True)
            if is_frozen:
                is_active_val = False

            # Status filter in-memory if needed
            if status == "active" and not is_active_val:
                continue
            if status == "suspended" and is_active_val:
                continue

            # Check if user has admin-granted local AI engine access
            local_setting = await kodewaves_db_client.get_setting(f"local_ai_user_{u.id}")
            has_local_ai = bool(local_setting.get("enabled", False)) if local_setting else False

            org_name_val = "Primary Organization"
            org_plan_val = "Starter Plan"
            org_features = {}
            org_quotas = {}
            if org:
                custom_name = await kodewaves_db_client.get_setting(f"org_name_{org.id}")
                org_name_val = custom_name.get("name") if custom_name and custom_name.get("name") else org.provider_id

                plan_setting = await kodewaves_db_client.get_setting(f"org_plan_{org.id}")
                if plan_setting and plan_setting.get("plan_code"):
                    org_plan_val = f"{plan_setting['plan_code'].capitalize()} Plan"

                org_features = await kodewaves_db_client.get_setting(f"org_features_{org.id}") or {}
                org_quotas = await kodewaves_db_client.get_setting(f"org_quotas_{org.id}") or {}

            response.append(
                UserAdminResponse(
                    id=u.id,
                    email=u.email,
                    provider_id=u.provider_id,
                    is_superuser=u.is_superuser,
                    is_active=is_active_val,
                    has_local_ai_access=has_local_ai,
                    is_wallet_frozen=is_frozen,
                    max_concurrent_calls=org_quotas.get("max_concurrent_calls", 2),
                    max_agents=org_quotas.get("max_agents", 10),
                    enable_campaigns=org_features.get("enable_campaigns", True),
                    enable_crm=org_features.get("enable_crm", True),
                    enable_widgets=org_features.get("enable_widgets", True),
                    enable_appointments=org_features.get("enable_appointments", True),
                    enable_forms=org_features.get("enable_forms", True),
                    enable_byok=org_features.get("enable_byok", True),
                    created_at=u.created_at.isoformat() if u.created_at else None,
                    organization_id=org.id if org else None,
                    organization_name=org_name_val,
                    wallet_balance_minutes=wallet_mins,
                    plan_name=org_plan_val,
                    total_calls=call_count,
                )
            )

        return response



@router.post("", response_model=Dict[str, Any])
async def create_admin_user(req: CreateUserRequest, _user=Depends(get_superuser)):
    """Superadmin provisions a new user account with credentials, organization, and minute grant."""
    existing_user = await db_client.get_user_by_email(req.email)
    if existing_user:
        raise HTTPException(status_code=409, detail=f"User with email '{req.email}' already exists.")

    hashed = hash_password(req.password)
    user = await db_client.create_user_with_email(
        email=req.email,
        password_hash=hashed,
        name=req.name,
    )

    # Set superadmin flag if requested
    if req.is_superuser:
        async with kodewaves_db_client.get_session() as session:
            stmt = select(UserModel).where(UserModel.id == user.id)
            res = await session.execute(stmt)
            u_rec = res.scalar_one_or_none()
            if u_rec:
                u_rec.is_superuser = True
                await session.commit()

    # Create primary organization
    org_provider_id = f"org_{user.provider_id}"
    organization, _ = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=org_provider_id, user_id=user.id
    )

    await db_client.add_user_to_organization(user.id, organization.id)
    await db_client.update_user_selected_organization(user.id, organization.id)

    # Bootstrap default service configs
    await ensure_organization_bootstrapped(
        organization.id,
        created_by=user.provider_id,
    )

    # Initialize wallet with initial minutes
    wallet = await kodewaves_db_client.get_or_create_wallet(organization.id)
    if req.initial_minutes > 0:
        await kodewaves_db_client.add_minutes(
            organization_id=organization.id,
            minutes=req.initial_minutes,
            reason="admin_creation_grant",
            notes=f"Initial minutes granted by superadmin on account provisioning.",
        )

    # Save local AI access if specified
    if req.has_local_ai_access:
        await kodewaves_db_client.set_setting(f"local_ai_user_{user.id}", {"enabled": True}, category="local_ai")
        await kodewaves_db_client.set_setting(f"local_ai_org_{organization.id}", {"enabled": True}, category="local_ai")

    return {
        "message": f"Successfully created user {req.email}",
        "user_id": user.id,
        "organization_id": organization.id,
        "initial_minutes": req.initial_minutes,
        "has_local_ai_access": req.has_local_ai_access,
    }


@router.patch("/{user_id}", response_model=Dict[str, Any])
async def update_admin_user(user_id: int, req: UpdateUserRequest, _user=Depends(get_superuser)):
    """Update user role, active status, local AI access, or manually set wallet minute balance."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if req.is_superuser is not None:
            user.is_superuser = req.is_superuser
        if req.is_active is not None and hasattr(user, "is_active"):
            user.is_active = req.is_active

        await session.commit()

        # Update local AI engine access if requested
        if req.has_local_ai_access is not None:
            await kodewaves_db_client.set_setting(
                f"local_ai_user_{user_id}",
                {"enabled": req.has_local_ai_access},
                category="local_ai"
            )
            if user.selected_organization_id:
                await kodewaves_db_client.set_setting(
                    f"local_ai_org_{user.selected_organization_id}",
                    {"enabled": req.has_local_ai_access},
                    category="local_ai"
                )

        # Update wallet balance or freeze status if requested
        if user.selected_organization_id:
            wallet_stmt = select(OrganizationWalletModel).where(
                OrganizationWalletModel.organization_id == user.selected_organization_id
            )
            w_res = await session.execute(wallet_stmt)
            wallet = w_res.scalar_one_or_none()
            if wallet:
                if req.wallet_balance_minutes is not None:
                    wallet.credit_balance_minutes = max(0, req.wallet_balance_minutes)
                if req.is_wallet_frozen is not None:
                    wallet.is_frozen = req.is_wallet_frozen
            await session.commit()

        # Update plan if requested
        if req.plan_name and user.selected_organization_id:
            clean_plan = req.plan_name.lower().replace(" plan", "").strip()
            await kodewaves_db_client.set_setting(
                f"org_plan_{user.selected_organization_id}",
                {"plan_code": clean_plan, "updated_at": datetime.now(UTC).isoformat()},
                category="plan",
            )

        # Update organization feature flags if provided
        if user.selected_organization_id:
            existing_features = await kodewaves_db_client.get_setting(f"org_features_{user.selected_organization_id}") or {}
            for flag in ["enable_campaigns", "enable_crm", "enable_widgets", "enable_appointments", "enable_forms", "enable_byok"]:
                val = getattr(req, flag, None)
                if val is not None:
                    existing_features[flag] = val
            await kodewaves_db_client.set_setting(f"org_features_{user.selected_organization_id}", existing_features, category="features")

            # Update organization resource quotas if provided
            existing_quotas = await kodewaves_db_client.get_setting(f"org_quotas_{user.selected_organization_id}") or {}
            if req.max_concurrent_calls is not None:
                existing_quotas["max_concurrent_calls"] = req.max_concurrent_calls
            if req.max_agents is not None:
                existing_quotas["max_agents"] = req.max_agents
            await kodewaves_db_client.set_setting(f"org_quotas_{user.selected_organization_id}", existing_quotas, category="quotas")

        return {"message": f"User #{user_id} updated successfully"}



@router.post("/{user_id}/grant-credits", response_model=Dict[str, Any])
async def grant_credits_by_user(user_id: int, req: PromoMinutesRequest, user=Depends(get_superuser)):
    """Grant bonus promo minutes to a user's primary organization."""
    if req.minutes <= 0:
        raise HTTPException(status_code=400, detail="Minutes must be greater than zero.")

    async with kodewaves_db_client.get_session() as session:
        u_stmt = select(UserModel).where(UserModel.id == user_id)
        u_res = await session.execute(u_stmt)
        target_user = u_res.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target user not found")

        org_id = target_user.selected_organization_id
        if not org_id:
            org_stmt = select(OrganizationModel).join(UserModel.organizations).where(UserModel.id == user_id)
            org_res = await session.execute(org_stmt)
            org = org_res.scalar_one_or_none()
            if org:
                org_id = org.id

        if not org_id:
            raise HTTPException(status_code=400, detail="User has no associated organization")

    wallet = await kodewaves_db_client.add_minutes(
        organization_id=org_id,
        minutes=req.minutes,
        reason="admin_promo",
        notes=f"Granted by superadmin {user.email or user.id}: {req.notes or 'No reason provided'}",
    )

    return {
        "user_id": user_id,
        "organization_id": org_id,
        "granted_minutes": req.minutes,
        "new_balance": wallet.credit_balance_minutes,
    }


@router.post("/{organization_id}/promo-minutes", response_model=Dict[str, Any])
async def grant_promo_minutes_by_org(organization_id: int, req: PromoMinutesRequest, user=Depends(get_superuser)):
    """Grant bonus promo minutes to an organization directly."""
    if req.minutes <= 0:
        raise HTTPException(status_code=400, detail="Minutes must be greater than zero.")

    wallet = await kodewaves_db_client.add_minutes(
        organization_id=organization_id,
        minutes=req.minutes,
        reason="admin_promo",
        notes=f"Granted by superadmin {user.email or user.id}: {req.notes or 'No reason provided'}",
    )
    return {
        "organization_id": organization_id,
        "granted_minutes": req.minutes,
        "new_balance": wallet.credit_balance_minutes,
    }


@router.put("/{user_id}/status", response_model=Dict[str, Any])
async def update_user_status(user_id: int, req: UserStatusRequest, _user=Depends(get_superuser)):
    """Suspend or reactivate a user account and freeze/unfreeze their wallet."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if hasattr(user, "is_active"):
            user.is_active = req.is_active

        # Freeze/unfreeze organization wallet
        if user.selected_organization_id:
            w_stmt = select(OrganizationWalletModel).where(
                OrganizationWalletModel.organization_id == user.selected_organization_id
            )
            w_res = await session.execute(w_stmt)
            wallet = w_res.scalar_one_or_none()
            if wallet:
                wallet.is_frozen = not req.is_active

        await session.commit()

        status_str = "activated" if req.is_active else "suspended"
        return {"message": f"User #{user_id} has been {status_str}."}


@router.post("/{user_id}/reset-password", response_model=Dict[str, Any])
async def reset_user_password(user_id: int, req: ResetPasswordRequest, _user=Depends(get_superuser)):
    """Superadmin password override for a user."""
    if len(req.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")

    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.password_hash = hash_password(req.new_password.strip())
        await session.commit()

        return {"message": f"Password reset successfully for user #{user_id} ({user.email})."}


@router.post("/{user_id}/impersonate", response_model=Dict[str, Any])
async def impersonate_user(user_id: int, _user=Depends(get_superuser)):
    """Superadmin login-as-user: generates a valid scoped session JWT token."""
    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        token = create_jwt_token(user.id, user.email or user.provider_id)
        return {
            "token": token,
            "user_id": user.id,
            "email": user.email,
            "redirect_url": "/workflow",
        }


@router.delete("/{user_id}", response_model=Dict[str, Any])
async def delete_user(user_id: int, current_user=Depends(get_superuser)):
    """Permanently delete a user account."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Superadmin cannot delete their own account.")

    async with kodewaves_db_client.get_session() as session:
        stmt = select(UserModel).where(UserModel.id == user_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        await session.delete(user)
        await session.commit()

        return {"message": f"User #{user_id} ({user.email}) deleted permanently."}
