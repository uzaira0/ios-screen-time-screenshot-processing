from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import UserRole

if TYPE_CHECKING:
    from ..database.models import User


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    from ..database.models import User

    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_or_create_user(db: AsyncSession, username: str) -> User:
    """Get or create a user by username.

    Note: This is a simplified version. For proper admin detection using
    ADMIN_USERNAMES whitelist, use the get_current_user dependency instead.
    """
    from ..database.models import User

    user = await get_user_by_username(db, username)
    if user:
        return user

    # Simple fallback logic - production code should use dependencies.get_current_user
    role = UserRole.ADMIN if username.lower() == "admin" else UserRole.ANNOTATOR
    db_user = User(username=username, role=role, is_active=True)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def create_user(db: AsyncSession, username: str, role: UserRole = UserRole.ANNOTATOR) -> User:
    from ..database.models import User

    db_user = User(username=username, role=role, is_active=True)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user
