"""Create the first client administrator from an interactive installation console."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from api.constants import AUTH_PROVIDER, KODEWAVES_EDITION
from api.db import db_client
from api.db.models import (
    OrganizationModel,
    UserModel,
    organization_users_association,
)
from api.services.client_creation_limits import enforce_client_creation_limit
from api.services.installation_license import (
    load_license,
    validate_installation_license,
)
from api.services.release_integrity import verify_configured_release
from api.utils.auth import hash_password


async def bootstrap_client_admin(email: str, password: str) -> int:
    """Atomically create the first local account, workspace, and membership."""
    if KODEWAVES_EDITION != "client" or AUTH_PROVIDER != "local":
        raise ValueError(
            "Bootstrap requires a client installation with local authentication"
        )
    normalized_email = email.strip().lower()
    if (
        not normalized_email
        or "@" not in normalized_email
        or any(c.isspace() for c in normalized_email)
    ):
        raise ValueError("Enter a valid administrator email")
    if len(password) < 12:
        raise ValueError("Administrator password must contain at least 12 characters")

    license_data = load_license()
    validate_installation_license(license_data)
    verify_configured_release()
    provider_id = f"oss_bootstrap_{uuid.uuid4()}"
    password_hash = hash_password(password)

    async with db_client.async_session() as session, session.begin():
        await session.execute(text("SELECT pg_advisory_xact_lock(492565710843)"))
        users = (await session.execute(select(func.count(UserModel.id)))).scalar_one()
        organizations = (
            await session.execute(select(func.count(OrganizationModel.id)))
        ).scalar_one()
        if users or organizations:
            raise ValueError(
                "Bootstrap is available only before the first account and workspace"
            )
        await enforce_client_creation_limit(
            session, limit_name="max_seats", model=UserModel
        )
        await enforce_client_creation_limit(
            session, limit_name="max_workspaces", model=OrganizationModel
        )

        user = UserModel(
            provider_id=provider_id,
            email=normalized_email,
            password_hash=password_hash,
            is_superuser=True,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        organization = OrganizationModel(
            provider_id=f"org_{provider_id}", created_at=datetime.now(UTC)
        )
        session.add(organization)
        await session.flush()
        await session.execute(
            organization_users_association.insert().values(
                user_id=user.id, organization_id=organization.id
            )
        )
        user.selected_organization_id = organization.id
        administrator_id = user.id
    return administrator_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email", required=True, help="First client administrator email"
    )
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error(
            "Bootstrap requires an interactive terminal for the password prompt"
        )
    password = getpass.getpass("Administrator password: ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    administrator_id = asyncio.run(bootstrap_client_admin(args.email, password))
    print(f"Client administrator created (user ID {administrator_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
