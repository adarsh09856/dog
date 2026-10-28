from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from minio import Minio

from api.services.filesystem import minio as storage


def configured_fs(monkeypatch, public_endpoint="https://voice.example.com"):
    internal = Mock()
    internal.bucket_exists.return_value = True
    actual_minio = Minio
    def client(endpoint, **kwargs):
        if endpoint == "minio:9000":
            return internal
        return actual_minio(endpoint, **kwargs)
    monkeypatch.setattr(storage, "Minio", client)
    fs = storage.MinioFileSystem(
        endpoint="minio:9000", public_endpoint=public_endpoint,
        access_key="synthetic-access", secret_key="synthetic-secret",
    )
    return fs, internal


@pytest.mark.asyncio
async def test_public_upload_and_download_are_signed_for_the_public_host(monkeypatch):
    fs, internal = configured_fs(monkeypatch)
    key = "knowledge_base/7/test/Hindi notes.txt"
    put = await fs.aget_presigned_put_url(key, expiration=90)
    get = await fs.aget_signed_url(key, expiration=120, force_inline=True)
    for url, expiry in [(put, "90"), (get, "120")]:
        parsed = urlsplit(url)
        assert parsed.netloc == "voice.example.com"
        assert parsed.path == "/voice-audio/knowledge_base/7/test/Hindi%20notes.txt"
        query = parse_qs(parsed.query)
        assert query["X-Amz-Expires"] == [expiry]
        assert query["X-Amz-Signature"][0]
    assert put != get
    assert parse_qs(urlsplit(get).query)["response-content-disposition"] == ["inline"]
    internal.delete_bucket_policy.assert_called_once_with("voice-audio")
    internal.set_bucket_policy.assert_not_called()


@pytest.mark.asyncio
async def test_internal_download_is_signed_by_internal_client(monkeypatch):
    fs, internal = configured_fs(monkeypatch)
    internal.presigned_get_object.return_value = "internal-signed-url"
    assert await fs.aget_signed_url("object.wav", use_internal_endpoint=True) == "internal-signed-url"
    internal.presigned_get_object.assert_called_once()


@pytest.mark.asyncio
async def test_legacy_endpoint_ending_in_bucket_does_not_duplicate_path(monkeypatch):
    fs, _ = configured_fs(monkeypatch, "https://voice.example.com/voice-audio/")
    url = await fs.aget_presigned_put_url("test.txt")
    assert urlsplit(url).path == "/voice-audio/test.txt"


def test_cannot_silently_start_with_public_policy_when_revocation_fails(monkeypatch):
    client = Mock()
    client.bucket_exists.return_value = True
    client.delete_bucket_policy.side_effect = RuntimeError("denied")
    monkeypatch.setattr(storage, "Minio", Mock(return_value=client))
    with pytest.raises(RuntimeError, match="private MinIO"):
        storage.MinioFileSystem(public_endpoint="https://voice.example.com")


@pytest.mark.parametrize("endpoint", [
    "https://voice.example.com/arbitrary-prefix", "https://user:pass@voice.example.com",
    "https://voice.example.com?token=bad", "https://voice.example.com#fragment",
])
def test_ambiguous_or_credential_bearing_public_endpoints_are_rejected(endpoint):
    with pytest.raises(ValueError):
        storage.MinioFileSystem(public_endpoint=endpoint)
