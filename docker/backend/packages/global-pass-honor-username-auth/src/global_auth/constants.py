"""StrEnum constants for authentication.

All domain strings MUST be StrEnums. No magic strings allowed.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """User roles for authorization."""

    ADMIN = "admin"
    ANNOTATOR = "annotator"


class AuthHeader(StrEnum):
    """HTTP header names for authentication."""

    SITE_PASSWORD = "X-Site-Password"
    USERNAME = "X-Username"


class DefaultUsername(StrEnum):
    """Default usernames for special cases."""

    ANONYMOUS = "anonymous"
    SYSTEM = "system"
