"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..profiles.registry import get_profile_registry
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    # Startup: Initialize profile registry
    registry = get_profile_registry()
    profiles = list(registry.get_all_profiles())
    print(f"Loaded {len(profiles)} device profiles")
    yield
    # Shutdown: Nothing to clean up


def create_app(
    title: str = "iOS Device Detector",
    version: str = "1.0.0",
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title=title,
        version=version,
        description="Detect iOS device models from image dimensions",
        lifespan=lifespan,
    )

    # Add CORS middleware
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include routes
    app.include_router(router)

    return app


# Default app instance
app = create_app()
