"""Key functions for rate limiting."""

from __future__ import annotations

from fastapi import Request


def get_remote_address(request: Request) -> str:
    """Get client IP address, handling proxies.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to client host.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (original client)
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_username_or_ip(request: Request) -> str:
    """Get username from header or fall back to IP.

    Uses X-Username header if present (for authenticated requests),
    otherwise falls back to IP address.
    """
    username = request.headers.get("X-Username")
    if username:
        return f"user:{username}"
    return f"ip:{get_remote_address(request)}"
