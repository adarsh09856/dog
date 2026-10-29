import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import s3_signed_url
from api.routes.s3_signed_url import (
    _extract_legacy_workflow_run_id,
    _extract_org_id_from_key,
)


def test_split_recording_keys_are_workflow_run_artifacts_not_org_keys():
    assert _extract_legacy_workflow_run_id("recordings/1855/user.wav") == 1855
    assert _extract_legacy_workflow_run_id("recordings/1855/bot.wav") == 1855

    assert _extract_org_id_from_key("recordings/1855/user.wav") is None
    assert _extract_org_id_from_key("recordings/1855/bot.wav") is None


def test_legacy_recording_keys_do_not_fall_through_to_org_scoped_auth():
    assert _extract_legacy_workflow_run_id("recordings/1855.wav") == 1855
    assert _extract_legacy_workflow_run_id("recordings/1855/other.wav") is None

    assert _extract_org_id_from_key("recordings/1855.wav") is None
    assert _extract_org_id_from_key("recordings/1855/other.wav") is None
    assert _extract_org_id_from_key("recordings/1855/user.wav/nested") is None


def test_known_org_scoped_keys_extract_org_id():
    assert _extract_org_id_from_key("campaigns/42/source.csv") == 42
    assert _extract_org_id_from_key("knowledge_base/42/document/file.pdf") == 42
    assert _extract_org_id_from_key("recordings/42/greeting-123/greeting.wav") == 42
    assert _extract_legacy_workflow_run_id("campaigns/42/source.csv") is None


def test_unknown_numeric_prefix_is_not_treated_as_org_scoped():
    assert _extract_org_id_from_key("unknown/42/file.wav") is None


def test_metadata_denies_inaccessible_runs_and_unscoped_voicemail(monkeypatch):
    user = SimpleNamespace(is_superuser=False, selected_organization_id=42)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(s3_signed_url.db_client, "get_workflow_run", lookup)
    for key in ("recordings/99.wav", "voicemail_detections/other-tenant.json"):
        with pytest.raises(HTTPException) as error:
            asyncio.run(s3_signed_url.get_file_metadata(key, user))
        assert error.value.status_code == 403
    lookup.assert_awaited_once_with(99, organization_id=42)


def test_metadata_allows_a_run_in_the_current_organization(monkeypatch):
    user = SimpleNamespace(is_superuser=False, selected_organization_id=42)
    monkeypatch.setattr(s3_signed_url.db_client, "get_workflow_run", AsyncMock(
        return_value=SimpleNamespace(storage_backend="minio")
    ))
    storage = SimpleNamespace(aget_file_metadata=AsyncMock(return_value={"size": 4}))
    monkeypatch.setattr(s3_signed_url, "get_storage_for_backend", lambda _backend: storage)
    result = asyncio.run(s3_signed_url.get_file_metadata("recordings/99.wav", user))
    assert result == {"key": "recordings/99.wav", "metadata": {"size": 4}}
