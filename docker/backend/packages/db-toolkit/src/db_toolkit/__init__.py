"""Database utilities for FastAPI with SQLAlchemy async.

Example usage:
    from db_toolkit import create_engine, create_session_maker, create_get_db

    engine = create_engine(settings.DATABASE_URL)
    session_maker = create_session_maker(engine)
    get_db = create_get_db(session_maker)

    @app.get("/items")
    async def get_items(db: AsyncSession = Depends(get_db)):
        ...
"""

from __future__ import annotations

from .engine import create_engine, create_session_maker
from .dependencies import create_get_db, DbSession
from .health import DatabaseHealthCheck
from .base import Base, TimestampMixin, SoftDeleteMixin

__all__ = [
    # Engine
    "create_engine",
    "create_session_maker",
    # Dependencies
    "create_get_db",
    "DbSession",
    # Health
    "DatabaseHealthCheck",
    # Base classes
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
]

__version__ = "0.1.0"
