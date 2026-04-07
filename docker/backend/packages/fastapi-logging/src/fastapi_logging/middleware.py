"""Request logging middleware."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .context import set_request_id
from .logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs all requests and responses.

    Features:
    - Generates/propagates request ID
    - Logs request start and completion
    - Measures request duration
    - Stores request ID in request.state

    Example:
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate request ID
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or None
        )
        request_id = set_request_id(request_id)

        # Store in request state for access in handlers
        request.state.request_id = request_id

        # Log request start
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            query=str(request.query_params) if request.query_params else None,
        )

        # Process request and measure time
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise
