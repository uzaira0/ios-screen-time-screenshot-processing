"""FastAPI dependencies for database access."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def create_get_db(
    session_maker: async_sessionmaker[AsyncSession],
) -> callable:
    """Create a FastAPI dependency that provides database sessions.

    Args:
        session_maker: Session factory from create_session_maker()

    Returns:
        Async generator function for use with Depends()

    Example:
        get_db = create_get_db(session_maker)

        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """

    async def get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            try:
                yield session
            finally:
                await session.close()

    return get_db


# Type alias for annotated dependency
# Usage: async def endpoint(db: DbSession): ...
# Note: This needs to be created per-app since it depends on the session maker
def create_db_session_type(get_db: callable):
    """Create a typed DbSession annotation for your app.

    Example:
        get_db = create_get_db(session_maker)
        DbSession = create_db_session_type(get_db)

        @app.get("/items")
        async def get_items(db: DbSession):
            ...
    """
    return Annotated[AsyncSession, Depends(get_db)]


# Convenience type for documentation
DbSession = Annotated[AsyncSession, Depends(lambda: None)]  # Placeholder, override in app
