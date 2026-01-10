"""Rate limiting for FastAPI applications.

Example usage:
    from fastapi_ratelimit import setup_rate_limiting, RateLimiter, rate_limit

    limiter = setup_rate_limiting(app)

    @app.get("/api/resource")
    @rate_limit("10/minute")
    async def get_resource():
        ...
"""

from __future__ import annotations

from .limiter import RateLimiter, setup_rate_limiting
from .decorators import rate_limit
from .key_funcs import get_remote_address, get_username_or_ip

__all__ = [
    "RateLimiter",
    "setup_rate_limiting",
    "rate_limit",
    "get_remote_address",
    "get_username_or_ip",
]

__version__ = "0.1.0"
