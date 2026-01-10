from __future__ import annotations

import logging
import os

from db_toolkit import create_engine, create_get_db, create_session_maker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine
from sqlalchemy.pool import StaticPool

from .models import Base

logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://screenshot:screenshot@localhost:5433/screenshot_annotations",
)

# Convert sync SQLite URLs to async (aiosqlite)
if DATABASE_URL.startswith("sqlite:///"):
    DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

# Configure engine based on database type
if "sqlite" in DATABASE_URL:
    # SQLite configuration (for testing or legacy development)
    # Uses StaticPool to work around SQLite's single-writer limitation
    # Note: db-toolkit doesn't handle SQLite's special needs, so we create manually
    logger.info("Using SQLite database", extra={"db_type": "sqlite"})
    engine = sa_create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_session_maker = create_session_maker(engine)
else:
    # PostgreSQL configuration (recommended for development and production)
    # Use db-toolkit for standardized connection pooling
    logger.info("Using PostgreSQL database", extra={"db_type": "postgresql"})
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        echo=False,
    )
    async_session_maker = create_session_maker(engine)

# Create get_db dependency using db-toolkit
get_db = create_get_db(async_session_maker)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def drop_db() -> None:
    """Drop all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped")
