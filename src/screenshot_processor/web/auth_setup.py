"""Authentication setup for Screenshot-Annotator.

Configures session-based authentication with site-wide protection.
"""

from __future__ import annotations

from global_auth import DatabaseSessionStorage

from .database.database import async_session_maker
from .database.models import Session


def create_session_storage() -> DatabaseSessionStorage:
    """Create async database session storage.

    Uses the existing async_session_maker and Session model.
    """
    return DatabaseSessionStorage(
        session_maker=async_session_maker,
        session_model=Session,
    )
