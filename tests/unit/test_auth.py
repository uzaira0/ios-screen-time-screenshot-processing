"""Tests for authentication and authorization functionality."""

from __future__ import annotations

import pytest

from global_auth.validation import (
    USERNAME_PATTERN,
    UsernameValidationError,
    validate_username,
)
from screenshot_processor.web.database.models import UserRole


class TestUsernameValidation:
    """Tests for username validation."""

    def test_validate_valid_username(self):
        """Valid usernames should pass validation."""
        valid_usernames = [
            "alice",
            "bob123",
            "user_name",
            "user-name",
            "ABC",
            "a1b2c3",
            "user_123-test",
            "abc",  # minimum 3 chars
            "a" * 50,  # maximum 50 chars
        ]
        for username in valid_usernames:
            result = validate_username(username)
            assert result == username

    def test_validate_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        assert validate_username("  alice  ") == "alice"
        assert validate_username("\talice\n") == "alice"

    def test_validate_empty_username_raises(self):
        """Empty username should raise HTTPException."""
        with pytest.raises(UsernameValidationError) as exc_info:
            validate_username("")
        assert exc_info.value is not None
        assert "cannot be empty" in str(exc_info.value)

    def test_validate_whitespace_only_raises(self):
        """Whitespace-only username should raise HTTPException."""
        with pytest.raises(UsernameValidationError) as exc_info:
            validate_username("   ")
        assert exc_info.value is not None
        assert "cannot be empty" in str(exc_info.value)

    def test_validate_too_short_raises(self):
        """Username shorter than 3 chars should raise UsernameValidationError."""
        with pytest.raises(UsernameValidationError) as exc_info:
            validate_username("ab")
        assert "at least 3" in str(exc_info.value)

    def test_validate_too_long_raises(self):
        """Username longer than 50 chars should raise UsernameValidationError."""
        with pytest.raises(UsernameValidationError) as exc_info:
            validate_username("a" * 51)
        assert "at most 50" in str(exc_info.value)

    def test_validate_invalid_characters_raises(self):
        """Username with invalid characters should raise HTTPException."""
        invalid_usernames = [
            "user@name",  # @ not allowed
            "user.name",  # . not allowed
            "user name",  # space not allowed
            "user!name",  # ! not allowed
            "user#name",  # # not allowed
            "user$name",  # $ not allowed
            "user%name",  # % not allowed
            "user&name",  # & not allowed
            "user/name",  # / not allowed (path traversal)
            "user\\name",  # \ not allowed
            "../admin",  # path traversal attempt
            "admin\x00",  # null byte injection
        ]
        for username in invalid_usernames:
            with pytest.raises(UsernameValidationError) as exc_info:
                validate_username(username)
            assert exc_info.value is not None

    def test_username_pattern_regex(self):
        """Test the username pattern regex directly."""
        # Valid patterns
        assert USERNAME_PATTERN.match("alice")
        assert USERNAME_PATTERN.match("alice_bob")
        assert USERNAME_PATTERN.match("alice-bob")
        assert USERNAME_PATTERN.match("alice123")
        assert USERNAME_PATTERN.match("ALICE")
        assert USERNAME_PATTERN.match("abc")
        assert USERNAME_PATTERN.match("a" * 50)

        # Invalid patterns
        assert not USERNAME_PATTERN.match("ab")  # too short
        assert not USERNAME_PATTERN.match("a" * 51)  # too long
        assert not USERNAME_PATTERN.match("alice@bob")
        assert not USERNAME_PATTERN.match("alice.bob")
        assert not USERNAME_PATTERN.match("alice bob")


class TestUserRole:
    """Tests for UserRole enum."""

    def test_role_values(self):
        """Test UserRole enum values."""
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.ANNOTATOR.value == "annotator"

    def test_role_is_string_enum(self):
        """UserRole should be a string enum for database compatibility."""
        assert isinstance(UserRole.ADMIN, str)
        assert isinstance(UserRole.ANNOTATOR, str)
        assert UserRole.ADMIN == "admin"
        assert UserRole.ANNOTATOR == "annotator"

    def test_role_comparison(self):
        """Test role comparison works correctly."""
        role = UserRole.ADMIN
        assert role == UserRole.ADMIN
        assert role == "admin"
        assert role != UserRole.ANNOTATOR
        assert role != "annotator"


class TestAuthorizationLogic:
    """Tests for authorization logic without database."""

    def test_admin_role_check(self):
        """Test admin role checking logic."""

        # Simulate the admin check from dependencies.py
        def is_admin(role: str) -> bool:
            return role == UserRole.ADMIN

        assert is_admin(UserRole.ADMIN)
        assert is_admin("admin")
        assert not is_admin(UserRole.ANNOTATOR)
        assert not is_admin("annotator")
        assert not is_admin("")

    def test_admin_whitelist_logic(self):
        """Test admin whitelist matching logic."""
        # Simulate the admin whitelist check from dependencies.py
        admin_usernames = ["admin", "superuser", "root"]

        def get_role_for_username(username: str) -> UserRole:
            return UserRole.ADMIN if username.lower() in admin_usernames else UserRole.ANNOTATOR

        assert get_role_for_username("admin") == UserRole.ADMIN
        assert get_role_for_username("ADMIN") == UserRole.ADMIN  # case insensitive
        assert get_role_for_username("Admin") == UserRole.ADMIN
        assert get_role_for_username("superuser") == UserRole.ADMIN
        assert get_role_for_username("root") == UserRole.ADMIN
        assert get_role_for_username("alice") == UserRole.ANNOTATOR
        assert get_role_for_username("bob") == UserRole.ANNOTATOR
