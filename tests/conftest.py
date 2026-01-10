"""
Shared test fixtures for all test modules.

This module provides async fixtures for testing with an in-memory SQLite database.
"""

from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator

# Set required environment variables BEFORE importing the app
# SECRET_KEY is required for security, must be at least 32 chars
os.environ["SECRET_KEY"] = "test-secret-key-at-least-32-chars-long-for-testing"
# Clear SITE_PASSWORD so tests don't require it (production may have it set)
os.environ.pop("SITE_PASSWORD", None)

# Reset settings singleton to pick up test environment variables
from screenshot_processor.web.config import reset_settings

reset_settings()

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from screenshot_processor.web.api.main import app  # noqa: E402
from screenshot_processor.web.database.database import get_db  # noqa: E402
from screenshot_processor.web.database.models import Base, Group, Screenshot, User  # noqa: E402

# Create test engine with in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database session for each test.
    Creates all tables before the test and drops them after.
    """
    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    # Drop all tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async HTTP client for testing the FastAPI app.
    Overrides the database dependency to use the test session.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Disable in-memory cache for tests — set TTL to 0 so every request queries fresh
    from screenshot_processor.web.cache import stats_cache

    stats_cache.invalidate_all()
    original_ttl = stats_cache._ttl
    stats_cache._ttl = 0.0

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    stats_cache.invalidate_all()
    stats_cache._ttl = original_ttl


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user for authentication."""
    user = User(
        username="testuser",
        role="annotator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    """Create a test admin user."""
    user = User(
        username="admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_group(db_session: AsyncSession) -> Group:
    """Create a test group."""
    group = Group(
        id="test-group",
        name="Test Group",
        image_type="screen_time",
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    return group


@pytest_asyncio.fixture
async def test_screenshot(db_session: AsyncSession, test_user: User) -> Screenshot:
    """Create a test screenshot."""
    screenshot = Screenshot(
        file_path="/test/screenshot1.png",
        image_type="screen_time",
        annotation_status="pending",
        processing_status="completed",
        target_annotations=2,
        current_annotation_count=0,
        uploaded_by_id=test_user.id,
    )
    db_session.add(screenshot)
    await db_session.commit()
    await db_session.refresh(screenshot)
    return screenshot


@pytest_asyncio.fixture
async def multiple_users(db_session: AsyncSession) -> list[User]:
    """Create multiple test users for multi-user tests."""
    users = []
    for i in range(3):
        user = User(
            username=f"annotator{i}",
            role="annotator",
            is_active=True,
        )
        db_session.add(user)
        users.append(user)
    await db_session.commit()
    for user in users:
        await db_session.refresh(user)
    return users


@pytest_asyncio.fixture
async def multiple_screenshots(db_session: AsyncSession, test_user: User, test_group: Group) -> list[Screenshot]:
    """Create multiple test screenshots for batch testing."""
    screenshots = []
    for i in range(5):
        screenshot = Screenshot(
            file_path=f"/test/screenshot{i}.png",
            image_type="screen_time",
            annotation_status="pending",
            processing_status="completed",
            target_annotations=2,
            current_annotation_count=0,
            uploaded_by_id=test_user.id,
            group_id=test_group.id,
        )
        db_session.add(screenshot)
        screenshots.append(screenshot)
    await db_session.commit()
    for screenshot in screenshots:
        await db_session.refresh(screenshot)
    return screenshots


def auth_headers(username: str) -> dict[str, str]:
    """
    Helper function to create authentication headers.

    The application uses header-based authentication via X-Username header.
    """
    return {"X-Username": username}
