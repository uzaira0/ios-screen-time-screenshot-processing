"""Rate limiting configuration for the API.

This module provides a shared rate limiter instance that can be used
across different route modules.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from .config import get_settings

settings = get_settings()


def get_remote_address_with_fallback(request: Request) -> str:
    """Get remote address with fallback for test clients.

    The default get_remote_address can fail when the test client
    doesn't provide proper client info. This provides a fallback.
    """
    try:
        return get_remote_address(request)
    except Exception:
        # Fallback for test clients that don't have proper client info
        return "test-client"


# Rate limiter - uses client IP address for identification
# Default rate limit is configurable via RATE_LIMIT_DEFAULT environment variable
limiter = Limiter(key_func=get_remote_address_with_fallback, default_limits=[settings.RATE_LIMIT_DEFAULT])


def get_upload_rate_limit() -> str:
    """Get rate limit string for upload endpoint."""
    return settings.RATE_LIMIT_UPLOAD


def get_batch_upload_rate_limit() -> str:
    """Get rate limit string for batch upload endpoint."""
    return settings.RATE_LIMIT_BATCH_UPLOAD


# Stricter rate limits for destructive admin operations
# These operations can delete data, so we limit them more aggressively
ADMIN_DESTRUCTIVE_RATE_LIMIT = "5/minute"  # 5 requests per minute per IP
