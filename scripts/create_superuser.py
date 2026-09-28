"""
Kodewaves Sovereign Voice AI — Superadmin Account Creation Script
Usage:
    python -m scripts.create_superuser --email admin@example.com --password mysecretpass --name "Super Admin"
Or via environment variables:
    ADMIN_EMAIL and ADMIN_PASSWORD
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import select

from api.db import db_client
from api.db.models import UserModel
from api.services.organization_bootstrap import ensure_organization_bootstrapped
from api.utils.auth import hash_password


async def create_or_promote_superuser(
    email: str,
    password: str,
    name: str = "Super Admin",
) -> UserModel:
    email = email.lower().strip()
    user = await db_client.get_user_by_email(email)

    if user:
        print(f"[INFO] User '{email}' already exists. Ensuring superuser privileges...")
        async with db_client.async_session() as session:
            stmt = select(UserModel).where(UserModel.id == user.id)
            res = await session.execute(stmt)
            u = res.scalar_one()
            u.is_superuser = True
            if password:
                u.password_hash = hash_password(password)
            await session.commit()
        print(f"[SUCCESS] User '{email}' has been promoted to Superadmin.")
        return user

    # Create new superadmin user
    hashed = hash_password(password)
    user = await db_client.create_user_with_email(
        email=email,
        password_hash=hashed,
        name=name,
        is_superuser=True,
    )

    # Create organization for the user
    org_provider_id = f"org_{user.provider_id}"
    organization, _ = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=org_provider_id, user_id=user.id
    )

    # Link user to organization
    await db_client.add_user_to_organization(user.id, organization.id)
    await db_client.update_user_selected_organization(user.id, organization.id)

    # Bootstrap default model and telephony configs
    await ensure_organization_bootstrapped(
        organization.id,
        created_by=user.provider_id,
    )

    # Initialize organization wallet with operational bonus minutes
    try:
        from api.db.kodewaves_client import kodewaves_db_client
        wallet = await kodewaves_db_client.get_wallet(organization.id)
        if not wallet:
            await kodewaves_db_client.add_minutes(
                organization_id=organization.id,
                minutes=1000,
                reason="admin_promo",
                notes="Superadmin initial deployment allocation",
            )
            print(f"[SUCCESS] Superadmin wallet initialized with 1,000 minutes.")
    except Exception as e:
        print(f"[WARN] Superadmin wallet initialization notice: {e}")

    print(f"[SUCCESS] Superadmin account '{email}' created successfully.")
    return user


def main():
    parser = argparse.ArgumentParser(description="Create or promote a Kodewaves superadmin user")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "admin@kodewaves.local"))
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", ""))
    parser.add_argument("--name", default="Super Admin")
    args = parser.parse_args()

    if not args.password:
        import secrets
        args.password = secrets.token_urlsafe(16)
        print(f"[INFO] No password provided. Generated temporary password: {args.password}")

    asyncio.run(create_or_promote_superuser(args.email, args.password, args.name))


if __name__ == "__main__":
    main()
