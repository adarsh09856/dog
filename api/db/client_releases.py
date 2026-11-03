"""Persistence for owner-managed, signed client releases and staged rollouts."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    ClientInstallationModel,
    ClientInstallationNonceModel,
    ClientReleaseCatalogModel,
    ClientReleaseRolloutModel,
    ClientReleaseRolloutTargetModel,
)
from api.services.client_update_protocol import (
    release_update_is_eligible,
    update_report_transition_allowed,
)


class ClientReleaseConflict(ValueError):
    """A release/rollout operation conflicts with immutable or active state."""


def _release_dict(record: ClientReleaseCatalogModel) -> dict:
    return {
        "release_id": record.release_id,
        "version": record.version,
        "archive_url": record.archive_url,
        "archive_sha256": record.archive_sha256,
        "archive_signature": record.archive_signature,
        "min_current_version": record.min_current_version,
        "notes": record.notes,
        "signed_envelope": record.signed_envelope,
        "state": record.state,
        "created_by_user_id": record.created_by_user_id,
        "published_by_user_id": record.published_by_user_id,
        "created_at": record.created_at.isoformat(),
        "published_at": record.published_at.isoformat() if record.published_at else None,
    }


def _rollout_dict(record: ClientReleaseRolloutModel, targets: list[ClientReleaseRolloutTargetModel]) -> dict:
    return {
        "rollout_id": record.rollout_id,
        "release_id": record.release_id,
        "state": record.state,
        "created_by_user_id": record.created_by_user_id,
        "updated_by_user_id": record.updated_by_user_id,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "paused_at": record.paused_at.isoformat() if record.paused_at else None,
        "stopped_at": record.stopped_at.isoformat() if record.stopped_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "targets": [
            {
                "installation_id": target.installation_id,
                "status": target.status,
                "current_version": target.current_version,
                "detail": target.detail,
                "last_reported_at": target.last_reported_at.isoformat() if target.last_reported_at else None,
            }
            for target in targets
        ],
    }


async def create_release(envelope: dict[str, str], envelope_sha256: str, user_id: int) -> dict:
    now = datetime.now(UTC)
    async with kodewaves_db_client.get_session() as session:
        record = ClientReleaseCatalogModel(
            release_id=envelope["release_id"], version=envelope["version"],
            archive_url=envelope["archive_url"], archive_sha256=envelope["archive_sha256"],
            archive_signature=envelope["archive_signature"],
            min_current_version=envelope["min_current_version"], notes=envelope["notes"],
            signed_envelope=envelope, envelope_sha256=envelope_sha256, state="draft",
            created_by_user_id=user_id, created_at=now,
        )
        session.add(record)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        await session.refresh(record)
        return _release_dict(record)


async def list_releases() -> list[dict]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(ClientReleaseCatalogModel).order_by(ClientReleaseCatalogModel.created_at.desc()))
        return [_release_dict(row) for row in result.scalars().all()]


async def publish_release(release_id: str, user_id: int) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientReleaseCatalogModel, release_id, with_for_update=True)
        if record is None:
            return None
        if record.state == "published":
            return _release_dict(record)
        now = datetime.now(UTC)
        record.state = "published"
        record.published_by_user_id = user_id
        record.published_at = now
        await session.commit()
        await session.refresh(record)
        return _release_dict(record)


async def create_rollout(
    *, release_id: str, installation_ids: list[str], idempotency_key: str,
    request_fingerprint: str, user_id: int,
) -> tuple[dict, bool]:
    now = datetime.now(UTC)
    ids = sorted(set(installation_ids))
    async with kodewaves_db_client.get_session() as session:
        existing = await session.scalar(select(ClientReleaseRolloutModel).where(
            ClientReleaseRolloutModel.created_by_user_id == user_id,
            ClientReleaseRolloutModel.idempotency_key == idempotency_key,
        ))
        if existing:
            if existing.request_fingerprint != request_fingerprint:
                raise ClientReleaseConflict("Idempotency key was already used for a different request")
            targets_result = await session.execute(select(ClientReleaseRolloutTargetModel).where(
                ClientReleaseRolloutTargetModel.rollout_id == existing.rollout_id
            ).order_by(ClientReleaseRolloutTargetModel.installation_id))
            return _rollout_dict(existing, list(targets_result.scalars().all())), False

        release = await session.get(ClientReleaseCatalogModel, release_id)
        if release is None or release.state != "published":
            raise ClientReleaseConflict("Rollouts require a published release")
        result = await session.execute(
            select(ClientInstallationModel)
            .where(ClientInstallationModel.installation_id.in_(ids))
            .order_by(ClientInstallationModel.installation_id)
            .with_for_update()
        )
        installations = list(result.scalars().all())
        if len(installations) != len(ids):
            raise ClientReleaseConflict("Every target must be a known licensed installation")
        if any(
            item.revoked_at is not None or item.integrity_failed_at is not None
            or item.expires_at <= now or item.enrolled_at is None
            or not item.installation_public_key
            for item in installations
        ):
            raise ClientReleaseConflict("Targets must be active, enrolled, non-revoked licensed installations")
        unresolved = await session.scalar(
            select(func.count()).select_from(ClientReleaseRolloutTargetModel)
            .join(ClientReleaseRolloutModel, ClientReleaseRolloutModel.rollout_id == ClientReleaseRolloutTargetModel.rollout_id)
            .where(
                ClientReleaseRolloutTargetModel.installation_id.in_(ids),
                or_(
                    ClientReleaseRolloutModel.state.in_(["staged", "active", "paused"]),
                    and_(
                        ClientReleaseRolloutModel.state == "stopped",
                        ClientReleaseRolloutTargetModel.status == "applying",
                    ),
                ),
            )
        )
        if unresolved:
            raise ClientReleaseConflict("A target already belongs to a pending rollout")
        rollout = ClientReleaseRolloutModel(
            rollout_id=str(uuid.uuid4()), release_id=release_id, state="staged",
            idempotency_key=idempotency_key, request_fingerprint=request_fingerprint,
            created_by_user_id=user_id, updated_by_user_id=user_id,
            created_at=now, updated_at=now,
        )
        session.add(rollout)
        targets = [ClientReleaseRolloutTargetModel(
            rollout_id=rollout.rollout_id, installation_id=installation_id,
            status="staged", detail="", created_at=now, updated_at=now,
        ) for installation_id in ids]
        session.add_all(targets)
        await session.commit()
        await session.refresh(rollout)
        persisted_targets = await session.execute(select(ClientReleaseRolloutTargetModel).where(
            ClientReleaseRolloutTargetModel.rollout_id == rollout.rollout_id
        ).order_by(ClientReleaseRolloutTargetModel.installation_id))
        return _rollout_dict(rollout, list(persisted_targets.scalars().all())), True


async def list_rollouts() -> list[dict]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(select(ClientReleaseRolloutModel).order_by(ClientReleaseRolloutModel.created_at.desc()))
        rollouts = list(result.scalars().all())
        if not rollouts:
            return []
        target_result = await session.execute(select(ClientReleaseRolloutTargetModel).where(
            ClientReleaseRolloutTargetModel.rollout_id.in_([row.rollout_id for row in rollouts])
        ).order_by(ClientReleaseRolloutTargetModel.installation_id))
        targets_by_rollout: dict[str, list[ClientReleaseRolloutTargetModel]] = {}
        for target in target_result.scalars().all():
            targets_by_rollout.setdefault(target.rollout_id, []).append(target)
        return [_rollout_dict(row, targets_by_rollout.get(row.rollout_id, [])) for row in rollouts]


async def get_rollout_by_idempotency(user_id: int, idempotency_key: str) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.scalar(select(ClientReleaseRolloutModel).where(
            ClientReleaseRolloutModel.created_by_user_id == user_id,
            ClientReleaseRolloutModel.idempotency_key == idempotency_key,
        ))
        if record is None:
            return None
        target_result = await session.execute(select(ClientReleaseRolloutTargetModel).where(
            ClientReleaseRolloutTargetModel.rollout_id == record.rollout_id
        ).order_by(ClientReleaseRolloutTargetModel.installation_id))
        return {
            "request_fingerprint": record.request_fingerprint,
            "rollout": _rollout_dict(record, list(target_result.scalars().all())),
        }


async def get_rollout(rollout_id: str) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientReleaseRolloutModel, rollout_id)
        if record is None:
            return None
        result = await session.execute(select(ClientReleaseRolloutTargetModel).where(
            ClientReleaseRolloutTargetModel.rollout_id == rollout_id
        ).order_by(ClientReleaseRolloutTargetModel.installation_id))
        return _rollout_dict(record, list(result.scalars().all()))


async def transition_rollout(rollout_id: str, action: str, user_id: int) -> dict | None:
    allowed = {
        "activate": {"staged", "paused"},
        "pause": {"active"},
        "stop": {"staged", "active", "paused"},
    }
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientReleaseRolloutModel, rollout_id, with_for_update=True)
        if record is None:
            return None
        target_state = {"activate": "active", "pause": "paused", "stop": "stopped"}[action]
        if record.state != target_state and record.state not in allowed[action]:
            raise ClientReleaseConflict(f"Cannot {action} a rollout in {record.state} state")
        now = datetime.now(UTC)
        record.state = target_state
        record.updated_by_user_id = user_id
        record.updated_at = now
        if action == "activate" and record.started_at is None:
            record.started_at = now
        elif action == "pause":
            record.paused_at = now
        elif action == "stop":
            record.stopped_at = now
        await session.commit()
        await session.refresh(record)
        result = await session.execute(select(ClientReleaseRolloutTargetModel).where(
            ClientReleaseRolloutTargetModel.rollout_id == rollout_id
        ).order_by(ClientReleaseRolloutTargetModel.installation_id))
        return _rollout_dict(record, list(result.scalars().all()))


async def pending_update(installation_id: str, current_version: str) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientReleaseRolloutModel, ClientReleaseCatalogModel, ClientReleaseRolloutTargetModel)
            .join(ClientReleaseCatalogModel, ClientReleaseCatalogModel.release_id == ClientReleaseRolloutModel.release_id)
            .join(ClientReleaseRolloutTargetModel, ClientReleaseRolloutTargetModel.rollout_id == ClientReleaseRolloutModel.rollout_id)
            .where(
                ClientReleaseRolloutTargetModel.installation_id == installation_id,
                ClientReleaseRolloutModel.state.in_(("active", "paused", "stopped")),
                ClientReleaseCatalogModel.state == "published",
            ).order_by(ClientReleaseRolloutModel.created_at.desc()).limit(1)
        )
        row = result.first()
        if row is None:
            return None
        rollout, release, target = row
        # Pausing/stopping prevents new updates from starting. A target that
        # already entered applying must still receive the signed rollout state
        # so it can stop before activation or report its terminal result.
        if rollout.state != "active" and target.status != "applying":
            return None
        if target.status in {"applied", "failed", "rolled_back"}:
            return None
        signed_envelope = dict(release.signed_envelope)
        retry_applied_report = (
            target.status == "applying" and current_version == release.version
        )
        if not retry_applied_report and not release_update_is_eligible(current_version, signed_envelope):
            return None
        signed_envelope["rollout_id"] = rollout.rollout_id
        signed_envelope["target_status"] = target.status
        signed_envelope["rollout_state"] = rollout.state
        return signed_envelope


async def report_update_status(
    *, installation_id: str, license_fingerprint: str, public_key: str,
    rollout_id: str, release_id: str, version: str, nonce_fingerprint: str,
    nonce_expires_at: datetime, status: str, detail: str,
) -> dict | None:
    now = datetime.now(UTC)
    async with kodewaves_db_client.get_session() as session:
        installation = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        if (
            installation is None or installation.installation_public_key != public_key
            or installation.revoked_at is not None or installation.integrity_failed_at is not None
            or installation.expires_at <= now
        ):
            return None
        valid_token = installation.token_fingerprint == license_fingerprint or (
            installation.previous_token_fingerprint == license_fingerprint
            and installation.previous_token_valid_until is not None
            and installation.previous_token_valid_until > now
        )
        if not valid_token:
            return None
        rollout = await session.get(ClientReleaseRolloutModel, rollout_id, with_for_update=True)
        if rollout is None or rollout.release_id != release_id:
            return None
        release = await session.get(ClientReleaseCatalogModel, release_id)
        if release is None or release.state != "published" or release.version != version:
            return None
        target = await session.get(ClientReleaseRolloutTargetModel, (rollout_id, installation_id), with_for_update=True)
        if target is None:
            return None
        if target.status == status:
            # Duplicate retries remain safe and do not consume a second nonce.
            return {"accepted": True, "status": target.status, "rollout_id": rollout_id}
        newer_rollout_exists = bool(await session.scalar(
            select(func.count()).select_from(ClientReleaseRolloutTargetModel)
            .join(ClientReleaseRolloutModel, ClientReleaseRolloutModel.rollout_id == ClientReleaseRolloutTargetModel.rollout_id)
            .where(
                ClientReleaseRolloutTargetModel.installation_id == installation_id,
                ClientReleaseRolloutModel.created_at > rollout.created_at,
            )
        ))
        if not update_report_transition_allowed(
            rollout_state=rollout.state,
            current_status=target.status,
            requested_status=status,
            has_newer_rollout=newer_rollout_exists,
        ):
            return None
        if status == "staged":
            return None
        if not nonce_fingerprint or nonce_expires_at <= now:
            return None
        await session.execute(delete(ClientInstallationNonceModel).where(
            ClientInstallationNonceModel.installation_id == installation_id,
            ClientInstallationNonceModel.expires_at <= now,
        ))
        inserted = await session.execute(insert(ClientInstallationNonceModel).values(
            installation_id=installation_id,
            nonce_fingerprint=nonce_fingerprint,
            expires_at=nonce_expires_at,
        ).on_conflict_do_nothing(index_elements=["installation_id", "nonce_fingerprint"]))
        if inserted.rowcount != 1:
            return None
        target.status = status
        target.detail = detail
        target.last_reported_at = now
        target.updated_at = now
        if status == "applied":
            target.current_version = release.version
        if rollout.state in {"active", "paused"} and status in {"applied", "failed", "rolled_back"}:
            active_count = await session.scalar(select(func.count()).select_from(ClientReleaseRolloutTargetModel).where(
                ClientReleaseRolloutTargetModel.rollout_id == rollout_id,
                ClientReleaseRolloutTargetModel.status.notin_(["applied", "failed", "rolled_back"]),
                ClientReleaseRolloutTargetModel.installation_id != installation_id,
            ))
            if not active_count:
                # A paused target may be allowed to finish after it had
                # already entered applying. Once every target is terminal,
                # close the rollout so it cannot block the installation's
                # next staged release indefinitely.
                rollout.state = "completed"
                rollout.completed_at = now
                rollout.updated_at = now
        accepted_status = target.status
        await session.commit()
        return {"accepted": True, "status": accepted_status, "rollout_id": rollout_id}
