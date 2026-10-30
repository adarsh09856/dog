"""Persistence for the owner-managed credit bundle catalog."""

import uuid

from sqlalchemy import select

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import CreditPackageModel


def _selector(identifier: str):
    try:
        return CreditPackageModel.id == uuid.UUID(identifier)
    except ValueError:
        return CreditPackageModel.name == identifier


async def list_packages() -> list[CreditPackageModel]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(CreditPackageModel).order_by(CreditPackageModel.sort_order))
        return list(result.scalars().all())


async def create_package(values: dict) -> CreditPackageModel:
    async with kodewaves_db_client.get_session() as session:
        record = CreditPackageModel(**values)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def update_package(identifier: str, values: dict) -> CreditPackageModel | None:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(CreditPackageModel).where(_selector(identifier)))
        record = result.scalar_one_or_none()
        if record is None:
            return None
        for key, value in values.items():
            setattr(record, key, value)
        await session.commit()
        await session.refresh(record)
        return record


async def delete_package(identifier: str) -> bool:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(CreditPackageModel).where(_selector(identifier)))
        record = result.scalar_one_or_none()
        if record is None:
            return False
        await session.delete(record)
        await session.commit()
        return True
