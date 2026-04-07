"""Pydantic settings mixin for site password authentication."""

from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class AuthSettingsMixin(BaseSettings):
    """Mixin class providing auth-related settings.

    Inherit from this class in your app's Settings class to add
    site password, session configuration, and admin usernames.

    Example:
        class Settings(AuthSettingsMixin, BaseSettings):
            DATABASE_URL: str = "sqlite:///app.db"
            # ... other app-specific settings
    """

    SITE_PASSWORD: str = Field(
        default="",
        description="Shared site password for all users. Empty = no auth required.",
    )
    ADMIN_USERNAMES: str = Field(
        default="admin",
        description="Comma-separated list of usernames with admin role.",
    )

    # Session configuration
    SESSION_EXPIRE_SECONDS: int = Field(
        default=60 * 60 * 24 * 7,  # 1 week
        description="Session lifetime in seconds. Default: 1 week (604800).",
    )
    SESSION_STORAGE: Literal["memory", "database"] = Field(
        default="database",
        description="Session storage backend. 'memory' for dev, 'database' for production.",
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode. When True, cookies won't require HTTPS.",
    )

    @property
    def site_password(self) -> str:
        """Get the configured site password."""
        return self.SITE_PASSWORD

    @property
    def password_required(self) -> bool:
        """Check if password authentication is required."""
        return bool(self.site_password)

    @property
    def session_expire_seconds(self) -> int:
        """Get session expiration time in seconds."""
        return self.SESSION_EXPIRE_SECONDS

    @property
    def debug(self) -> bool:
        """Check if debug mode is enabled."""
        return self.DEBUG

    @cached_property
    def admin_usernames_list(self) -> list[str]:
        """Get admin usernames as a lowercase list."""
        return [
            name.strip().lower()
            for name in self.ADMIN_USERNAMES.split(",")
            if name.strip()
        ]
