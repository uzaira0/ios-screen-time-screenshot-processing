from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status

if TYPE_CHECKING:
    from ..database import Screenshot
    from ..repositories import ScreenshotRepository
from global_auth import (
    UserRole,
    create_get_current_user,
    create_verify_site_password,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import User, get_db

# Create site password verification using shared package
verify_site_password = create_verify_site_password(get_settings)


async def get_or_create_user_impl(db: AsyncSession, username: str, role: UserRole) -> User:
    """Get or create user by username with the specified role."""
    from sqlalchemy import select

    from ..database.models import UserRole as ModelUserRole

    # Map shared UserRole to model UserRole
    model_role = ModelUserRole.ADMIN if role == UserRole.ADMIN else ModelUserRole.ANNOTATOR

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        user = User(username=username, role=model_role, is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


# Create get_current_user using shared package
get_current_user = create_get_current_user(
    get_db=get_db,
    get_settings=get_settings,
    get_or_create_user=get_or_create_user_impl,
)


async def get_current_admin_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    from ..database.models import UserRole as ModelUserRole

    if current_user.role != ModelUserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
SitePassword = Annotated[str, Depends(verify_site_password)]


async def get_screenshot_for_update(repo: ScreenshotRepository, screenshot_id: int) -> Screenshot:
    """Get screenshot with row lock for safe concurrent updates.

    Shared helper used by both screenshots and annotations routes.
    """
    screenshot = await repo.get_by_id_for_update(screenshot_id)
    if not screenshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenshot not found")
    return screenshot
