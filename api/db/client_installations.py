"""Owner-side persistence for commercial installation entitlements."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from api.db.kodewaves_client import kodewaves_db_client
from api.db.kodewaves_models import (
    ClientDomainChallengeModel,
    ClientBindingRequestModel,
    ClientInstallationModel,
    ClientInstallationNonceModel,
    ClientIntegrityAlertModel,
)
from api.db.models import UserModel


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
                "feature_version": item.feature_version,
                "entitlement_version": item.entitlement_version,
                "limits": item.limits,
                "expires_at": int(item.expires_at.timestamp()),
                "token_fingerprint": item.token_fingerprint,
                "identity_enrolled": item.installation_public_key is not None,
                "enrollment_expires_at": item.enrollment_expires_at.isoformat() if item.enrollment_expires_at else None,
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


def _utc(value: datetime) -> datetime:
    """Treat naive test/legacy timestamps as UTC; PostgreSQL stores UTC offsets."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def issue_installation_enrollment(installation_id: str, token_fingerprint: str) -> datetime | None:
    """Replace a pending token and return its expiry; never rebind an enrolled key."""
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        now = datetime.now(UTC)
        if (
            record is None or record.revoked_at is not None or record.integrity_failed_at is not None
            or record.installation_public_key is not None or _utc(record.expires_at) <= now
        ):
            return None
        expires_at = min(now + timedelta(minutes=15), _utc(record.expires_at))
        record.enrollment_token_fingerprint = token_fingerprint
        record.enrollment_expires_at = expires_at
        record.updated_at = now
        await session.commit()
        return expires_at


async def consume_installation_enrollment(
    installation_id: str, license_fingerprint: str, token_fingerprint: str, public_key: str,
) -> bool:
    """Atomically consume a pending token and bind one installation public key."""
    async with kodewaves_db_client.get_session() as session:
        record = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        now = datetime.now(UTC)
        if (
            record is None or record.revoked_at is not None or record.integrity_failed_at is not None
            or record.installation_public_key is not None or record.enrollment_expires_at is None
            or _utc(record.enrollment_expires_at) <= now or _utc(record.expires_at) <= now
            or not record.enrollment_token_fingerprint
            or not hmac.compare_digest(record.enrollment_token_fingerprint, token_fingerprint)
            or not hmac.compare_digest(record.token_fingerprint, license_fingerprint)
        ):
            return False
        record.installation_public_key = public_key
        record.enrollment_token_fingerprint = None
        record.enrollment_expires_at = None
        record.enrolled_at = now
        record.updated_at = now
        await session.commit()
        return True


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
            "feature_version": record.feature_version,
            "entitlement_version": record.entitlement_version,
            "limits": record.limits,
            "expires_at": int(record.expires_at.timestamp()),
            "token_fingerprint": record.token_fingerprint,
            "installation_public_key": record.installation_public_key,
            "previous_token_valid_until": record.previous_token_valid_until,
            "revoked_at": record.revoked_at,
            "integrity_failed_at": record.integrity_failed_at,
        }


async def renew_client_installation_record(
    installation_id: str, expected_fingerprint: str, new_fingerprint: str,
    expires_at: datetime, user_id: int, *,
    features: list[str] | None = None, feature_version: int | None = None,
    limits: dict[str, int] | None = None,
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
        record.previous_token_valid_until = min(_utc(record.expires_at), now + timedelta(hours=48))
        record.token_fingerprint = new_fingerprint
        record.expires_at = expires_at
        if features is not None:
            record.features = features
        if feature_version is not None:
            record.feature_version = feature_version
        if limits is not None:
            record.limits = limits
        record.entitlement_version += 1
        record.renewed_at = now
        record.renewed_by_user_id = user_id
        record.updated_at = now
        await session.commit()
        return True


async def create_client_binding_request(
    *, installation_id: str, token_fingerprint: str, public_key: str,
    nonce_fingerprint: str, nonce_expires_at: datetime, domains: list[str],
    ip_ranges: list[str], reason: str,
) -> dict | None:
    """Persist one fresh signed request for an enrolled, active installation."""
    async with kodewaves_db_client.get_session() as session:
        installation = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        now = datetime.now(UTC)
        if (
            installation is None
            or installation.installation_public_key != public_key
            or installation.revoked_at is not None
            or installation.integrity_failed_at is not None
            or _utc(installation.expires_at) <= now
            or _utc(nonce_expires_at) <= now
        ):
            return None
        current_token = hmac.compare_digest(installation.token_fingerprint, token_fingerprint)
        previous_token = bool(
            installation.previous_token_fingerprint
            and installation.previous_token_valid_until
            and _utc(installation.previous_token_valid_until) > now
            and hmac.compare_digest(installation.previous_token_fingerprint, token_fingerprint)
        )
        if not (current_token or previous_token):
            return None
        await session.execute(delete(ClientInstallationNonceModel).where(
            ClientInstallationNonceModel.installation_id == installation_id,
            ClientInstallationNonceModel.expires_at <= now,
        ))
        inserted = await session.execute(
            insert(ClientInstallationNonceModel).values(
                installation_id=installation_id,
                nonce_fingerprint=nonce_fingerprint,
                expires_at=nonce_expires_at,
            ).on_conflict_do_nothing(index_elements=["installation_id", "nonce_fingerprint"])
        )
        if inserted.rowcount != 1:
            return None
        pending = await session.execute(select(ClientBindingRequestModel.id).where(
            ClientBindingRequestModel.installation_id == installation_id,
            ClientBindingRequestModel.status == "pending",
        ).limit(1))
        if pending.scalar_one_or_none() is not None:
            # Consume a valid proof even when another request is pending. Otherwise
            # the same signed submission can be replayed after that request resolves.
            await session.commit()
            return {"conflict": True}
        request = ClientBindingRequestModel(
            installation_id=installation_id,
            requested_domains=domains,
            requested_ip_ranges=ip_ranges,
            reason=reason,
            status="pending",
            created_at=now,
        )
        session.add(request)
        await session.flush()
        result = {
            "id": request.id,
            "installation_id": installation_id,
            "requested_domains": domains,
            "requested_ip_ranges": ip_ranges,
            "reason": reason,
            "status": "pending",
            "created_at": now.isoformat(),
        }
        await session.commit()
        return result


async def get_client_binding_request(request_id: int) -> dict | None:
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientBindingRequestModel, ClientInstallationModel.customer_id)
            .join(ClientInstallationModel)
            .where(ClientBindingRequestModel.id == request_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        request, customer_id = row
        return {
            "id": request.id,
            "installation_id": request.installation_id,
            "customer_id": customer_id,
            "requested_domains": request.requested_domains,
            "requested_ip_ranges": request.requested_ip_ranges,
            "reason": request.reason,
            "status": request.status,
            "created_at": request.created_at.isoformat(),
            "resolved_at": request.resolved_at.isoformat() if request.resolved_at else None,
            "resolved_by_user_id": request.resolved_by_user_id,
            "license_issued_at": request.license_issued_at,
        }


async def list_client_binding_requests(*, include_resolved: bool = False) -> list[dict]:
    async with kodewaves_db_client.get_session() as session:
        query = (
            select(ClientBindingRequestModel, ClientInstallationModel.customer_id)
            .join(ClientInstallationModel)
            .order_by(ClientBindingRequestModel.created_at.desc())
            .limit(200)
        )
        if not include_resolved:
            query = query.where(ClientBindingRequestModel.status == "pending")
        result = await session.execute(query)
        return [
            {
                "id": request.id,
                "installation_id": request.installation_id,
                "customer_id": customer_id,
                "requested_domains": request.requested_domains,
                "requested_ip_ranges": request.requested_ip_ranges,
                "reason": request.reason,
                "status": request.status,
                "created_at": request.created_at.isoformat(),
                "resolved_at": request.resolved_at.isoformat() if request.resolved_at else None,
                "resolved_by_user_id": request.resolved_by_user_id,
                "license_issued_at": request.license_issued_at,
            }
            for request, customer_id in result.all()
        ]


async def resolve_client_binding_request(
    request_id: int, *, outcome: str, user_id: int, expected_fingerprint: str | None = None,
    new_fingerprint: str | None = None, domains: list[str] | None = None,
    ip_ranges: list[str] | None = None, license_issued_at: int | None = None,
) -> bool:
    """Resolve once; approval rotates the license and binding atomically."""
    if outcome not in {"approved", "rejected"}:
        raise ValueError("Invalid binding request outcome")
    async with kodewaves_db_client.get_session() as session:
        installation_id = await session.scalar(
            select(ClientBindingRequestModel.installation_id).where(ClientBindingRequestModel.id == request_id)
        )
        if installation_id is None:
            return False
        # All binding mutations lock the installation before the request.
        installation = await session.get(ClientInstallationModel, installation_id, with_for_update=True)
        request = await session.get(ClientBindingRequestModel, request_id, with_for_update=True)
        if request is None or request.status != "pending":
            return False
        now = datetime.now(UTC)
        if outcome == "approved":
            if (
                not expected_fingerprint or not new_fingerprint or domains is None
                or ip_ranges is None or license_issued_at is None
            ):
                raise ValueError("Approval requires signed replacement binding data")
            if (
                installation is None
                or request.requested_domains != domains
                or request.requested_ip_ranges != ip_ranges
                or installation.token_fingerprint != expected_fingerprint
                or installation.revoked_at is not None
                or installation.integrity_failed_at is not None
                or _utc(installation.expires_at) <= now
                or (
                    installation.previous_token_valid_until is not None
                    and _utc(installation.previous_token_valid_until) > now
                )
            ):
                return False
            installation.previous_token_fingerprint = installation.token_fingerprint
            installation.previous_token_valid_until = min(_utc(installation.expires_at), now + timedelta(hours=48))
            installation.token_fingerprint = new_fingerprint
            installation.domains = domains
            installation.ip_ranges = ip_ranges
            installation.renewed_at = now
            installation.renewed_by_user_id = user_id
            installation.updated_at = now
        request.status = outcome
        request.license_issued_at = license_issued_at
        request.resolved_at = now
        request.resolved_by_user_id = user_id
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
    expected_public_key: str | None = None, nonce_fingerprint: str | None = None,
    nonce_expires_at: datetime | None = None,
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
        if (
            record is None
            or not expected_public_key
            or record.installation_public_key != expected_public_key
        ):
            return None
        now = datetime.now(UTC)
        integrity_alert_notification = (
            not integrity_ok and record.integrity_failed_at is None
        )
        integrity_alert_notification_id = None
        if expected_public_key is not None:
            if not nonce_fingerprint or nonce_expires_at is None or _utc(nonce_expires_at) <= now:
                return None
            await session.execute(delete(ClientInstallationNonceModel).where(
                ClientInstallationNonceModel.installation_id == installation_id,
                ClientInstallationNonceModel.expires_at <= now,
            ))
            inserted = await session.execute(
                insert(ClientInstallationNonceModel).values(
                    installation_id=installation_id, nonce_fingerprint=nonce_fingerprint,
                    expires_at=nonce_expires_at,
                ).on_conflict_do_nothing(
                    index_elements=["installation_id", "nonce_fingerprint"]
                )
            )
            if inserted.rowcount != 1:
                return None
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
                email_status="pending",
                email_attempt_count=0,
                email_scheduled_for=now,
            ).on_conflict_do_update(
                constraint="uq_client_integrity_alert_event",
                set_={
                    "last_seen_at": now,
                    "occurrence_count": ClientIntegrityAlertModel.occurrence_count + 1,
                    # A repeated tamper event after acknowledgement is active
                    # again and must return to the owner's unacknowledged queue.
                    "acknowledged_at": None,
                    "acknowledged_by_user_id": None,
                },
            )
            alert_result = await session.execute(
                statement.returning(ClientIntegrityAlertModel.id)
            )
            integrity_alert_notification_id = alert_result.scalar_one_or_none()
        record.updated_at = now
        # SQLAlchemy expires ORM attributes on commit; capture the status while
        # the row is loaded, then return it only after the commit succeeds.
        status = {
            "installation_id": record.installation_id,
            "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
            "integrity_failed_at": record.integrity_failed_at.isoformat() if record.integrity_failed_at else None,
            "integrity_alert_notification": integrity_alert_notification,
            "integrity_alert_notification_id": (
                integrity_alert_notification_id if integrity_alert_notification else None
            ),
            "expires_at": int(
                (record.previous_token_valid_until if previous_token else record.expires_at).timestamp()
            ),
            "features": sorted(record.features),
            "feature_version": record.feature_version,
            "limits": dict(record.limits),
            "entitlement_version": record.entitlement_version,
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
                "email_status": alert.email_status,
                "email_attempt_count": alert.email_attempt_count,
                "email_last_attempt_at": (
                    alert.email_last_attempt_at.isoformat() if alert.email_last_attempt_at else None
                ),
                "email_sent_at": alert.email_sent_at.isoformat() if alert.email_sent_at else None,
                "email_last_error": alert.email_last_error,
            }
            for alert in result.scalars().all()
        ]


async def claim_client_integrity_alert_email(alert_id: int, *, lease_seconds: int = 90) -> dict | None:
    """Atomically claim one due alert email and return its mail payload.

    The persisted lease prevents duplicate ARQ jobs from sending concurrently.
    If a worker dies, ``email_scheduled_for`` expires and the sweeper can reclaim it.
    SMTP is at-least-once: a crash after server acceptance but before success is
    recorded may cause one duplicate notification after lease expiry.
    """
    now = datetime.now(UTC)
    async with kodewaves_db_client.get_session() as session:
        claimed = await session.execute(
            update(ClientIntegrityAlertModel)
            .where(
                ClientIntegrityAlertModel.id == alert_id,
                ClientIntegrityAlertModel.email_status.in_(("pending", "sending")),
                ClientIntegrityAlertModel.email_scheduled_for.is_not(None),
                ClientIntegrityAlertModel.email_scheduled_for <= now,
            )
            .values(
                email_status="sending",
                email_attempt_count=ClientIntegrityAlertModel.email_attempt_count + 1,
                email_last_attempt_at=now,
                email_scheduled_for=now + timedelta(seconds=lease_seconds),
                email_last_error=None,
            )
            .returning(ClientIntegrityAlertModel.id)
        )
        if claimed.scalar_one_or_none() is None:
            await session.rollback()
            return None
        result = await session.execute(
            select(ClientIntegrityAlertModel, ClientInstallationModel.customer_id)
            .join(
                ClientInstallationModel,
                ClientInstallationModel.installation_id == ClientIntegrityAlertModel.installation_id,
            )
            .where(ClientIntegrityAlertModel.id == alert_id)
        )
        row = result.one_or_none()
        if row is None:
            await session.commit()
            return None
        alert, customer_id = row
        # Async sessions expire ORM attributes on commit. Materialize the task
        # payload while the selected row is still loaded, then commit the lease.
        payload = {
            "id": alert.id,
            "installation_id": alert.installation_id,
            "customer_id": customer_id,
            "reason": alert.reason,
            "component": alert.component,
            "expected_sha256": alert.expected_sha256,
            "observed_sha256": alert.observed_sha256,
            "attempt_count": alert.email_attempt_count,
        }
        await session.commit()
        return payload


async def mark_client_integrity_alert_email_sent(alert_id: int) -> None:
    now = datetime.now(UTC)
    async with kodewaves_db_client.get_session() as session:
        await session.execute(
            update(ClientIntegrityAlertModel)
            .where(ClientIntegrityAlertModel.id == alert_id, ClientIntegrityAlertModel.email_status == "sending")
            .values(
                email_status="sent", email_sent_at=now, email_scheduled_for=None,
                email_last_error=None,
            )
        )
        await session.commit()


async def schedule_client_integrity_alert_email_retry(
    alert_id: int, *, retry_at: datetime, error_code: str, terminal: bool = False,
) -> None:
    """Record a safe error code and schedule retry or terminal failure."""
    async with kodewaves_db_client.get_session() as session:
        await session.execute(
            update(ClientIntegrityAlertModel)
            .where(ClientIntegrityAlertModel.id == alert_id, ClientIntegrityAlertModel.email_status == "sending")
            .values(
                email_status="failed" if terminal else "pending",
                email_scheduled_for=None if terminal else retry_at,
                email_last_error=error_code[:80],
            )
        )
        await session.commit()


async def get_due_client_integrity_alert_emails(
    *, now: datetime | None = None, limit: int = 100, after_id: int = 0,
) -> list[dict]:
    cutoff = now or datetime.now(UTC)
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(ClientIntegrityAlertModel.id, ClientIntegrityAlertModel.email_attempt_count)
            .where(
                ClientIntegrityAlertModel.email_status.in_(("pending", "sending")),
                ClientIntegrityAlertModel.email_scheduled_for.is_not(None),
                ClientIntegrityAlertModel.email_scheduled_for <= cutoff,
                ClientIntegrityAlertModel.id > after_id,
            )
            .order_by(ClientIntegrityAlertModel.id)
            .limit(limit)
        )
        return [
            {"id": row.id, "attempt_count": row.email_attempt_count}
            for row in result.all()
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


async def list_active_platform_superadmin_emails() -> list[str]:
    """Return normalized recipient addresses for active platform superadmins."""
    async with kodewaves_db_client.get_session() as session:
        result = await session.execute(
            select(UserModel.email).where(
                UserModel.is_superuser.is_(True),
                UserModel.is_active.is_(True),
                UserModel.email.is_not(None),
            )
        )
        return sorted({
            address.strip() for address in result.scalars().all()
            if isinstance(address, str) and address.strip()
        })
