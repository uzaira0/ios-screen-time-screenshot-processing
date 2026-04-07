"""Tests for FastAPI dependencies."""

from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from pydantic_settings import BaseSettings

from global_auth import (
    AuthSettingsMixin,
    create_verify_site_password,
    get_username_optional,
    get_username_required,
)


class TestSettings(AuthSettingsMixin, BaseSettings):
    """Test settings class."""

    pass


class TestVerifySitePassword:
    """Tests for create_verify_site_password."""

    def test_no_password_required(self) -> None:
        """When SITE_PASSWORD is empty, all requests succeed."""
        settings = TestSettings(SITE_PASSWORD="")
        verify = create_verify_site_password(lambda: settings)

        result = verify(None)
        assert result == ""

        result = verify("any-password")
        assert result == ""

    def test_password_required_missing_header(self) -> None:
        """When password required but header missing, raises 401."""
        settings = TestSettings(SITE_PASSWORD="secret")
        verify = create_verify_site_password(lambda: settings)

        with pytest.raises(HTTPException) as exc_info:
            verify(None)

        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail.lower()

    def test_password_required_wrong_password(self) -> None:
        """When password incorrect, raises 401."""
        settings = TestSettings(SITE_PASSWORD="secret")
        verify = create_verify_site_password(lambda: settings)

        with pytest.raises(HTTPException) as exc_info:
            verify("wrong-password")

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    def test_password_correct(self) -> None:
        """When password correct, returns it."""
        settings = TestSettings(SITE_PASSWORD="secret")
        verify = create_verify_site_password(lambda: settings)

        result = verify("secret")
        assert result == "secret"

    def test_uses_constant_time_comparison(self) -> None:
        """Verify timing attack protection is in place."""
        # Check that secrets.compare_digest is used in the source
        from global_auth.dependencies import create_verify_site_password

        source = inspect.getsource(create_verify_site_password)
        assert "secrets.compare_digest" in source


class TestGetUsernameOptional:
    """Tests for get_username_optional."""

    def test_returns_anonymous_when_missing(self) -> None:
        """Returns 'anonymous' when header is missing."""
        result = get_username_optional(None)
        assert result == "anonymous"

    def test_returns_anonymous_when_empty(self) -> None:
        """Returns 'anonymous' when header is empty."""
        result = get_username_optional("")
        assert result == "anonymous"

        result = get_username_optional("   ")
        assert result == "anonymous"

    def test_returns_username_when_provided(self) -> None:
        """Returns username when provided."""
        result = get_username_optional("john")
        assert result == "john"

    def test_strips_whitespace(self) -> None:
        """Strips whitespace from username."""
        result = get_username_optional("  alice  ")
        assert result == "alice"


class TestGetUsernameRequired:
    """Tests for get_username_required."""

    def test_raises_when_missing(self) -> None:
        """Raises 401 when header is missing."""
        with pytest.raises(HTTPException) as exc_info:
            get_username_required(None)

        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail.lower()

    def test_raises_when_invalid(self) -> None:
        """Raises 400 when username is invalid."""
        with pytest.raises(HTTPException) as exc_info:
            get_username_required("ab")  # Too short

        assert exc_info.value.status_code == 400

    def test_returns_validated_username(self) -> None:
        """Returns validated username."""
        result = get_username_required("john")
        assert result == "john"

    def test_strips_whitespace(self) -> None:
        """Strips whitespace from username."""
        result = get_username_required("  alice  ")
        assert result == "alice"
