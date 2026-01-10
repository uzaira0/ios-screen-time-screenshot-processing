"""
Authentication API routes.

Uses the shared global_auth package for consistent auth across all apps.
Variant B: User-tracking with database auto-creation.
"""

from __future__ import annotations

from global_auth import create_auth_router

from screenshot_processor.web.api.dependencies import get_or_create_user_impl
from screenshot_processor.web.config import get_settings
from screenshot_processor.web.database import UserRead, get_db

# Create auth router using shared package (Variant B with user database)
router = create_auth_router(
    get_settings=get_settings,
    variant="b",
    get_db=get_db,
    get_or_create_user=get_or_create_user_impl,
    user_response_model=UserRead,
    prefix="/auth",  # Prefix for auth endpoints
    tags=["Authentication"],
)
