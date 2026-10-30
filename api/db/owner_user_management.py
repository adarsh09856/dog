"""Serialized owner account changes keep the control plane recoverable."""

from fastapi import HTTPException
from sqlalchemy import delete, select, text, update

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import AuditLogModel, OrganizationWalletModel
from api.db.models import (
    APIKeyModel, UserConfigurationModel, UserModel, WorkflowModel,
    organization_users_association,
)
from api.db.owner_account_lock import lock_owner_account_mutation


async def _locked_actor_and_target(session, actor_id: int, user_id: int):
    # Every demotion, suspension and deletion uses this same lock. Rechecking
    # the actor afterward stops two owners concurrently removing one another.
    await lock_owner_account_mutation(session)
    actor_result = await session.execute(select(UserModel).where(UserModel.id == actor_id).with_for_update())
    actor = actor_result.scalar_one_or_none()
    if actor is None or not actor.is_active or not actor.is_superuser:
        raise HTTPException(status_code=403, detail="Active owner privileges required")
    if actor_id == user_id:
        return actor, actor
    target_result = await session.execute(select(UserModel).where(UserModel.id == user_id).with_for_update())
    target = target_result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    return actor, target


async def update_account(actor_id: int, user_id: int, values: dict, *, freeze_with_status: bool = False):
    freeze_with_status = freeze_with_status or "is_active" in values
    async with kodewaves_db_client.get_session() as session:
        actor, target = await _locked_actor_and_target(session, actor_id, user_id)
        if actor_id == user_id and (values.get("is_superuser") is False or values.get("is_active") is False):
            raise HTTPException(status_code=409, detail="Use another active owner account to demote or suspend this owner")
        for field in ("is_superuser", "is_active"):
            if values.get(field) is not None:
                setattr(target, field, values[field])
        organization_id = target.selected_organization_id
        if organization_id and (any(values.get(key) is not None for key in (
            "wallet_balance_minutes", "is_wallet_frozen",
        )) or freeze_with_status):
            result = await session.execute(select(OrganizationWalletModel).where(
                OrganizationWalletModel.organization_id == organization_id,
            ).with_for_update())
            wallet = result.scalar_one_or_none()
            if wallet is not None:
                if values.get("wallet_balance_minutes") is not None:
                    wallet.credit_balance_minutes = max(0, int(values["wallet_balance_minutes"]))
                if values.get("is_wallet_frozen") is not None:
                    wallet.is_frozen = values["is_wallet_frozen"]
                if freeze_with_status:
                    wallet.is_frozen = not values["is_active"]
        if values:
            session.add(AuditLogModel(
                actor_id=actor_id, actor_email=actor.email,
                action="user.status" if freeze_with_status else "user.update",
                resource_type="user", resource_id=str(user_id), changes=values,
            ))
        await session.commit()
        return organization_id


async def delete_account(actor_id: int, user_id: int) -> str:
    async with kodewaves_db_client.get_session() as session:
        actor, target = await _locked_actor_and_target(session, actor_id, user_id)
        if actor_id == user_id:
            raise HTTPException(status_code=400, detail="Superadmin cannot delete their own account.")
        email = target.email or target.provider_id
        await session.execute(delete(organization_users_association).where(organization_users_association.c.user_id == user_id))
        await session.execute(delete(UserConfigurationModel).where(UserConfigurationModel.user_id == user_id))
        await session.execute(update(WorkflowModel).where(WorkflowModel.user_id == user_id).values(user_id=None))
        await session.execute(update(APIKeyModel).where(APIKeyModel.created_by == user_id).values(created_by=None))
        session.add(AuditLogModel(
            actor_id=actor_id, actor_email=actor.email, action="user.delete",
            resource_type="user", resource_id=str(user_id), changes={"email": email},
        ))
        await session.delete(target)
        await session.commit()
        return email
