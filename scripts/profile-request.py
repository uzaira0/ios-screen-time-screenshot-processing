"""
FastAPI per-request profiling middleware.

When PROFILE=1 environment variable is set, wraps each request with
pyinstrument and saves HTML profiles to profiling-reports/requests/.

Also adds X-Profile-Time response header with wall time in milliseconds.

Usage:
    PROFILE=1 uvicorn src.screenshot_processor.web.api.main:app --reload
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

PROFILE_ENABLED = os.getenv("PROFILE", "0") == "1"
PROFILE_DIR = Path("profiling-reports/requests")


class RequestProfilingMiddleware(BaseHTTPMiddleware):
    """Profile individual HTTP requests with pyinstrument when PROFILE=1."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not PROFILE_ENABLED:
            return await call_next(request)

        try:
            from pyinstrument import Profiler
        except ImportError:
            return await call_next(request)

        profiler = Profiler(async_mode="enabled")
        profiler.start()
        start = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            profiler.stop()
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Add timing header
            response.headers["X-Profile-Time"] = f"{elapsed_ms:.2f}ms"

            # Save profile HTML
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            endpoint = request.url.path.strip("/").replace("/", "_") or "root"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{endpoint}_{timestamp}.html"
            profile_path = PROFILE_DIR / filename

            html = profiler.output_html()
            profile_path.write_text(html)

        return response
