"""Database-backed session storage using SQLAlchemy.

Provides both sync and async session storage implementations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .session import SessionData, SessionStorage, generate_session_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import Session, sessionmaker


class DatabaseSessionStorage(SessionStorage):
    """SQLAlchemy-based session storage (async).

    Requires a Session table in your database. Example model:

        class Session(Base):
            __tablename__ = "sessions"

            token = Column(String(64), primary_key=True)
            user_id = Column(String(36), nullable=True, index=True)
            username = Column(String(50), nullable=False)
            created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
            expires_at = Column(DateTime(timezone=True), nullable=False)
            last_activity = Column(DateTime(timezone=True), nullable=True)
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession],
        session_model: Any,
    ) -> None:
        """Initialize database session storage.

        Args:
            session_maker: SQLAlchemy async session maker
            session_model: SQLAlchemy model class for sessions table
        """
        self.session_maker = session_maker
        self.Session = session_model

    async def create(
        self,
        username: str,
        user_id: str | None = None,
        expire_seconds: int = 604800,
    ) -> str:
        token = generate_session_token()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expire_seconds)

        async with self.session_maker() as db:
            session_record = self.Session(
                token=token,
                user_id=user_id,
                username=username,
                created_at=now,
                expires_at=expires_at,
                last_activity=now,
            )
            db.add(session_record)
            await db.commit()

        return token

    async def get(self, token: str) -> SessionData | None:
        from sqlalchemy import select

        async with self.session_maker() as db:
            result = await db.execute(
                select(self.Session).where(self.Session.token == token)
            )
            record = result.scalar_one_or_none()

            if record is None:
                return None

            session_data = SessionData(
                token=record.token,
                user_id=record.user_id,
                username=record.username,
                created_at=record.created_at,
                expires_at=record.expires_at,
                last_activity=record.last_activity,
            )

            if session_data.is_expired:
                # Clean up expired session
                await db.delete(record)
                await db.commit()
                return None

            # Update last activity
            record.last_activity = datetime.now(UTC)
            await db.commit()

            return session_data

    async def delete(self, token: str) -> bool:
        from sqlalchemy import select

        async with self.session_maker() as db:
            result = await db.execute(
                select(self.Session).where(self.Session.token == token)
            )
            record = result.scalar_one_or_none()

            if record is None:
                return False

            await db.delete(record)
            await db.commit()
            return True

    async def cleanup_expired(self) -> int:
        from sqlalchemy import delete

        now = datetime.now(UTC)

        async with self.session_maker() as db:
            result = await db.execute(
                delete(self.Session).where(self.Session.expires_at < now)
            )
            await db.commit()
            return result.rowcount or 0


class SyncDatabaseSessionStorage:
    """SQLAlchemy-based session storage (sync version for flash-processing).

    Same interface as DatabaseSessionStorage but uses sync sessions.
    Note: This is NOT a subclass of SessionStorage since that's async.
    """

    def __init__(
        self,
        session_maker: sessionmaker[Session],
        session_model: Any,
    ) -> None:
        """Initialize sync database session storage.

        Args:
            session_maker: SQLAlchemy sync session maker
            session_model: SQLAlchemy model class for sessions table
        """
        self.session_maker = session_maker
        self.Session = session_model

    def create(
        self,
        username: str,
        user_id: str | None = None,
        expire_seconds: int = 604800,
    ) -> str:
        token = generate_session_token()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=expire_seconds)

        with self.session_maker() as db:
            session_record = self.Session(
                token=token,
                user_id=user_id,
                username=username,
                created_at=now,
                expires_at=expires_at,
                last_activity=now,
            )
            db.add(session_record)
            db.commit()

        return token

    def get(self, token: str) -> SessionData | None:
        with self.session_maker() as db:
            record = db.query(self.Session).filter(self.Session.token == token).first()

            if record is None:
                return None

            session_data = SessionData(
                token=record.token,
                user_id=record.user_id,
                username=record.username,
                created_at=record.created_at,
                expires_at=record.expires_at,
                last_activity=record.last_activity,
            )

            if session_data.is_expired:
                # Clean up expired session
                db.delete(record)
                db.commit()
                return None

            # Update last activity
            record.last_activity = datetime.now(UTC)
            db.commit()

            return session_data

    def delete(self, token: str) -> bool:
        with self.session_maker() as db:
            record = db.query(self.Session).filter(self.Session.token == token).first()

            if record is None:
                return False

            db.delete(record)
            db.commit()
            return True

    def cleanup_expired(self) -> int:
        now = datetime.now(UTC)

        with self.session_maker() as db:
            count = db.query(self.Session).filter(self.Session.expires_at < now).delete()
            db.commit()
            return count
