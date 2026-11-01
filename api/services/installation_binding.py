"""Dependency-light helpers for installation license IP binding."""

from __future__ import annotations

import ipaddress


def license_ip_binding_valid(ip_ranges: tuple[str, ...], observed_ip: str | None) -> bool:
    """Match the owner's observed peer address against an optional allowlist."""
    if not ip_ranges:
        return True
    try:
        address = ipaddress.ip_address(observed_ip or "")
        return any(address in ipaddress.ip_network(value) for value in ip_ranges)
    except ValueError:
        return False
