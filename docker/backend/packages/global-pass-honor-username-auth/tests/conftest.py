"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest
from pydantic_settings import BaseSettings

from global_auth import AuthSettingsMixin


class TestSettings(AuthSettingsMixin, BaseSettings):
    """Test settings class."""

    pass


@pytest.fixture
def settings_no_password() -> TestSettings:
    """Settings with no password required."""
    return TestSettings(SITE_PASSWORD="", ADMIN_USERNAMES="admin")


@pytest.fixture
def settings_with_password() -> TestSettings:
    """Settings with password required."""
    return TestSettings(SITE_PASSWORD="secret123", ADMIN_USERNAMES="admin,superuser")
