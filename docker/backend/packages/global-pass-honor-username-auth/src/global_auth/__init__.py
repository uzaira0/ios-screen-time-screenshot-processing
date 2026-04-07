"""Global site password + honor-system username authentication.

This package provides shared authentication components for FastAPI applications
using a simple site password + honor-system username model.

Three authentication modes are supported:

1. **Header-Based (Variant A)**: Simple per-request auth via X-Site-Password header
2. **Header-Based (Variant B)**: Per-request auth with user database tracking
3. **Session-Based**: Site-wide protection with secure HTTP-only cookies

Session-Based Auth (RECOMMENDED for full site protection):
    from global_auth import (
        AuthSettingsMixin,
        create_session_auth_router,
        SessionAuthMiddleware,
        DatabaseSessionStorage,
    )

    class Settings(AuthSettingsMixin, BaseSettings):
        DATABASE_URL: str = "postgresql://..."

    # Create session storage (use your Session model)
    session_storage = DatabaseSessionStorage(session_maker, SessionModel)

    # Add auth router (login/logout/status endpoints)
    auth_router = create_session_auth_router(get_settings, session_storage)
    app.include_router(auth_router, prefix="/api/v1")

    # Add middleware to BLOCK ALL requests without valid session
    app.add_middleware(
        SessionAuthMiddleware,
        get_settings=get_settings,
        session_storage=session_storage,
        allowed_paths=["/api/v1/auth/status", "/api/v1/auth/session/login", "/health"],
    )

Header-Based (Variant A - Simple):
    from global_auth import AuthSettingsMixin, create_auth_router, create_verify_site_password

    class Settings(AuthSettingsMixin, BaseSettings):
        DATABASE_URL: str = "sqlite:///app.db"

    verify_site_password = create_verify_site_password(get_settings)
    auth_router = create_auth_router(get_settings, variant="a")

    @router.get("/protected")
    async def protected(
        _: Annotated[str, Depends(verify_site_password)],
        username: str = Depends(get_username_required),
    ):
        return {"message": f"Hello, {username}"}

Header-Based (Variant B - User Tracking):
    from global_auth import (
        AuthSettingsMixin,
        create_auth_router,
        create_get_current_user,
        UserRole,
    )

    auth_router = create_auth_router(
        get_settings=get_settings,
        variant="b",
        get_db=get_db,
        get_or_create_user=get_or_create_user,
        user_response_model=UserRead,
    )

    get_current_user = create_get_current_user(get_db, get_settings, get_or_create_user)

    @router.get("/protected")
    async def protected(current_user: User = Depends(get_current_user)):
        return {"message": f"Hello, {current_user.username}"}
"""

from __future__ import annotations

from .config import AuthSettingsMixin
from .constants import AuthHeader, DefaultUsername, UserRole
from .dependencies import (
    create_get_username_validated,
    create_type_aliases,
    create_verify_site_password,
    get_username_optional,
    get_username_optional_validated,
    get_username_required,
)
from .dependencies_user import (
    create_get_current_admin_user,
    create_get_current_user,
)
from .router import create_auth_router, create_session_auth_router
from .schemas import (
    AuthStatusResponse,
    PasswordVerifyRequest,
    PasswordVerifyResponse,
    SessionLoginRequest,
    SessionLoginResponse,
    UserLoginRequest,
    UserResponseBase,
)
from .session import (
    InMemorySessionStorage,
    SessionAuthMiddleware,
    SessionData,
    SessionStorage,
    clear_session_cookie,
    set_session_cookie,
)
from .session_storage_db import DatabaseSessionStorage, SyncDatabaseSessionStorage
from .validation import (
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    USERNAME_PATTERN,
    UsernameValidationError,
    validate_username,
)

__all__ = [
    "USERNAME_MAX_LENGTH",
    "USERNAME_MIN_LENGTH",
    "USERNAME_PATTERN",
    "AuthHeader",
    "AuthSettingsMixin",
    "AuthStatusResponse",
    "DatabaseSessionStorage",
    "DefaultUsername",
    "InMemorySessionStorage",
    "PasswordVerifyRequest",
    "PasswordVerifyResponse",
    "SessionAuthMiddleware",
    "SessionData",
    "SessionLoginRequest",
    "SessionLoginResponse",
    "SessionStorage",
    "SyncDatabaseSessionStorage",
    "UserLoginRequest",
    "UserResponseBase",
    "UserRole",
    "UsernameValidationError",
    "clear_session_cookie",
    "create_auth_router",
    "create_get_current_admin_user",
    "create_get_current_user",
    "create_get_username_validated",
    "create_session_auth_router",
    "create_type_aliases",
    "create_verify_site_password",
    "get_username_optional",
    "get_username_optional_validated",
    "get_username_required",
    "set_session_cookie",
    "validate_username",
]

__version__ = "0.1.0"
