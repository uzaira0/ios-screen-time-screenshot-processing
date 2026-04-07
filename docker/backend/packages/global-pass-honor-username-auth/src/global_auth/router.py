"""Auth router factory for both variants."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .constants import UserRole
from .dependencies_user import create_get_current_user
from .schemas import (
    AuthStatusResponse,
    PasswordVerifyRequest,
    PasswordVerifyResponse,
    SessionLoginRequest,
    SessionLoginResponse,
    UserLoginRequest,
)
from .session import SessionStorage, clear_session_cookie, set_session_cookie
from .validation import UsernameValidationError, validate_username


class HasPasswordRequired(Protocol):
    """Protocol for settings with password_required and site_password."""

    @property
    def password_required(self) -> bool: ...

    @property
    def site_password(self) -> str: ...


class HasSessionSettings(Protocol):
    """Protocol for settings with session configuration."""

    @property
    def password_required(self) -> bool: ...

    @property
    def site_password(self) -> str: ...

    @property
    def session_expire_seconds(self) -> int: ...

    @property
    def debug(self) -> bool: ...


class HasPasswordRequiredAndAdmins(HasPasswordRequired, Protocol):
    """Protocol for settings with password_required, site_password, and admin_usernames_list."""

    @property
    def admin_usernames_list(self) -> list[str]: ...


def create_auth_router(
    get_settings: Callable[[], HasPasswordRequired | HasPasswordRequiredAndAdmins],
    variant: Literal["a", "b"] = "a",
    get_db: Callable[..., Any] | None = None,
    get_or_create_user: Callable[[Any, str, UserRole], Any] | None = None,
    user_response_model: type | None = None,
    prefix: str = "/auth",
    tags: list[str] | None = None,
) -> APIRouter:
    """Create auth router for the specified variant.

    Args:
        get_settings: Function returning settings object
        variant: "a" for simple (no DB), "b" for user-tracking (with DB)
        get_db: Database session dependency (required for variant B)
        get_or_create_user: Function to get/create users (required for variant B)
        user_response_model: Pydantic model for user response (required for variant B)
        prefix: Router prefix (default: "/auth")
        tags: OpenAPI tags (default: ["Authentication"])

    Returns:
        Configured APIRouter with:
        - GET /status - Check if password required (both variants)
        - POST /verify - Verify password (both variants)
        - POST /login - Login with username+password (variant B only)
        - GET /me - Get current user info (variant B only)

    Example (Variant A):
        auth_router = create_auth_router(get_settings, variant="a")
        app.include_router(auth_router, prefix="/api/v1/auth")

    Example (Variant B):
        auth_router = create_auth_router(
            get_settings=get_settings,
            variant="b",
            get_db=get_db,
            get_or_create_user=get_or_create_user,
            user_response_model=UserRead,
        )
        app.include_router(auth_router, prefix="/api/v1/auth")
    """
    router = APIRouter(prefix=prefix, tags=tags or ["Authentication"])

    @router.get("/status", response_model=AuthStatusResponse)
    async def auth_status() -> AuthStatusResponse:
        """Check if authentication is required.

        Public endpoint - frontend uses this to determine if login is needed.
        """
        settings = get_settings()
        return AuthStatusResponse(password_required=settings.password_required)

    @router.post("/verify", response_model=PasswordVerifyResponse)
    async def verify_password(data: PasswordVerifyRequest) -> PasswordVerifyResponse:
        """Verify site password (stateless check).

        Does not create a session - frontend should store password
        and send via X-Site-Password header on subsequent requests.
        """
        settings = get_settings()
        site_password = settings.site_password

        if not site_password:
            return PasswordVerifyResponse(valid=True, password_required=False)

        # CRITICAL: Use constant-time comparison to prevent timing attacks
        # Encode to bytes to support unicode passwords
        is_valid = secrets.compare_digest(
            data.password.encode("utf-8"),
            site_password.encode("utf-8"),
        )

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
            )

        return PasswordVerifyResponse(valid=True, password_required=True)

    # Variant B adds login and me endpoints
    if variant == "b":
        if not all([get_db, get_or_create_user, user_response_model]):
            raise ValueError(
                "Variant B requires get_db, get_or_create_user, and user_response_model"
            )

        # Create the get_current_user dependency
        _get_current_user = create_get_current_user(
            get_db=get_db,
            get_settings=get_settings,  # type: ignore
            get_or_create_user=get_or_create_user,
        )

        @router.post("/login", response_model=user_response_model)
        async def login(
            login_data: UserLoginRequest,
            db: Any = Depends(get_db),
        ) -> Any:
            """Login with username and optional password.

            Auto-creates user on first login. Returns user info.
            """
            settings = get_settings()

            # Validate password if required
            if settings.site_password:
                if not login_data.password:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Password required",
                    )
                if not secrets.compare_digest(
                    login_data.password.encode("utf-8"),
                    settings.site_password.encode("utf-8"),
                ):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid password",
                    )

            # Validate username
            try:
                username = validate_username(login_data.username)
            except UsernameValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                ) from e

            # Determine role based on admin whitelist
            admin_usernames = getattr(settings, "admin_usernames_list", ["admin"])
            role = (
                UserRole.ADMIN
                if username.lower() in admin_usernames
                else UserRole.ANNOTATOR
            )

            user = await get_or_create_user(db, username, role)  # type: ignore

            if hasattr(user, "is_active") and not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive",
                )

            return user

        @router.get("/me", response_model=user_response_model)
        async def get_me(
            current_user: Any = Depends(_get_current_user),
        ) -> Any:
            """Get current user info.

            Requires X-Username header (and X-Site-Password if configured).
            """
            return current_user

    return router


def create_session_auth_router(
    get_settings: Callable[[], HasSessionSettings],
    session_storage: SessionStorage,
    prefix: str = "/auth",
    tags: list[str] | None = None,
) -> APIRouter:
    """Create session-based auth router for site-wide protection.

    This router provides endpoints for session-based authentication where
    the entire site is protected by session cookies. Use with SessionAuthMiddleware.

    Args:
        get_settings: Function returning settings object with session config
        session_storage: Storage backend for sessions (Database or InMemory)
        prefix: Router prefix (default: "/auth")
        tags: OpenAPI tags (default: ["Authentication"])

    Returns:
        Configured APIRouter with:
        - GET /status - Check if password required (public)
        - POST /session/login - Login and get session cookie
        - POST /session/logout - Clear session cookie

    Example:
        from global_auth import create_session_auth_router, DatabaseSessionStorage
        from global_auth.session import SessionAuthMiddleware

        session_storage = DatabaseSessionStorage(session_maker, SessionModel)

        # Add session router
        auth_router = create_session_auth_router(get_settings, session_storage)
        app.include_router(auth_router, prefix="/api/v1")

        # Add middleware to protect ALL routes
        app.add_middleware(
            SessionAuthMiddleware,
            get_settings=get_settings,
            session_storage=session_storage,
            allowed_paths=["/api/v1/auth/status", "/api/v1/auth/session/login", "/health"],
        )
    """
    router = APIRouter(prefix=prefix, tags=tags or ["Authentication"])

    @router.get("/status", response_model=AuthStatusResponse)
    async def auth_status() -> AuthStatusResponse:
        """Check if authentication is required.

        Public endpoint - frontend uses this to determine if login is needed.
        """
        settings = get_settings()
        return AuthStatusResponse(password_required=settings.password_required)

    @router.post("/session/login", response_model=SessionLoginResponse)
    async def session_login(
        data: SessionLoginRequest,
        response: Response,
    ) -> SessionLoginResponse:
        """Login with username and optional password, get session cookie.

        Creates a session and sets an HTTP-only secure cookie.
        Frontend should redirect here if no valid session exists.
        """
        settings = get_settings()

        # Validate password if required
        if settings.site_password:
            if not data.password:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Password required",
                )
            if not secrets.compare_digest(
                data.password.encode("utf-8"),
                settings.site_password.encode("utf-8"),
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid password",
                )

        # Validate username
        try:
            username = validate_username(data.username)
        except UsernameValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        # Create session
        expire_seconds = settings.session_expire_seconds
        session_token = await session_storage.create(
            username=username,
            user_id=None,  # Session-only auth doesn't track user IDs
            expire_seconds=expire_seconds,
        )

        # Set cookie
        set_session_cookie(
            response=response,
            token=session_token,
            max_age=expire_seconds,
            secure=not settings.debug,  # HTTPS only in production
        )

        return SessionLoginResponse(
            success=True,
            username=username,
            expires_in_seconds=expire_seconds,
        )

    @router.post("/session/logout")
    async def session_logout(
        request: Request,
        response: Response,
    ) -> dict[str, bool]:
        """Logout and clear session cookie.

        Deletes the session from storage and clears the cookie.
        """
        # Get session token from cookie
        session_token = request.cookies.get("session_token")
        if session_token:
            await session_storage.delete(session_token)

        # Clear cookie
        clear_session_cookie(response)

        return {"success": True}

    @router.get("/session/me")
    async def session_me(request: Request) -> dict[str, str | None]:
        """Get current session info.

        Returns the username from the current session.
        Requires valid session (enforced by middleware).
        """
        # Session data is set by middleware
        username = getattr(request.state, "username", None)
        user_id = getattr(request.state, "user_id", None)
        return {"username": username, "user_id": user_id}

    return router
