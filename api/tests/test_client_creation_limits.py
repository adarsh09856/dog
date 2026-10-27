from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.services import client_creation_limits


class _CountResult:
    def __init__(self, count: int):
        self.count = count

    def scalar_one(self) -> int:
        return self.count

    def scalars(self):
        return self

    def first(self):
        return self.count


class _Session:
    def __init__(self, count: int):
        self.count = count
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _CountResult(self.count)


@pytest.mark.asyncio
@pytest.mark.parametrize("limit_name", ["max_seats", "max_workspaces", "max_agents", "max_campaigns"])
@pytest.mark.parametrize("count,allowed", [(1, True), (2, False)])
async def test_signed_creation_limit_is_checked_under_transaction_lock(
    monkeypatch, limit_name, count, allowed
):
    monkeypatch.setattr(client_creation_limits, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        client_creation_limits,
        "load_license",
        lambda: SimpleNamespace(limits={limit_name: 2}),
    )
    monkeypatch.setattr(client_creation_limits, "validate_installation_license", lambda _license: None)
    monkeypatch.setattr(client_creation_limits, "require_current_owner_status", AsyncMock())
    session = _Session(count)

    if allowed:
        await client_creation_limits.enforce_client_creation_limit(
            session, limit_name=limit_name, model=SimpleNamespace(id=1)
        )
    else:
        with pytest.raises(HTTPException) as exc:
            await client_creation_limits.enforce_client_creation_limit(
                session, limit_name=limit_name, model=SimpleNamespace(id=1)
            )
        assert exc.value.status_code == 403

    assert len(session.statements) == 2
    assert "pg_advisory_xact_lock" in str(session.statements[0])


@pytest.mark.asyncio
async def test_saas_creation_does_not_read_client_license(monkeypatch):
    monkeypatch.setattr(client_creation_limits, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        client_creation_limits,
        "load_license",
        lambda: pytest.fail("SaaS must not read installation licensing"),
    )
    session = _Session(100)
    await client_creation_limits.enforce_client_creation_limit(
        session, limit_name="max_workspaces", model=SimpleNamespace(id=1)
    )
    assert session.statements == []


@pytest.mark.asyncio
async def test_existing_workspace_is_reused_after_lock_at_capacity(monkeypatch):
    monkeypatch.setattr(client_creation_limits, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        client_creation_limits,
        "load_license",
        lambda: SimpleNamespace(limits={"max_workspaces": 1}),
    )
    monkeypatch.setattr(client_creation_limits, "validate_installation_license", lambda _license: None)
    monkeypatch.setattr(client_creation_limits, "require_current_owner_status", AsyncMock())
    existing = SimpleNamespace(id=42)
    session = _Session(existing)
    found = await client_creation_limits.enforce_client_creation_limit(
        session,
        limit_name="max_workspaces",
        model=SimpleNamespace(id=1),
        existing_query=client_creation_limits.select(1),
    )
    assert found is existing
    assert len(session.statements) == 2


@pytest.mark.asyncio
async def test_uncapped_creation_still_requires_active_owner_status(monkeypatch):
    monkeypatch.setattr(client_creation_limits, "KODEWAVES_EDITION", "client")
    license_data = SimpleNamespace(limits={})
    monkeypatch.setattr(client_creation_limits, "load_license", lambda: license_data)
    monkeypatch.setattr(client_creation_limits, "validate_installation_license", lambda _license: None)
    owner_status = AsyncMock(side_effect=ValueError("installation revoked"))
    monkeypatch.setattr(client_creation_limits, "require_current_owner_status", owner_status)

    with pytest.raises(ValueError, match="revoked"):
        await client_creation_limits.enforce_client_creation_limit(
            _Session(0), limit_name="max_agents", model=SimpleNamespace(id=1)
        )

    owner_status.assert_awaited_once_with(license_data)
