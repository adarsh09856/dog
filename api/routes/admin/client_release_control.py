"""Owner-only immutable release catalog and per-install rollout controls."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError

from api.db.client_releases import (
    ClientReleaseConflict,
    create_release,
    create_rollout,
    get_rollout,
    get_rollout_by_idempotency,
    list_releases,
    list_rollouts,
    publish_release,
    transition_rollout,
)
from api.db.models import UserModel
from api.services.auth.depends import get_superuser
from api.services.client_update_protocol import (
    ClientUpdateProtocolError,
    verify_release_envelope,
)

router = APIRouter(tags=["admin-client-release-control"])


class ClientReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,99}$")
    version: str
    archive_url: str
    archive_sha256: str
    archive_signature: str
    min_current_version: str
    notes: str = Field(default="", max_length=4000)


class RolloutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str = Field(min_length=3, max_length=100)
    installation_ids: list[str] = Field(min_length=1, max_length=500)

    @field_validator("installation_ids")
    @classmethod
    def unique_installations(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,99}", value) for value in values):
            raise ValueError("Installation IDs must be valid licensed installation identifiers")
        if len(values) != len(set(values)):
            raise ValueError("Duplicate installation IDs are not allowed")
        return sorted(values)


@router.get("/releases")
async def get_client_releases(
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> list[dict]:
    return await list_releases()


@router.post("/releases", status_code=201)
async def add_client_release(
    request: ClientReleaseCreate,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    """Store immutable metadata; archive private signing keys remain offline.

    The detached Ed25519 signature covers canonical UTF-8 JSON containing
    release_id, version, archive_url, archive_sha256, min_current_version,
    and notes. The archive digest binds the downloaded archive bytes.
    """
    try:
        envelope = verify_release_envelope(request.model_dump())
    except ClientUpdateProtocolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    digest = hashlib.sha256(json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    try:
        return await create_release(envelope, digest, user.id)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Release ID or version already exists") from exc


@router.post("/releases/{release_id}/publish")
async def make_client_release_available(
    release_id: str,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    release = await publish_release(release_id, user.id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release


@router.post("/rollouts", status_code=201)
async def stage_client_rollout(
    request: RolloutCreate,
    user: Annotated[UserModel, Depends(get_superuser)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=100)],
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._:-]{16,100}", idempotency_key):
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 16–100 URL-safe characters")
    fingerprint = hashlib.sha256(json.dumps(
        {"release_id": request.release_id, "installation_ids": request.installation_ids},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    try:
        rollout, created = await create_rollout(
            release_id=request.release_id,
            installation_ids=request.installation_ids,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            user_id=user.id,
        )
    except ClientReleaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        # The uniqueness constraint arbitrates concurrent idempotent requests.
        existing = await get_rollout_by_idempotency(user.id, idempotency_key)
        if existing and existing["request_fingerprint"] == fingerprint:
            return existing["rollout"]
        raise HTTPException(status_code=409, detail="Rollout idempotency key conflicts with an existing request") from exc
    return {**rollout, "created": created}


@router.get("/rollouts")
async def get_client_rollouts(
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> list[dict]:
    return await list_rollouts()


@router.get("/rollouts/{rollout_id}")
async def get_client_rollout(
    rollout_id: str,
    _user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    result = await get_rollout(rollout_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Rollout not found")
    return result


async def _transition(rollout_id: str, action: str, user: UserModel) -> dict:
    try:
        result = await transition_rollout(rollout_id, action, user.id)
    except ClientReleaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Rollout not found")
    return result


@router.post("/rollouts/{rollout_id}/activate")
async def activate_client_rollout(
    rollout_id: str,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    return await _transition(rollout_id, "activate", user)


@router.post("/rollouts/{rollout_id}/pause")
async def pause_client_rollout(
    rollout_id: str,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    return await _transition(rollout_id, "pause", user)


@router.post("/rollouts/{rollout_id}/stop")
async def stop_client_rollout(
    rollout_id: str,
    user: Annotated[UserModel, Depends(get_superuser)],
) -> dict:
    return await _transition(rollout_id, "stop", user)
