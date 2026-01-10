"""
Server-Timing middleware and slow request logging.

Adds `Server-Timing: total;dur=X.XX` header to every response.
When PROFILE=1, also saves pyinstrument call trees to profiling-reports/requests/.
Logs warnings for requests exceeding 500ms.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

PROFILE_ENABLED = os.getenv("PROFILE", "0") == "1"
SLOW_REQUEST_THRESHOLD_MS = float(os.getenv("SLOW_REQUEST_THRESHOLD_MS", "500"))
PROFILE_DIR = Path("profiling-reports/requests")


class ServerTimingMiddleware(BaseHTTPMiddleware):
    """Add Server-Timing header and log slow requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()

        if PROFILE_ENABLED:
            response = await self._dispatch_with_profile(request, call_next, start)
        else:
            response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["Server-Timing"] = f"total;dur={elapsed_ms:.2f}"

        if elapsed_ms > SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "Slow request: %s %s took %.1fms",
                request.method,
                request.url.path,
                elapsed_ms,
            )

        return response

    async def _dispatch_with_profile(
        self, request: Request, call_next: RequestResponseEndpoint, start: float
    ) -> Response:
        """Dispatch with pyinstrument profiling."""
        try:
            from pyinstrument import Profiler
        except ImportError:
            return await call_next(request)

        profiler = Profiler(async_mode="enabled")
        profiler.start()

        response: Response | None = None
        try:
            response = await call_next(request)
        finally:
            profiler.stop()
            elapsed_ms = (time.perf_counter() - start) * 1000

            if response is not None:
                response.headers["X-Profile-Time"] = f"{elapsed_ms:.2f}ms"

            # Save profile for slow requests or all requests when profiling
            try:
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                endpoint = request.url.path.strip("/").replace("/", "_") or "root"
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{endpoint}_{timestamp}.html"
                profile_path = PROFILE_DIR / filename
                profile_path.write_text(profiler.output_html())
            except OSError:
                logger.warning("Failed to write profile to %s", PROFILE_DIR)

        if response is None:
            raise RuntimeError("call_next did not return a response")
        return response
