"""
Unit tests for auth_service module.

Tests user lookup, creation, and auto-creation logic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screenshot_processor.web.database.models import User, UserRole
from screenshot_processor.web.services.auth_service import (
    create_user,
    get_or_create_user,
    get_user_by_username,
)


class TestGetUserByUsername:
    """Tests for get_user_by_username."""

    @pytest.mark.asyncio
    async def test_existing_user(self, db_session: AsyncSession):
        user = User(username="auth_existing", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()

        result = await get_user_by_username(db_session, "auth_existing")
        assert result is not None
        assert result.username == "auth_existing"

    @pytest.mark.asyncio
    async def test_nonexistent_user(self, db_session: AsyncSession):
        result = await get_user_by_username(db_session, "nobody")
        assert result is None

    @pytest.mark.asyncio
    async def test_case_sensitive(self, db_session: AsyncSession):
        user = User(username="CaseSensitive", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()

        assert await get_user_by_username(db_session, "CaseSensitive") is not None
        assert await get_user_by_username(db_session, "casesensitive") is None


class TestGetOrCreateUser:
    """Tests for get_or_create_user."""

    @pytest.mark.asyncio
    async def test_creates_new_user(self, db_session: AsyncSession):
        result = await get_or_create_user(db_session, "brand_new_user")
        assert result is not None
        assert result.username == "brand_new_user"
        assert result.role == UserRole.ANNOTATOR.value
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_returns_existing_user(self, db_session: AsyncSession):
        user = User(username="already_here", role="annotator", is_active=True)
        db_session.add(user)
        await db_session.commit()
        original_id = user.id

        result = await get_or_create_user(db_session, "already_here")
        assert result.id == original_id

    @pytest.mark.asyncio
    async def test_admin_username_gets_admin_role(self, db_session: AsyncSession):
        result = await get_or_create_user(db_session, "admin")
        assert result.role == UserRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_admin_case_insensitive(self, db_session: AsyncSession):
        result = await get_or_create_user(db_session, "Admin")
        assert result.role == UserRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_non_admin_gets_annotator_role(self, db_session: AsyncSession):
        result = await get_or_create_user(db_session, "regular_joe")
        assert result.role == UserRole.ANNOTATOR.value

    @pytest.mark.asyncio
    async def test_user_persisted_to_db(self, db_session: AsyncSession):
        await get_or_create_user(db_session, "persisted_user")
        row = await db_session.execute(
            select(User).where(User.username == "persisted_user")
        )
        assert row.scalar_one_or_none() is not None


class TestCreateUser:
    """Tests for create_user."""

    @pytest.mark.asyncio
    async def test_create_with_default_role(self, db_session: AsyncSession):
        result = await create_user(db_session, "default_role_user")
        assert result.role == UserRole.ANNOTATOR.value
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_create_with_admin_role(self, db_session: AsyncSession):
        result = await create_user(db_session, "new_admin", role=UserRole.ADMIN)
        assert result.role == UserRole.ADMIN.value

    @pytest.mark.asyncio
    async def test_create_returns_refreshed_user(self, db_session: AsyncSession):
        result = await create_user(db_session, "refreshed_user")
        assert result.id is not None
        assert result.created_at is not None
