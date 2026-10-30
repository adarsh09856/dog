"""Read published pricing without creating catalog entries as a side effect."""

from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import CreditPackageModel, SaaSPlanModel


async def list_active_plans() -> list[SaaSPlanModel]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(SaaSPlanModel).where(
                SaaSPlanModel.is_active.is_(True),
                SaaSPlanModel.is_public.is_(True),
            )
            .order_by(SaaSPlanModel.monthly_price_cents, SaaSPlanModel.name)
        )
        return list(result.scalars().all())


async def list_active_credit_packages() -> list[CreditPackageModel]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(CreditPackageModel).where(CreditPackageModel.is_active.is_(True))
            .order_by(CreditPackageModel.sort_order, CreditPackageModel.name)
        )
        return list(result.scalars().all())
