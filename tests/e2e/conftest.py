"""
Fixtures for end-to-end tests.

Extends integration test fixtures with E2E-specific helpers.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import Group, Screenshot, User


@pytest_asyncio.fixture
async def multiple_users(db_session: AsyncSession) -> list[User]:
    """Create multiple users for multi-user testing."""
    users = [User(username=f"user{i}", role="annotator", is_active=True) for i in range(1, 4)]
    db_session.add_all(users)
    await db_session.commit()

    for user in users:
        await db_session.refresh(user)

    return users


@pytest_asyncio.fixture
async def test_group(db_session: AsyncSession) -> Group:
    """Create a test group."""
    group = Group(
        id="test_group",
        name="Test Group",
        image_type="screen_time",
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    return group


@pytest_asyncio.fixture
async def multiple_screenshots(
    db_session: AsyncSession,
    test_group: Group,
) -> list[Screenshot]:
    """Create multiple screenshots for batch testing."""
    screenshots = [
        Screenshot(
            file_path=f"/test/screenshot{i}.png",
            image_type="screen_time",
            group_id=test_group.id,
            participant_id=f"P{i:03d}",
            target_annotations=2,
        )
        for i in range(1, 6)
    ]
    db_session.add_all(screenshots)
    await db_session.commit()

    for screenshot in screenshots:
        await db_session.refresh(screenshot)

    return screenshots
