"""FastAPI dependencies for Variant A (no user database).

These dependencies provide site password verification and username extraction
for applications that don't need a user database.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Annotated, Protocol

from fastapi import Depends, Header, HTTPException, status

from .constants import AuthHeader, DefaultUsername
from .validation import UsernameValidationError, validate_username


class HasSitePassword(Protocol):
    """Protocol for settings with site_password property."""

    @property
    def site_password(self) -> str: ...


def create_verify_site_password(
    get_settings: Callable[[], HasSitePassword],
) -> Callable[[str | None], str]:
    """Factory to create site password verification dependency.

    Args:
        get_settings: Function returning settings with site_password property

    Returns:
        FastAPI dependency function that validates X-Site-Password header

    Example:
        verify_site_password = create_verify_site_password(get_settings)

        @router.get("/protected")
        async def protected(_: Annotated[str, Depends(verify_site_password)]):
            return {"message": "authenticated"}
    """

    def verify_site_password(
        x_site_password: Annotated[
            str | None, Header(alias=AuthHeader.SITE_PASSWORD)
        ] = None,
    ) -> str:
        """Verify site password from X-Site-Password header.

        Uses constant-time comparison to prevent timing attacks.

        Returns:
            The validated password (or empty string if no password required)

        Raises:
            HTTPException 401 if password is required but missing/invalid
        """
        settings = get_settings()
        site_password = settings.site_password

        if not site_password:
            return ""  # No password configured, allow access

        if not x_site_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Site password required",
            )

        # CRITICAL: Use constant-time comparison to prevent timing attacks
        # Encode to bytes to support unicode passwords
        if not secrets.compare_digest(
            x_site_password.encode("utf-8"),
            site_password.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid site password",
            )

        return x_site_password

    return verify_site_password


def get_username_optional(
    x_username: Annotated[str | None, Header(alias=AuthHeader.USERNAME)] = None,
) -> str:
    """Get username from header, defaulting to 'anonymous'.

    No validation - accepts any value or returns default.
    Use this when username is optional for audit logging.
    """
    if x_username:
        return x_username.strip() or DefaultUsername.ANONYMOUS
    return DefaultUsername.ANONYMOUS


def create_get_username_validated(
    require: bool = True,
) -> Callable[[str | None], str | None]:
    """Factory to create username dependency with validation.

    Args:
        require: If True, raises 401 when username missing

    Returns:
        FastAPI dependency function

    Example:
        get_username_required = create_get_username_validated(require=True)

        @router.get("/protected")
        async def protected(username: Annotated[str, Depends(get_username_required)]):
            return {"user": username}
    """

    def get_username(
        x_username: Annotated[str | None, Header(alias=AuthHeader.USERNAME)] = None,
    ) -> str | None:
        if not x_username:
            if require:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Username required via X-Username header",
                )
            return None

        try:
            return validate_username(x_username)
        except UsernameValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    return get_username


# Pre-built dependencies for common use cases
get_username_required = create_get_username_validated(require=True)
get_username_optional_validated = create_get_username_validated(require=False)


def create_type_aliases(
    verify_site_password: Callable[[str | None], str],
) -> tuple[type, type, type]:
    """Create type aliases for dependency injection.

    Args:
        verify_site_password: The verify_site_password dependency from factory

    Returns:
        Tuple of (SitePassword, Username, UsernameOptional) type aliases

    Example:
        verify_site_password = create_verify_site_password(get_settings)
        SitePassword, Username, UsernameOptional = create_type_aliases(verify_site_password)

        @router.get("/protected")
        async def protected(_: SitePassword, username: Username):
            return {"user": username}
    """
    SitePassword = Annotated[str, Depends(verify_site_password)]
    Username = Annotated[str, Depends(get_username_required)]
    UsernameOptional = Annotated[str | None, Depends(get_username_optional_validated)]
    return SitePassword, Username, UsernameOptional
