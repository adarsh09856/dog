from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import payments


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes,bonus,price", [(0, 0, 100), (-1, 0, 100), (10, -1, 100), (10, 0, 0)])
async def test_invalid_bundle_is_rejected_before_gateway(monkeypatch, minutes, bonus, price):
    package = SimpleNamespace(is_active=True, minutes=minutes, bonus_minutes=bonus, price_cents=price)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: package)))

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(payments.kodewaves_db_client, "get_session", lambda: SessionContext())
    monkeypatch.setattr(payments, "get_gateway_credentials", AsyncMock(return_value={}))
    gateway = AsyncMock(side_effect=AssertionError("Gateway must not be contacted"))
    monkeypatch.setattr(payments.httpx, "AsyncClient", gateway)
    with pytest.raises(HTTPException, match="not available for purchase") as error:
        await payments.create_payment_order(
            payments.CreateOrderRequest(package_id="invalid-bundle"),
            SimpleNamespace(selected_organization_id=1),
        )
    assert error.value.status_code == 400
    gateway.assert_not_called()
