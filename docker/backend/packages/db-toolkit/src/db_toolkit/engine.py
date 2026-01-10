"""SQLAlchemy engine and session factories."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine as sa_create_async_engine,
)


def create_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    pool_recycle: int = 1800,
    echo: bool = False,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine with sensible defaults.

    Args:
        database_url: Database connection URL (e.g., postgresql+asyncpg://...)
        pool_size: Number of connections in the pool (default: 5)
        max_overflow: Max connections above pool_size (default: 10)
        pool_timeout: Seconds to wait for connection (default: 30)
        pool_recycle: Seconds before recycling connection (default: 1800)
        echo: Log SQL statements (default: False)

    Returns:
        Configured AsyncEngine

    Example:
        engine = create_engine("postgresql+asyncpg://user:pass@localhost/db")
    """
    # Handle SQLite specially (no pooling)
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs: dict = {
        "echo": echo,
    }

    if not is_sqlite:
        engine_kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True,  # Verify connections before use
        )

    return sa_create_async_engine(database_url, **engine_kwargs)


def create_session_maker(
    engine: AsyncEngine,
    *,
    expire_on_commit: bool = False,
    autoflush: bool = False,
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory for the given engine.

    Args:
        engine: AsyncEngine to bind sessions to
        expire_on_commit: Expire objects after commit (default: False for async)
        autoflush: Auto-flush before queries (default: False)

    Returns:
        Session factory that creates AsyncSession instances

    Example:
        session_maker = create_session_maker(engine)
        async with session_maker() as session:
            ...
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=expire_on_commit,
        autoflush=autoflush,
    )
