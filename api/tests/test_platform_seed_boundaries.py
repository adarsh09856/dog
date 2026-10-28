"""Startup must not invent sale offers or bypass client enrollment."""

from unittest.mock import AsyncMock, Mock

import pytest

from scripts import seed_platform


@pytest.mark.asyncio
@pytest.mark.parametrize("edition,demo_offers", [("saas", None), ("saas", False), ("saas", True), ("client", True)])
async def test_startup_seeding_respects_edition_and_explicit_demo_offer_choice(monkeypatch, edition, demo_offers):
    monkeypatch.setattr(seed_platform, "runtime_edition", lambda: edition, raising=False)
    if demo_offers is None:
        monkeypatch.delenv("KODEWAVES_SEED_DEMO_OFFERS", raising=False)
    else:
        monkeypatch.setenv("KODEWAVES_SEED_DEMO_OFFERS", str(demo_offers).lower())
    operations = {}
    for name in (
        "seed_global_settings", "seed_saas_plans", "seed_credit_packages",
        "seed_ai_model_catalog", "seed_banned_words", "seed_prompt_templates",
        "seed_wallets_for_existing_orgs", "seed_superadmin_user",
    ):
        operations[name] = AsyncMock()
        monkeypatch.setattr(seed_platform, name, operations[name])
    local_model = Mock()
    monkeypatch.setattr(seed_platform, "seed_local_ai_model", local_model)

    await seed_platform.main()

    for name in ("seed_global_settings", "seed_ai_model_catalog", "seed_banned_words", "seed_prompt_templates"):
        operations[name].assert_awaited_once()
    for name in ("seed_saas_plans", "seed_credit_packages"):
        assert operations[name].await_count == int(edition == "saas" and demo_offers is True)
    for name in ("seed_wallets_for_existing_orgs", "seed_superadmin_user"):
        assert operations[name].await_count == int(edition == "saas")
    assert local_model.call_count == int(edition == "saas")


@pytest.mark.asyncio
async def test_client_cannot_run_owner_account_seed_directly(monkeypatch):
    from scripts import create_superuser

    monkeypatch.setattr(create_superuser, "create_or_promote_superuser", AsyncMock())
    monkeypatch.setattr(seed_platform, "runtime_edition", lambda: "client", raising=False)
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.test")
    monkeypatch.setenv("ADMIN_PASSWORD", "not-an-installation-password")
    with pytest.raises(ValueError, match="owner|client"):
        await seed_platform.seed_superadmin_user()
