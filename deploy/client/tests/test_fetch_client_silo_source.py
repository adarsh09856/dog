from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "owner-tools"))
import fetch_client_silo_source


def test_fetcher_accepts_only_an_existing_approved_source_archive(tmp_path: Path, monkeypatch):
    archive = tmp_path / "silo-source.tar.gz"
    archive.write_bytes(b"release source")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(fetch_client_silo_source, "SILO_SOURCE_SHA256", digest)

    with patch.object(fetch_client_silo_source.urllib.request, "urlopen") as urlopen:
        assert fetch_client_silo_source.fetch_source_archive(archive) == digest
        urlopen.assert_not_called()


def test_fetcher_does_not_publish_a_source_with_the_wrong_digest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(fetch_client_silo_source, "SILO_SOURCE_SHA256", "a" * 64)
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    response = Response(b"not the approved source")
    monkeypatch.setattr(fetch_client_silo_source.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    output = tmp_path / "downloads/silo-source.tar.gz"

    with pytest.raises(ValueError, match="failed its pinned SHA-256 check"):
        fetch_client_silo_source.fetch_source_archive(output)

    assert not output.exists()
    assert not list(output.parent.glob("*.tmp"))
