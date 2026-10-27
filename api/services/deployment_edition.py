"""Build the owner control plane only into Kodewaves hosted installations."""

import os
from typing import Any

# Docker replaces this marker in the source stage and the release manifest
# covers the resulting file. A client runtime env var cannot switch editions.
IMAGE_EDITION = None


def runtime_edition(configured: str | None = None) -> str:
    """Return the baked image edition; runtime config cannot change it."""
    value = (
        configured if configured is not None else os.getenv("KODEWAVES_EDITION", "saas")
    ).strip().lower()
    if IMAGE_EDITION is not None:
        return IMAGE_EDITION
    if value not in {"saas", "client"}:
        raise RuntimeError("KODEWAVES_EDITION must be either 'saas' or 'client'")
    return value


def public_signup_enabled(edition: str, configured: str | None = None) -> bool:
    """Public self-service signup is a hosted SaaS feature, never client mode."""
    if edition == "client":
        return False
    if edition != "saas":
        raise ValueError("edition must be either 'saas' or 'client'")
    value = configured if configured is not None else os.getenv("ENABLE_SIGNUP", "true")
    return value.strip().lower() == "true"


def mount_owner_control_plane(router: Any, edition: str) -> bool:
    """Mount owner-only routes for SaaS; omit them from client installations."""
    if edition == "client":
        return False
    if edition != "saas":
        raise ValueError("edition must be either 'saas' or 'client'")

    # Import these modules only for SaaS, so client-mode API startup does not
    # register or import the owner route trees.
    from api.routes.admin import admin_router
    from api.routes.superuser import router as superuser_router

    router.include_router(admin_router)
    router.include_router(superuser_router)
    return True
