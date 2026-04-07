"""Tests for AuthSettingsMixin configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings

from global_auth import AuthSettingsMixin


class TestSettings(AuthSettingsMixin, BaseSettings):
    """Test settings class."""

    pass


class TestAuthSettingsMixin:
    """Tests for AuthSettingsMixin."""

    def test_default_values(self) -> None:
        """Default values are correct."""
        settings = TestSettings()
        assert settings.SITE_PASSWORD == ""
        assert settings.site_password == ""
        assert settings.password_required is False

    def test_site_password_property(self) -> None:
        """site_password property returns SITE_PASSWORD."""
        settings = TestSettings(SITE_PASSWORD="secret")
        assert settings.site_password == "secret"
        assert settings.password_required is True

    def test_password_required_false_when_empty(self) -> None:
        """password_required is False when SITE_PASSWORD is empty."""
        settings = TestSettings(SITE_PASSWORD="")
        assert settings.password_required is False

    def test_password_required_true_when_set(self) -> None:
        """password_required is True when SITE_PASSWORD is set."""
        settings = TestSettings(SITE_PASSWORD="any-password")
        assert settings.password_required is True

    def test_admin_usernames_default(self) -> None:
        """Default admin username is 'admin'."""
        settings = TestSettings()
        assert settings.admin_usernames_list == ["admin"]

    def test_admin_usernames_parsed(self) -> None:
        """Comma-separated admin usernames are parsed to list."""
        settings = TestSettings(ADMIN_USERNAMES="admin, superuser, root")
        assert settings.admin_usernames_list == ["admin", "superuser", "root"]

    def test_admin_usernames_lowercase(self) -> None:
        """Admin usernames are normalized to lowercase."""
        settings = TestSettings(ADMIN_USERNAMES="ADMIN, SuperUser")
        assert settings.admin_usernames_list == ["admin", "superuser"]

    def test_admin_usernames_whitespace_stripped(self) -> None:
        """Whitespace is stripped from admin usernames."""
        settings = TestSettings(ADMIN_USERNAMES="  admin  ,  user  ")
        assert settings.admin_usernames_list == ["admin", "user"]

    def test_admin_usernames_empty_entries_filtered(self) -> None:
        """Empty entries in admin usernames are filtered out."""
        settings = TestSettings(ADMIN_USERNAMES="admin,,user,")
        assert settings.admin_usernames_list == ["admin", "user"]
