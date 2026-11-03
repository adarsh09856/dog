"""Resolve a client installation's peer IP using explicitly trusted proxies."""

from __future__ import annotations

import ipaddress
import os

from starlette.requests import Request


def observed_client_ip(request: Request) -> str | None:
    """Use the peer address; honor XFF only behind a configured trusted proxy."""
    peer = request.client.host if request.client else None
    if not peer:
        return None
    try:
        current = ipaddress.ip_address(peer)
        trusted = [
            ipaddress.ip_network(value.strip(), strict=False)
            for value in os.getenv("KODEWAVES_OWNER_TRUSTED_PROXY_CIDRS", "").split(",")
            if value.strip()
        ]
    except ValueError:
        return None
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded or not any(current in network for network in trusted):
        return str(current)
    try:
        chain = [ipaddress.ip_address(value.strip()) for value in forwarded.split(",")]
    except ValueError:
        return None
    chain.append(current)
    while len(chain) > 1 and any(chain[-1] in network for network in trusted):
        chain.pop()
    return str(chain[-1])
