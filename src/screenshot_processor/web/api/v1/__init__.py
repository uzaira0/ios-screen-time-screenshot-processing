"""API v1 - Production-ready versioned API."""

from __future__ import annotations

from fastapi import APIRouter

from ..routes import admin, annotations, auth, consensus, screenshots

# Create v1 router
router = APIRouter(prefix="/v1")

# Include all route modules
router.include_router(auth.router)
router.include_router(screenshots.router)
router.include_router(annotations.router)
router.include_router(consensus.router)
router.include_router(admin.router)

__all__ = ["router"]
