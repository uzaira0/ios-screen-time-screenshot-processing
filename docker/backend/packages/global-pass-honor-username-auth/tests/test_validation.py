"""Tests for username validation."""

from __future__ import annotations

import pytest

from global_auth import (
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    UsernameValidationError,
    validate_username,
)


class TestValidateUsername:
    """Tests for validate_username function."""

    def test_valid_username(self) -> None:
        """Valid usernames are returned stripped."""
        assert validate_username("john") == "john"
        assert validate_username("  alice  ") == "alice"
        assert validate_username("user_123") == "user_123"
        assert validate_username("test-user") == "test-user"

    def test_empty_username_raises(self) -> None:
        """Empty usernames raise UsernameValidationError."""
        with pytest.raises(UsernameValidationError, match="cannot be empty"):
            validate_username("")

        with pytest.raises(UsernameValidationError, match="cannot be empty"):
            validate_username("   ")

    def test_username_too_short(self) -> None:
        """Usernames shorter than minimum raise error."""
        with pytest.raises(
            UsernameValidationError, match=f"at least {USERNAME_MIN_LENGTH}"
        ):
            validate_username("ab")

    def test_username_too_long(self) -> None:
        """Usernames longer than maximum raise error."""
        long_name = "a" * (USERNAME_MAX_LENGTH + 1)
        with pytest.raises(
            UsernameValidationError, match=f"at most {USERNAME_MAX_LENGTH}"
        ):
            validate_username(long_name)

    def test_username_invalid_characters(self) -> None:
        """Usernames with invalid characters raise error."""
        # Each name must be at least 3 chars to pass length check first
        invalid_names = ["user@name", "user name", "user.name", "user/name", "用户名称"]

        for name in invalid_names:
            with pytest.raises(UsernameValidationError, match="only letters"):
                validate_username(name)

    def test_username_edge_cases(self) -> None:
        """Edge case usernames are handled correctly."""
        # Exactly minimum length
        assert validate_username("abc") == "abc"

        # Exactly maximum length
        max_name = "a" * USERNAME_MAX_LENGTH
        assert validate_username(max_name) == max_name

        # All valid character types
        assert validate_username("User_Name-123") == "User_Name-123"
