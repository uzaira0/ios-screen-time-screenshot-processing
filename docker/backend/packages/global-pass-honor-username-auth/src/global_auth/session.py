"""Session-based authentication for full site protection.

This module provides session middleware and storage for protecting
entire sites with cookie-based authentication.

Usage:
    from global_auth import SessionAuthMiddleware, DatabaseSessionStorage

    # Create session storage
    session_storage = DatabaseSessionStorage(session_maker)

    # Add middleware (blocks ALL requests except allowlist)
    app.add_middleware(
        SessionAuthMiddleware,
        get_settings=get_settings,
        session_storage=session_storage,
        allowed_paths=["/api/v1/auth/login", "/api/v1/auth/status", "/health"],
    )
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

# Session token configuration
SESSION_TOKEN_BYTES = 32  # 256 bits of entropy
SESSION_COOKIE_NAME = "session_token"


@dataclass
class SessionData:
    """Session data stored in backend."""

    token: str
    user_id: str | None
    username: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(UTC) > self.expires_at


class SessionStorage(ABC):
    """Abstract base class for session storage backends."""

    @abstractmethod
    async def create(
        self,
        username: str,
        user_id: str | None = None,
        expire_seconds: int = 604800,
    ) -> str:
        """Create a new session and return the token.

        Args:
            username: The username for this session
            user_id: Optional user ID (for Variant B)
            expire_seconds: Session lifetime in seconds (default 1 week)

        Returns:
            Session token string
        """
        ...

    @abstractmethod
    async def get(self, token: str) -> SessionData | None:
        """Get session data by token.

        Args:
            token: Session token

        Returns:
            SessionData if valid session exists, None otherwise
        """
        ...

    @abstractmethod
    async def delete(self, token: str) -> bool:
        """Delete a session.

        Args:
            token: Session token to delete

        Returns:
            True if session was deleted, False if not found
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove all expired sessions.

        Returns:
            Number of sessions deleted
        """
        ...


class InMemorySessionStorage(SessionStorage):
    """In-memory session storage for development/testing.

    WARNING: Sessions are lost on restart. Not suitable for production.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    async def create(
        self,
        username: str,
        user_id: str | None = None,
        expire_seconds: int = 604800,
    ) -> str:
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        now = datetime.now(UTC)
        self._sessions[token] = SessionData(
            token=token,
            user_id=user_id,
            username=username,
            created_at=now,
            expires_at=now + timedelta(seconds=expire_seconds),
            last_activity=now,
        )
        return token

    async def get(self, token: str) -> SessionData | None:
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.is_expired:
            del self._sessions[token]
            return None
        # Update last activity
        session.last_activity = datetime.now(UTC)
        return session

    async def delete(self, token: str) -> bool:
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    async def cleanup_expired(self) -> int:
        now = datetime.now(UTC)
        expired = [t for t, s in self._sessions.items() if s.expires_at < now]
        for token in expired:
            del self._sessions[token]
        return len(expired)


class HasSessionSettings(Protocol):
    """Protocol for settings with session configuration."""

    @property
    def site_password(self) -> str:
        ...

    @property
    def session_expire_seconds(self) -> int:
        ...

    @property
    def debug(self) -> bool:
        ...


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that blocks ALL requests without valid session.

    Allowlisted paths (like /login, /health) are accessible without session.
    All other paths return 401 if no valid session cookie is present.

    Usage:
        app.add_middleware(
            SessionAuthMiddleware,
            get_settings=get_settings,
            session_storage=session_storage,
            allowed_paths=["/api/v1/auth/login", "/api/v1/auth/status", "/health"],
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        get_settings: Callable[[], HasSessionSettings],
        session_storage: SessionStorage,
        allowed_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.get_settings = get_settings
        self.session_storage = session_storage
        self.allowed_paths = allowed_paths or [
            "/api/v1/auth/login",
            "/api/v1/auth/status",
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

    def _is_allowed_path(self, path: str) -> bool:
        """Check if path is in allowlist."""
        return any(path.startswith(allowed) for allowed in self.allowed_paths)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = self.get_settings()

        # If no site password configured, allow all requests
        if not settings.site_password:
            return await call_next(request)

        # Check if path is allowed without auth
        if self._is_allowed_path(request.url.path):
            return await call_next(request)

        # Check session cookie
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_token:
            return Response(
                content='{"detail": "Not authenticated"}',
                status_code=401,
                media_type="application/json",
            )

        # Validate session
        session = await self.session_storage.get(session_token)
        if session is None:
            return Response(
                content='{"detail": "Session expired or invalid"}',
                status_code=401,
                media_type="application/json",
            )

        # Store session data in request state for use in endpoints
        request.state.session = session
        request.state.username = session.username
        request.state.user_id = session.user_id

        return await call_next(request)


def set_session_cookie(
    response: Response,
    token: str,
    max_age: int,
    secure: bool = True,
) -> None:
    """Set session cookie on response.

    Args:
        response: FastAPI Response object
        token: Session token
        max_age: Cookie lifetime in seconds
        secure: If True, cookie only sent over HTTPS
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,  # Not accessible via JavaScript (XSS protection)
        secure=secure,  # HTTPS only in production
        samesite="strict",  # CSRF protection
        max_age=max_age,
        path="/",  # Available for all paths
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie from response."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
    )


def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)
