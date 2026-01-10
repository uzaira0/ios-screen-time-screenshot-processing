"""Rate limiter setup and configuration."""

from __future__ import annotations

from typing import Callable

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address as slowapi_get_remote_address

from .key_funcs import get_remote_address


class RateLimiter:
    """Rate limiter wrapper with sensible defaults.

    Example:
        limiter = RateLimiter()

        @app.get("/api/resource")
        @limiter.limit("10/minute")
        async def get_resource(request: Request):
            ...
    """

    def __init__(
        self,
        *,
        key_func: Callable[[Request], str] | None = None,
        default_limits: list[str] | None = None,
        storage_uri: str | None = None,
    ):
        """Create a rate limiter.

        Args:
            key_func: Function to extract rate limit key from request
            default_limits: Default rate limits (e.g., ["100/hour"])
            storage_uri: Redis URI for distributed rate limiting
        """
        self._key_func = key_func or get_remote_address
        self._default_limits = default_limits or []
        self._storage_uri = storage_uri

        self._limiter = Limiter(
            key_func=self._key_func,
            default_limits=self._default_limits,
            storage_uri=self._storage_uri,
        )

    @property
    def limiter(self) -> Limiter:
        """Get the underlying slowapi Limiter."""
        return self._limiter

    def limit(self, limit_value: str):
        """Decorator to apply rate limit to an endpoint.

        Args:
            limit_value: Rate limit string (e.g., "10/minute", "100/hour")

        Example:
            @limiter.limit("10/minute")
            async def my_endpoint(request: Request):
                ...
        """
        return self._limiter.limit(limit_value)

    def shared_limit(self, limit_value: str, scope: str):
        """Decorator for shared rate limit across multiple endpoints.

        Args:
            limit_value: Rate limit string
            scope: Shared scope name

        Example:
            @limiter.shared_limit("100/hour", scope="api")
            async def endpoint1(request: Request):
                ...

            @limiter.shared_limit("100/hour", scope="api")
            async def endpoint2(request: Request):
                ...
        """
        return self._limiter.shared_limit(limit_value, scope=scope)


def setup_rate_limiting(
    app: FastAPI,
    *,
    key_func: Callable[[Request], str] | None = None,
    default_limits: list[str] | None = None,
    storage_uri: str | None = None,
) -> RateLimiter:
    """Setup rate limiting on a FastAPI app.

    Args:
        app: FastAPI application
        key_func: Function to extract rate limit key from request
        default_limits: Default rate limits for all endpoints
        storage_uri: Redis URI for distributed rate limiting

    Returns:
        RateLimiter instance for use in decorators

    Example:
        from fastapi_ratelimit import setup_rate_limiting

        app = FastAPI()
        limiter = setup_rate_limiting(app, default_limits=["100/hour"])

        @app.get("/resource")
        @limiter.limit("10/minute")
        async def get_resource(request: Request):
            ...
    """
    rate_limiter = RateLimiter(
        key_func=key_func,
        default_limits=default_limits,
        storage_uri=storage_uri,
    )

    # Attach to app state
    app.state.limiter = rate_limiter.limiter

    # Add exception handler
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    return rate_limiter
