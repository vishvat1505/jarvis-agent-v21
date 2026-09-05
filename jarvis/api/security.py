"""Access controls for the local Jarvis desktop-management surface."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def require_loopback_jarvis(request: Request) -> None:
    """Restrict desktop-management endpoints to the local machine."""
    client_host = request.client.host if request.client else None
    if not _is_loopback_host(client_host):
        raise HTTPException(status_code=403, detail="Jarvis is local-only")
    origin = request.headers.get("origin")
    if origin and not _is_loopback_host(urlsplit(origin).hostname):
        raise HTTPException(status_code=403, detail="Jarvis is local-only")


def _is_loopback_host(host: str | None) -> bool:
    if host is None:
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False
