from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql
from api.db.kodewaves_client import kodewaves_db_client


@pytest.mark.asyncio
async def test_bulk_refresh_preserves_admin_disabled_and_verified_voice_flags(monkeypatch):
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    @asynccontextmanager
    async def context():
        yield session
    monkeypatch.setattr(kodewaves_db_client, 'get_session', context)
    rows = [dict(provider='gemini', tts_model='gemini-3.8-flash-tts',
                 voice_id=f'ta-in-native-{i}', name='Tamil speaker',
                 gender='female', languages=['ta-IN'], is_active=True,
                 preview_ok=False) for i in range(401)]
    await kodewaves_db_client.upsert_discovered_voices(rows)
    assert session.execute.await_count == 3
    session.commit.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    update_sql = sql.split('DO UPDATE SET', 1)[1]
    assert 'uq_voice_provider_model_voice' in sql
    assert 'languages = excluded.languages' in update_sql
    assert 'is_active' not in update_sql
    assert 'preview_ok' not in update_sql
