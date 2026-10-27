"""Owner-side persistence for commercial installation entitlements."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    ClientDomainChallengeModel,
    ClientInstallationModel,
    ClientIntegrityAlertModel,
)


async def save_domain_challenge(customer_id: str, domain: str, token_sha256: str) -> datetime:
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=24)
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientDomainChallengeModel, (customer_id, domain), with_for_update=True)
        if record is None:
            record = ClientDomainChallengeModel(
                customer_id=customer_id, domain=domain, token_sha256=token_sha256,
                expires_at=expires_at, verified_at=None, created_at=now,
            )
            session.add(record)
        else:
            record.token_sha256 = token_sha256
            record.expires_at = expires_at
            record.verified_at = None
            record.created_at = now
        await session.commit()
    return expires_at


async def get_pending_domain_challenge(customer_id: str, domain: str) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientDomainChallengeModel, (customer_id, domain))
        if record is None or record.expires_at <= datetime.now(UTC) or record.verified_at is not None:
            return None
        return {"token_sha256": record.token_sha256, "expires_at": record.expires_at}


async def mark_domain_verified(customer_id: str, domain: str, token_sha256: str) -> datetime | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientDomainChallengeModel, (customer_id, domain), with_for_update=True)
        now = datetime.now(UTC)
        if record is None or record.expires_at <= now or record.token_sha256 != token_sha256 or record.verified_at is not None:
            return None
        record.verified_at = now
        await session.commit()
        return now


async def unverified_license_domains(customer_id: str, domains: list[str]) -> list[str]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientDomainChallengeModel).where(
                ClientDomainChallengeModel.customer_id == customer_id,
                ClientDomainChallengeModel.domain.in_(domains),
            )
        )
        verified = {item.domain for item in result.scalars().all() if item.verified_at and item.verified_at >= cutoff}
    return sorted(set(domains) - verified)


async def list_client_installation_records() -> list[dict]:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientInstallationModel).order_by(ClientInstallationModel.created_at.desc())
        )
        return [
            {
                "installation_id": item.installation_id,
                "customer_id": item.customer_id,
                "domains": item.domains,
                "ip_ranges": item.ip_ranges,
                "features": item.features,
                "limits": item.limits,
                "expires_at": int(item.expires_at.timestamp()),
                "token_fingerprint": item.token_fingerprint,
                "renewed_at": item.renewed_at.isoformat() if item.renewed_at else None,
                "previous_token_valid_until": item.previous_token_valid_until.isoformat() if item.previous_token_valid_until else None,
                "created_at": item.created_at.isoformat(),
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
                "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
                "observed_ip": item.observed_ip,
                "integrity_failed_at": item.integrity_failed_at.isoformat() if item.integrity_failed_at else None,
            }
            for item in result.scalars().all()
        ]


async def create_client_installation_record(**fields) -> None:
    record = ClientInstallationModel(**fields)
    async with kodewaves_db_client.get_session() as session:
        session.add(record)
        await session.commit()


async def get_client_installation_record(installation_id: str) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientInstallationModel, installation_id)
        if record is None:
            return None
        return {
            "installation_id": record.installation_id,
            "customer_id": record.customer_id,
            "domains": record.domains,
            "ip_ranges": record.ip_ranges,
            "features": record.features,
            "limits": record.limits,
            "expires_at": int(record.expires_at.timestamp()),
            "token_fingerprint": record.token_fingerprint,
            "previous_token_valid_until": record.previous_token_valid_until,
            "revoked_at": record.revoked_at,
            "integrity_failed_at": record.integrity_failed_at,
        }


async def renew_client_installation_record(
    installation_id: str, expected_fingerprint: str, new_fingerprint: str,
    expires_at: datetime, user_id: int,
) -> bool:
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        now = datetime.now(UTC)
        if (
            record is None or record.token_fingerprint != expected_fingerprint
            or record.revoked_at is not None or record.integrity_failed_at is not None
            or (record.previous_token_valid_until is not None and record.previous_token_valid_until > now)
        ):
            return False
        record.previous_token_fingerprint = record.token_fingerprint
        record.previous_token_valid_until = min(record.expires_at, now + timedelta(hours=48))
        record.token_fingerprint = new_fingerprint
        record.expires_at = expires_at
        record.renewed_at = now
        record.renewed_by_user_id = user_id
        record.updated_at = now
        await session.commit()
        return True


async def revoke_client_installation_record(installation_id: str, user_id: int) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientInstallationModel)
            .where(ClientInstallationModel.installation_id == installation_id)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        needs_commit = record.revoked_at is None
        if needs_commit:
            record.revoked_at = datetime.now(UTC)
            record.revoked_by_user_id = user_id
            record.updated_at = record.revoked_at
        result = {
            "installation_id": record.installation_id,
            "revoked_at": record.revoked_at.isoformat(),
        }
        if needs_commit:
            await session.commit()
        return result


async def record_client_installation_check(
    installation_id: str, fingerprint: str, *, integrity_ok: bool,
    integrity_finding: dict | None = None, observed_ip: str | None = None,
) -> dict | None:
    """Record verified-client observation and latch any integrity alert."""
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientInstallationModel).where(
                ClientInstallationModel.installation_id == installation_id,
                or_(
                    ClientInstallationModel.token_fingerprint == fingerprint,
                    (
                        (ClientInstallationModel.previous_token_fingerprint == fingerprint)
                        & (ClientInstallationModel.previous_token_valid_until > datetime.now(UTC))
                    ),
                ),
            ).with_for_update()
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        now = datetime.now(UTC)
        previous_token = getattr(record, "previous_token_fingerprint", None) == fingerprint
        record.last_seen_at = now
        record.observed_ip = observed_ip
        if not integrity_ok and record.integrity_failed_at is None:
            record.integrity_failed_at = now
        if not integrity_ok:
            finding = integrity_finding or {
                "reason": "unknown", "component": "release",
                "expected_sha256": None, "observed_sha256": None,
            }
            event_fingerprint = hashlib.sha256(
                json.dumps(finding, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            statement = insert(ClientIntegrityAlertModel).values(
                installation_id=installation_id,
                event_fingerprint=event_fingerprint,
                reason=finding["reason"],
                component=finding["component"],
                expected_sha256=finding.get("expected_sha256"),
                observed_sha256=finding.get("observed_sha256"),
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=1,
            ).on_conflict_do_update(
                constraint="uq_client_integrity_alert_event",
                set_={
                    "last_seen_at": now,
                    "occurrence_count": ClientIntegrityAlertModel.occurrence_count + 1,
                },
            )
            await session.execute(statement)
        record.updated_at = now
        # SQLAlchemy expires ORM attributes on commit; capture the status while
        # the row is loaded, then return it only after the commit succeeds.
        status = {
            "installation_id": record.installation_id,
            "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
            "integrity_failed_at": record.integrity_failed_at.isoformat() if record.integrity_failed_at else None,
            "expires_at": int(
                (record.previous_token_valid_until if previous_token else record.expires_at).timestamp()
            ),
        }
        await session.commit()
        return status


async def list_client_integrity_alerts(*, include_acknowledged: bool = False) -> list[dict]:
    async with kodewaves_db_client.get_session() as session:
        query = select(ClientIntegrityAlertModel).order_by(ClientIntegrityAlertModel.last_seen_at.desc()).limit(100)
        if not include_acknowledged:
            query = query.where(ClientIntegrityAlertModel.acknowledged_at.is_(None))
        result = await session.execute(query)
        return [
            {
                "id": alert.id,
                "installation_id": alert.installation_id,
                "reason": alert.reason,
                "component": alert.component,
                "expected_sha256": alert.expected_sha256,
                "observed_sha256": alert.observed_sha256,
                "first_seen_at": alert.first_seen_at.isoformat(),
                "last_seen_at": alert.last_seen_at.isoformat(),
                "occurrence_count": alert.occurrence_count,
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            }
            for alert in result.scalars().all()
        ]


async def acknowledge_client_integrity_alert(alert_id: int, user_id: int) -> bool:
    async with kodewaves_db_client.get_session() as session:
        alert = await session.get(ClientIntegrityAlertModel, alert_id, with_for_update=True)
        if alert is None:
            return False
        if alert.acknowledged_at is None:
            alert.acknowledged_at = datetime.now(UTC)
            alert.acknowledged_by_user_id = user_id
            await session.commit()
        return True
