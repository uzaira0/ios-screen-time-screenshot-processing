from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_errors import setup_error_handlers
from fastapi_logging import RequestLoggingMiddleware, get_logger, setup_logging
from fastapi_ratelimit import setup_rate_limiting
from global_auth import SessionAuthMiddleware, create_session_auth_router
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_setup import create_session_storage
from ..config import get_settings
from ..database import HealthCheckResponse, RootResponse, get_db, init_db
from . import v1
from .routes.websocket import router as ws_router

# Get settings for rate limiting configuration
settings = get_settings()

# Configure structured logging (JSON in production, text in development)
setup_logging(json_format=not settings.DEBUG)
logger = get_logger(__name__)


async def _periodic_cleanup(interval_seconds: int = 3600) -> None:
    """Periodically clean up expired sessions and stale UserQueueState rows.

    Runs every *interval_seconds* (default 1 hour) as a background asyncio task
    spawned from the app lifespan.
    """
    import asyncio

    from screenshot_processor.web.database import async_session_maker
    from screenshot_processor.web.repositories.admin_repository import AdminRepository

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            # 1. Clean up expired sessions
            deleted_sessions = await session_storage.cleanup_expired()
            if deleted_sessions:
                logger.info("Cleaned up expired sessions", extra={"deleted": deleted_sessions})

            # 2. Clean up stale UserQueueState rows for completed/deleted screenshots
            async with async_session_maker() as db:
                admin_repo = AdminRepository(db)
                deleted_queue_states = await admin_repo.cleanup_stale_queue_states()
                if deleted_queue_states:
                    await db.commit()
                    logger.info(
                        "Cleaned up stale UserQueueState rows",
                        extra={"deleted": deleted_queue_states},
                    )
        except Exception as e:
            logger.error("Periodic cleanup failed", extra={"error": str(e)})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    import asyncio

    logger.info("Starting iOS Screenshot Processing API...")
    await init_db()
    logger.info("Database initialized")

    # Start periodic cleanup task for expired sessions and stale queue states
    cleanup_task = asyncio.create_task(_periodic_cleanup())

    yield

    cleanup_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleanup_task
    logger.info("Shutting down iOS Screenshot Processing API...")


app = FastAPI(
    title="iOS Screenshot Processing API",
    description="Multi-user platform for processing iPhone screen time and battery screenshots",
    version="1.0.0",
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
)

# Setup standardized error handlers (replaces custom exception handler)
setup_error_handlers(app, debug=settings.DEBUG)
logger.info("Error handlers configured")

# Setup rate limiting (replaces slowapi)
setup_rate_limiting(app, default_limits=[settings.RATE_LIMIT_DEFAULT])
logger.info("Rate limiting configured", default_limits=[settings.RATE_LIMIT_DEFAULT])

# Add GZip compression for JSON/text responses > 500 bytes.
# Skips already-compressed formats (PNG/JPEG images) to avoid wasting CPU.
from starlette.middleware.gzip import GZipMiddleware


class SelectiveGZipMiddleware(GZipMiddleware):
    """GZip that skips binary/image content types."""

    _SKIP_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/heic", "application/octet-stream"})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and any(scope["path"].endswith(suffix) for suffix in ("/image", "/original-image", "/stage-image")):
            # Bypass gzip for image endpoints
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


app.add_middleware(SelectiveGZipMiddleware, minimum_size=500)

# Add Server-Timing header + slow request logging middleware
from .middleware import ServerTimingMiddleware

app.add_middleware(ServerTimingMiddleware)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Get CORS origins from config
cors_origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]

# Configure CORS - must be before SessionAuthMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Username", "X-Site-Password"],
)

# Create session storage for authentication
session_storage = create_session_storage()

# Add session auth middleware - BLOCKS ALL requests without valid session
# except for allowlisted paths (login, status, health, docs)
app.add_middleware(
    SessionAuthMiddleware,
    get_settings=get_settings,
    session_storage=session_storage,
    allowed_paths=[
        "/api/v1/auth/status",
        "/api/v1/auth/session/login",
        "/api/v1/auth/login",  # Header-based auth for API clients
        "/api/ws",  # WebSocket uses username query-param auth
        "/health",
        "/",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/api/v1/openapi.json",
    ],
)


@app.get("/", response_model=RootResponse)
async def root():
    """Root endpoint providing API information."""
    return RootResponse(
        message="Screenshot Annotation API",
        version="1.0.0",
        docs="/api/v1/docs",
        redoc="/api/v1/redoc",
    )


@app.get("/health", response_model=HealthCheckResponse)
async def health_check(db: AsyncSession = Depends(get_db), include_worker: bool = False):
    """
    Comprehensive health check endpoint.

    Returns health status including database connectivity.
    Set include_worker=true to also check workflow worker availability.
    """
    health_status = "healthy"
    checks_dict = {}

    # Database connectivity check
    try:
        await db.execute(text("SELECT 1"))
        checks_dict["database"] = "ok"
    except Exception as e:
        logger.error("Health check - database error", extra={"error": str(e)})
        health_status = "unhealthy"
        checks_dict["database"] = f"error: {e!s}"

    # Optional workflow worker health check
    if include_worker:
        checks_dict["workflow_worker"] = "health check not yet implemented"

    # Return appropriate status code
    status_code = 200 if health_status == "healthy" else 503
    return JSONResponse(
        content=HealthCheckResponse(status=health_status, checks=checks_dict).model_dump(),
        status_code=status_code,
    )


# Mount v1 API
app.include_router(v1.router, prefix="/api")

# Session-based auth router - provides login/logout/status endpoints
# Uses the same session_storage as the middleware
auth_router = create_session_auth_router(
    get_settings=get_settings,
    session_storage=session_storage,
    prefix="",
    tags=["auth"],
)
app.include_router(auth_router, prefix="/api/v1/auth")

# WebSocket router — mounted at /api/ws (outside versioned API)
app.include_router(ws_router, prefix="/api")
