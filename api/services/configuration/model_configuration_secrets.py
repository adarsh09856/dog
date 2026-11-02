"""Encryption helpers for persisted organization/workflow model credentials."""

from __future__ import annotations

import copy
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from api.services.configuration.masking import (
    SERVICE_SECRET_FIELDS,
    SENTINEL_UNMASKED_KEYS,
)

ENCRYPTED_SECRET_PREFIX = "fernet:v1:"
CURRENT_KEY_ENV = "MASTER_CREDENTIAL_ENCRYPTION_KEY"
PREVIOUS_KEYS_ENV = "MASTER_CREDENTIAL_ENCRYPTION_KEY_PREVIOUS"
WORKFLOW_MODEL_SECRET_BLOCKS = (
    "model_overrides",
    "model_configuration_v2_override",
)


class ModelConfigurationSecretError(RuntimeError):
    """Raised when model secrets cannot be encrypted or decrypted safely."""


def _configured_ciphers() -> tuple[Fernet, ...]:
    current_key = os.environ.get(CURRENT_KEY_ENV, "").strip()
    if not current_key:
        raise ModelConfigurationSecretError(
            f"{CURRENT_KEY_ENV} must be explicitly configured to store model provider credentials"
        )

    configured_keys = [current_key]
    configured_keys.extend(
        key.strip()
        for key in os.environ.get(PREVIOUS_KEYS_ENV, "").split(",")
        if key.strip()
    )
    ciphers: list[Fernet] = []
    for key in dict.fromkeys(configured_keys):
        try:
            # The preflight accepts both padded and unpadded URL-safe Fernet
            # encodings; cryptography's Fernet constructor requires padding.
            normalized_key = key + "=" * (-len(key) % 4)
            ciphers.append(Fernet(normalized_key.encode("ascii")))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ModelConfigurationSecretError(
                f"{CURRENT_KEY_ENV} and {PREVIOUS_KEYS_ENV} must contain valid Fernet keys"
            ) from exc
    return tuple(ciphers)


def _decrypt_secret_payload(value: str) -> tuple[str, int]:
    ciphertext = value[len(ENCRYPTED_SECRET_PREFIX) :]
    for key_index, cipher in enumerate(_configured_ciphers()):
        try:
            return cipher.decrypt(ciphertext.encode("ascii")).decode("utf-8"), key_index
        except (InvalidToken, ValueError, UnicodeEncodeError):
            continue
    raise ModelConfigurationSecretError(
        "Encrypted model provider credential cannot be decrypted with the configured keyring"
    )


def _encrypt_secret_payload(payload: str) -> str:
    cipher = _configured_ciphers()[0]
    return ENCRYPTED_SECRET_PREFIX + cipher.encrypt(payload.encode("utf-8")).decode("ascii")


def _read_encrypted_secret(value: Any) -> tuple[str, int] | None:
    if not isinstance(value, str) or not value.startswith(ENCRYPTED_SECRET_PREFIX):
        return None
    try:
        payload, key_index = _decrypt_secret_payload(value)
        json.loads(payload)
    except Exception as exc:
        if isinstance(exc, ModelConfigurationSecretError):
            raise
        raise ModelConfigurationSecretError(
            "Encrypted model provider credential has an invalid payload"
        ) from exc
    return payload, key_index


def _transform_model_secrets(value: Any, *, encrypt: bool) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, nested in value.items():
            if key in SERVICE_SECRET_FIELDS and nested not in (None, ""):
                if isinstance(nested, str) and key == "api_key" and (
                    nested in SENTINEL_UNMASKED_KEYS or nested.startswith("sovereign-")
                ):
                    result[key] = nested
                elif encrypt:
                    encrypted = _read_encrypted_secret(nested)
                    if encrypted is not None:
                        payload, key_index = encrypted
                        result[key] = (
                            nested if key_index == 0 else _encrypt_secret_payload(payload)
                        )
                    else:
                        payload = json.dumps(nested, separators=(",", ":"))
                        result[key] = _encrypt_secret_payload(payload)
                elif isinstance(nested, str) and nested.startswith(ENCRYPTED_SECRET_PREFIX):
                    payload, _key_index = _decrypt_secret_payload(nested)
                    try:
                        result[key] = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        raise ModelConfigurationSecretError(
                            "Encrypted model provider credential has an invalid payload"
                        ) from exc
                else:
                    result[key] = _transform_model_secrets(nested, encrypt=False)
            else:
                result[key] = _transform_model_secrets(nested, encrypt=encrypt)
        return result
    if isinstance(value, list):
        return [_transform_model_secrets(item, encrypt=encrypt) for item in value]
    return value


def encrypt_model_configuration_secrets(value: dict) -> dict:
    """Encrypt provider secrets in an org model configuration before storing it."""
    return _transform_model_secrets(value, encrypt=True)


def decrypt_model_configuration_secrets(value: dict) -> dict:
    """Decrypt provider secrets on read; accept legacy plaintext transparently."""
    return _transform_model_secrets(value, encrypt=False)


def encrypt_workflow_model_configuration_secrets(value: dict | None) -> dict | None:
    """Encrypt only the model override blocks in a workflow configuration."""
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    for key in WORKFLOW_MODEL_SECRET_BLOCKS:
        block = result.get(key)
        if isinstance(block, dict):
            result[key] = encrypt_model_configuration_secrets(block)
    return result


def decrypt_workflow_model_configuration_secrets(value: dict | None) -> dict | None:
    """Decrypt model override blocks while leaving unrelated workflow data intact."""
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    for key in WORKFLOW_MODEL_SECRET_BLOCKS:
        block = result.get(key)
        if isinstance(block, dict):
            result[key] = decrypt_model_configuration_secrets(block)
    return result
