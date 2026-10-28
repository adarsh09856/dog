import asyncio
from types import SimpleNamespace

from api.routes import installation
from api.services.installation_license import InstallationLicenseError


def test_regular_client_user_can_read_only_entitlements(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        installation,
        "load_license",
        lambda: SimpleNamespace(features={"voice", "crm"}, limits={"max_agents": 3}),
    )
    monkeypatch.setattr(installation, "validate_installation_license", lambda _license: None)

    async def owner_status(_license):
        return SimpleNamespace(using_outage_grace=False)

    monkeypatch.setattr(installation, "require_current_owner_status", owner_status)
    result = asyncio.run(
        installation.installation_feature_status(SimpleNamespace(is_superuser=False))
    )

    assert result == {
        "edition": "client",
        "valid": True,
        "features": ["crm", "voice"],
        "limits": {"max_agents": 3},
        "owner_status": "current",
    }
    assert "domains" not in result
    assert "installation_id" not in result


def test_feature_status_returns_no_grants_for_invalid_installation(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "client")
    monkeypatch.setattr(
        installation,
        "load_license",
        lambda: (_ for _ in ()).throw(InstallationLicenseError("license expired")),
    )
    result = asyncio.run(
        installation.installation_feature_status(SimpleNamespace(is_superuser=False))
    )
    assert result == {
        "edition": "client",
        "valid": False,
        "features": [],
        "limits": {},
        "message": "license expired",
    }


def test_feature_status_does_not_apply_client_license_to_saas(monkeypatch):
    monkeypatch.setattr(installation, "KODEWAVES_EDITION", "saas")
    monkeypatch.setattr(
        installation,
        "load_license",
        lambda: (_ for _ in ()).throw(AssertionError("SaaS must not load a client license")),
    )
    result = asyncio.run(
        installation.installation_feature_status(SimpleNamespace(is_superuser=True))
    )
    assert result == {"edition": "saas", "valid": True, "features": [], "limits": {}}
