"""Deliver owner email notifications for first-seen client integrity failures."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from loguru import logger
from api.db.client_installations import list_active_platform_superadmin_emails
from api.db.kodewaves_client import kodewaves_db_client


async def notify_client_integrity_alert(
    *, installation_id: str, customer_id: str, finding: dict[str, str | None],
) -> bool:
    """Email active platform superadmins using the configured platform SMTP.

    This is best effort: status enforcement and alert persistence have already
    completed, and a mail failure must not turn an owner check into a failure.
    Repeated checks do not schedule another message for the same latched
    installation incident.
    """
    try:
        smtp = await kodewaves_db_client.get_setting("smtp") or {}
        host = smtp.get("smtp_host")
        if not isinstance(host, str) or not host.strip():
            logger.warning("Client integrity alert email skipped: platform SMTP is not configured")
            return False

        port = int(smtp.get("smtp_port") or 587)
        if not 1 <= port <= 65535:
            logger.warning("Client integrity alert email skipped: platform SMTP port is invalid")
            return False
        recipients = await list_active_platform_superadmin_emails()
        if not recipients:
            logger.warning("Client integrity alert email skipped: no active owner email is configured")
            return False

        sender = smtp.get("smtp_from") or smtp.get("smtp_user") or "noreply@kodewaves.in"
        reason = str(finding.get("reason") or "unknown")[:30]
        component = str(finding.get("component") or "release")[:500]
        message = EmailMessage()
        message["Subject"] = f"Kodewaves client integrity alert: {installation_id}"
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(
            "A licensed client installation reported a protected-release integrity failure.\n\n"
            f"Customer: {customer_id}\n"
            f"Installation: {installation_id}\n"
            f"Reason: {reason}\n"
            f"Component: {component}\n\n"
            "The installation is blocked by its integrity status. Review the alert in the Kodewaves "
            "superadmin Client Installations panel before taking action."
        )

        def send() -> None:
            server = None
            try:
                if port == 465:
                    server = smtplib.SMTP_SSL(host, port, timeout=10, context=ssl.create_default_context())
                else:
                    server = smtplib.SMTP(host, port, timeout=10)
                    server.starttls(context=ssl.create_default_context())
                username = smtp.get("smtp_user")
                password = smtp.get("smtp_password")
                if username and password:
                    server.login(username, password)
                server.send_message(message)
            finally:
                if server is not None:
                    try:
                        server.quit()
                    except Exception:  # noqa: BLE001 - preserve the send result
                        pass

        await asyncio.to_thread(send)
        return True
    except Exception as exc:  # noqa: BLE001 - mail delivery must not bypass the alert latch
        logger.warning("Client integrity alert email delivery failed: %s", type(exc).__name__)
        return False
