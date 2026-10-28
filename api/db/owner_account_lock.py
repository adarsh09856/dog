"""Shared transaction lock for changes to owner accounts and privileges."""

from sqlalchemy import text

OWNER_ACCOUNT_ADVISORY_LOCK_ID = 492565710844


async def lock_owner_account_mutation(session) -> None:
    """Serialize owner grants, revocations, suspensions, and removals."""
    await session.execute(
        text(f"SELECT pg_advisory_xact_lock({OWNER_ACCOUNT_ADVISORY_LOCK_ID})")
    )
