import base64
import hashlib
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from api.services.credentials.master_credential_service import MasterCredentialService


def _legacy_fernet(secret: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def _clear_master_key_environment(monkeypatch) -> None:
    for name in (
        "MASTER_CREDENTIAL_ENCRYPTION_KEY",
        "MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS",
        "KODEWAVES_SECRET_KEY",
        "OSS_JWT_SECRET",
        "JWT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_master_provider_credentials_require_an_explicit_encryption_key(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    monkeypatch.setenv("OSS_JWT_SECRET", "a-jwt-secret-is-not-an-encryption-key")
    monkeypatch.setenv("JWT_SECRET", "another-jwt-secret")

    with pytest.raises(RuntimeError, match="MASTER_CREDENTIAL_ENCRYPTION_KEY"):
        MasterCredentialService().encrypt("provider credential")


def test_master_provider_credentials_encrypt_with_the_current_key(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    current_key = Fernet.generate_key()
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY", current_key.decode())

    encrypted = MasterCredentialService().encrypt("provider credential")

    assert Fernet(current_key).decrypt(encrypted.encode()).decode() == "provider credential"


def test_master_provider_credentials_reject_a_malformed_current_key(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(RuntimeError, match="valid URL-safe Fernet key"):
        MasterCredentialService().encrypt("provider credential")


def test_master_provider_credentials_can_read_previous_key_during_rotation(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    current_key = Fernet.generate_key()
    previous_key = Fernet.generate_key()
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY", current_key.decode())
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", previous_key.decode())
    previous_ciphertext = Fernet(previous_key).encrypt(b"legacy provider credential").decode()

    service = MasterCredentialService()
    assert service.decrypt(previous_ciphertext) == "legacy provider credential"

    rotated_ciphertext = service.encrypt("legacy provider credential")
    assert Fernet(current_key).decrypt(rotated_ciphertext.encode()).decode() == "legacy provider credential"


def test_master_provider_credentials_reject_ciphertext_outside_the_keyring(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS", Fernet.generate_key().decode())
    unknown_ciphertext = Fernet.generate_key()
    ciphertext = Fernet(unknown_ciphertext).encrypt(b"provider credential").decode()

    with pytest.raises(RuntimeError, match="cannot be decrypted with the configured keyring"):
        MasterCredentialService().decrypt(ciphertext)


def test_master_provider_credentials_read_explicit_legacy_kodewaves_key(monkeypatch) -> None:
    _clear_master_key_environment(monkeypatch)
    current_key = Fernet.generate_key()
    legacy_secret = "legacy-installed-kodewaves-secret"
    monkeypatch.setenv("MASTER_CREDENTIAL_ENCRYPTION_KEY", current_key.decode())
    monkeypatch.setenv("KODEWAVES_SECRET_KEY", legacy_secret)
    old_ciphertext = _legacy_fernet(legacy_secret).encrypt(b"legacy database row").decode()

    assert MasterCredentialService().decrypt(old_ciphertext) == "legacy database row"


def test_master_service_does_not_use_jwt_or_source_literal_as_encryption_key() -> None:
    service_source = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "credentials"
        / "master_credential_service.py"
    ).read_text(encoding="utf-8")

    assert "os.environ.get(\"OSS_JWT_SECRET\")" not in service_source
    assert "os.environ.get(\"JWT_SECRET\")" not in service_source
    assert "kodewaves-master-sovereign-secret-key-32b" not in service_source
