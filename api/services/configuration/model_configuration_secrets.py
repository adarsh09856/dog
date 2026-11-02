"""Encryption helpers for persisted organization/workflow model credentials."""

from __future__ import annotations

import copy
import json
from typing import Any

from api.services.configuration.masking import (
    SERVICE_SECRET_FIELDS,
    SENTINEL_UNMASKED_KEYS,
)
from api.services.credentials.master_credential_service import master_credential_service

ENCRYPTED_SECRET_PREFIX = "fernet:v1:"
WORKFLOW_MODEL_SECRET_BLOCKS = (
    "model_overrides",
    "model_configuration_v2_override",
)


def _is_encrypted_secret(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith(ENCRYPTED_SECRET_PREFIX):
        return False
    try:
        json.loads(master_credential_service.decrypt(value[len(ENCRYPTED_SECRET_PREFIX):]))
    except Exception as exc:
        raise ValueError("Encrypted model provider credential cannot be decrypted") from exc
    return True


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
                    if _is_encrypted_secret(nested):
                        result[key] = nested
                    else:
                        payload = json.dumps(nested, separators=(",", ":"))
                        ciphertext = master_credential_service.encrypt(payload)
                        result[key] = ENCRYPTED_SECRET_PREFIX + ciphertext
                elif isinstance(nested, str) and nested.startswith(ENCRYPTED_SECRET_PREFIX):
                    ciphertext = nested[len(ENCRYPTED_SECRET_PREFIX):]
                    result[key] = json.loads(master_credential_service.decrypt(ciphertext))
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
