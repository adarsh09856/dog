from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api.services import client_integrity_notifications as notifications


@pytest.mark.asyncio
async def test_integrity_notification_emails_only_active_owner_recipients(monkeypatch):
    monkeypatch.setattr(notifications.kodewaves_db_client, "get_setting", AsyncMock(return_value={
        "smtp_host": "smtp.example.com", "smtp_port": 587,
        "smtp_user": "mailer@example.com", "smtp_password": "secret",
        "smtp_from": "alerts@example.com",
    }))
    monkeypatch.setattr(notifications, "list_active_platform_superadmin_emails", AsyncMock(
        return_value=["owner@example.com", "second@example.com"],
    ))
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["connection"] = (host, port, timeout)

        def starttls(self, *, context):
            sent["tls"] = context

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

        def quit(self):
            sent["quit"] = True

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

    delivered = await notifications.notify_client_integrity_alert(
        installation_id="client-123", customer_id="customer-123",
        finding={"reason": "modified_file", "component": "api/app.py"},
    )

    assert delivered is True
    assert sent["connection"] == ("smtp.example.com", 587, 10)
    assert sent["login"] == ("mailer@example.com", "secret")
    assert sent["quit"] is True
    message = sent["message"]
    assert message["To"] == "owner@example.com, second@example.com"
    assert message["Subject"] == "Kodewaves client integrity alert: client-123"
    assert "customer-123" in message.get_content()
    assert "modified_file" in message.get_content()
    assert "api/app.py" in message.get_content()
    assert "secret" not in message.get_content()


@pytest.mark.asyncio
async def test_integrity_notification_skips_cleanly_without_smtp(monkeypatch):
    monkeypatch.setattr(
        notifications.kodewaves_db_client, "get_setting", AsyncMock(return_value=None),
    )
    get_recipients = AsyncMock()
    monkeypatch.setattr(notifications, "list_active_platform_superadmin_emails", get_recipients)

    delivered = await notifications.notify_client_integrity_alert(
        installation_id="client-123", customer_id="customer-123",
        finding={"reason": "modified_file", "component": "api/app.py"},
    )

    assert delivered is False
    get_recipients.assert_not_awaited()
