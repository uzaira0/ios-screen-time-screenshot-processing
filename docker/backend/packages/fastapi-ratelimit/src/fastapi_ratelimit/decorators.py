"""Rate limit decorators."""

from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from fastapi import Request

F = TypeVar("F", bound=Callable)


def rate_limit(limit_value: str) -> Callable[[F], F]:
    """Decorator to add rate limiting metadata to an endpoint.

    Note: This decorator adds metadata. The actual rate limiting is
    performed by the limiter attached to the app. Use RateLimiter.limit()
    for direct rate limiting.

    Args:
        limit_value: Rate limit string (e.g., "10/minute", "100/hour")

    Example:
        @app.get("/resource")
        @rate_limit("10/minute")
        async def get_resource(request: Request):
            ...
    """

    def decorator(func: F) -> F:
        # Store rate limit as function attribute for introspection
        func._rate_limit = limit_value  # type: ignore
        return func

    return decorator
