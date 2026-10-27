"""Opt-in real PostgreSQL check for concurrent first-owner assignment.

Set KODEWAVES_OWNER_RACE_DISPOSABLE_DATABASE_URL to a loopback PostgreSQL
database named kodewaves_owner_race_test. This uses a temporary schema with
only the tables needed for the race, not a fully migrated installation.
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.user_client import UserClient


@pytest.mark.asyncio
async def test_concurrent_first_signups_create_exactly_one_owner(monkeypatch):
    database_url = os.getenv("KODEWAVES_OWNER_RACE_DISPOSABLE_DATABASE_URL")
    if not database_url:
        pytest.skip("Disposable owner-race PostgreSQL database was not supplied")
    parsed = make_url(database_url)
    if (
        parsed.drivername != "postgresql+asyncpg"
        or parsed.host not in {"127.0.0.1", "localhost", "::1"}
        or parsed.database != "kodewaves_owner_race_test"
    ):
        pytest.fail("Owner race test requires a loopback disposable database named kodewaves_owner_race_test")

    schema = f"owner_race_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    engine = create_async_engine(
        database_url, connect_args={"server_settings": {"search_path": schema}}
    )
    schema_created = False
    try:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE organizations (id SERIAL PRIMARY KEY)"))
            await conn.execute(text("""CREATE TABLE users (
                id SERIAL PRIMARY KEY, provider_id VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMPTZ,
                selected_organization_id INTEGER REFERENCES organizations(id),
                is_superuser BOOLEAN, is_active BOOLEAN NOT NULL,
                email VARCHAR, password_hash VARCHAR
            )"""))
            await conn.execute(text(
                "CREATE UNIQUE INDEX ix_users_email_lower ON users (lower(email)) WHERE email IS NOT NULL"
            ))

        # Exercise the shared owner lock, independently of separate client-seat
        # license checks. Delay the count while its transaction lock is held.
        monkeypatch.setattr("api.services.client_creation_limits.KODEWAVES_EDITION", "saas")
        factory = async_sessionmaker(engine)

        @asynccontextmanager
        async def delayed_session():
            async with factory() as session:
                original = session.execute

                async def execute(statement, *args, **kwargs):
                    result = await original(statement, *args, **kwargs)
                    if "count(" in str(statement).lower():
                        await asyncio.sleep(0.05)
                    return result

                session.execute = execute
                yield session

        client = UserClient.__new__(UserClient)
        client.async_session = delayed_session
        users = await asyncio.wait_for(
            asyncio.gather(*(
                client.create_user_with_email(f"user{i}@example.test", "test-hash")
                for i in range(12)
            )),
            timeout=45,
        )
        async with engine.connect() as conn:
            persisted = (await conn.execute(text(
                "SELECT count(*), count(*) FILTER (WHERE is_superuser) FROM users"
            ))).one()
        assert len(users) == 12
        assert sum(bool(user.is_superuser) for user in users) == 1
        assert tuple(persisted) == (12, 1)
    finally:
        await engine.dispose()
        if schema_created:
            async with admin_engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin_engine.dispose()
