"""FastAPI dependencies for Variant B (with user database).

These dependencies provide user management for applications that need
to track users in a database with IDs and roles.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Protocol, TypeVar

from fastapi import Depends, Header, HTTPException, status

from .constants import AuthHeader, UserRole
from .dependencies import HasSitePassword, create_verify_site_password
from .validation import UsernameValidationError, validate_username


class HasAdminUsernames(Protocol):
    """Protocol for settings with admin_usernames_list property."""

    @property
    def admin_usernames_list(self) -> list[str]: ...


class HasSitePasswordAndAdmins(HasSitePassword, HasAdminUsernames, Protocol):
    """Protocol for settings with both site_password and admin usernames."""

    pass


UserModel = TypeVar("UserModel")


def create_get_current_user(
    get_db: Callable[..., Any],
    get_settings: Callable[[], HasSitePasswordAndAdmins],
    get_or_create_user: Callable[[Any, str, UserRole], Any],
) -> Callable[..., Any]:
    """Factory to create get_current_user dependency for Variant B.

    This creates a dependency that:
    1. Validates the site password (if configured)
    2. Extracts and validates the username from X-Username header
    3. Gets or creates the user in the database
    4. Assigns admin role if username is in admin whitelist

    Args:
        get_db: FastAPI dependency that yields database session
        get_settings: Function returning settings
        get_or_create_user: Async function to get or create user.
            Signature: async (db, username, role) -> User

    Returns:
        FastAPI dependency that returns User model instance

    Example:
        async def get_or_create_user(db: AsyncSession, username: str, role: UserRole) -> User:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if not user:
                user = User(username=username, role=role, is_active=True)
                db.add(user)
                await db.commit()
                await db.refresh(user)
            return user

        get_current_user = create_get_current_user(get_db, get_settings, get_or_create_user)

        @router.get("/protected")
        async def protected(current_user: Annotated[User, Depends(get_current_user)]):
            return {"user": current_user.username}
    """
    verify_site_password = create_verify_site_password(get_settings)

    async def get_current_user(
        x_username: Annotated[str | None, Header(alias=AuthHeader.USERNAME)] = None,
        _site_password: str = Depends(verify_site_password),
        db: Any = Depends(get_db),
    ) -> Any:
        """Get or create user based on X-Username header.

        Site password validation happens via dependency chain.
        User is auto-created on first request.
        """
        if not x_username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username header required",
            )

        try:
            username = validate_username(x_username)
        except UsernameValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        # Determine role based on admin whitelist
        settings = get_settings()
        role = (
            UserRole.ADMIN
            if username.lower() in settings.admin_usernames_list
            else UserRole.ANNOTATOR
        )

        user = await get_or_create_user(db, username, role)

        # Check if user is active
        if hasattr(user, "is_active") and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )

        return user

    return get_current_user


def create_get_current_admin_user(
    get_current_user: Callable[..., Any],
) -> Callable[..., Any]:
    """Factory to create admin-only dependency.

    Args:
        get_current_user: Dependency that returns User model

    Returns:
        FastAPI dependency that returns User, but raises 403 if not admin

    Example:
        get_current_user = create_get_current_user(get_db, get_settings, get_or_create_user)
        get_current_admin_user = create_get_current_admin_user(get_current_user)

        @router.delete("/admin-only")
        async def admin_action(admin: Annotated[User, Depends(get_current_admin_user)]):
            return {"admin": admin.username}
    """

    async def get_current_admin_user(
        current_user: Any = Depends(get_current_user),
    ) -> Any:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return current_user

    return get_current_admin_user
