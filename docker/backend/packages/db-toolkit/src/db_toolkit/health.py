"""Database health check utilities."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class DatabaseHealthCheck:
    """Health check for database connectivity.

    Use with deploy_toolkit's create_app:

        from db_toolkit import create_engine, DatabaseHealthCheck

        engine = create_engine(settings.DATABASE_URL)

        app = create_app(
            title="My API",
            settings=settings,
            health_checks=[DatabaseHealthCheck(engine)],
        )
    """

    def __init__(self, engine: AsyncEngine, name: str = "database"):
        """Create a database health check.

        Args:
            engine: SQLAlchemy async engine to check
            name: Name for this check in health response
        """
        self.engine = engine
        self.name = name

    async def __call__(self) -> tuple[str, bool, str | None]:
        """Execute the health check.

        Returns:
            Tuple of (name, is_healthy, message)
        """
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return (self.name, True, "connected")
        except Exception as e:
            return (self.name, False, f"error: {e}")
