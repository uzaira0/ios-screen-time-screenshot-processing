"""Username validation utilities."""

from __future__ import annotations

import re
from typing import Final

# Username must be alphanumeric with underscores/hyphens, 3-50 chars
USERNAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")
USERNAME_MIN_LENGTH: Final[int] = 3
USERNAME_MAX_LENGTH: Final[int] = 50


class UsernameValidationError(ValueError):
    """Raised when username validation fails."""

    pass


def validate_username(username: str) -> str:
    """Validate and normalize username.

    Args:
        username: Raw username string

    Returns:
        Normalized username (stripped of whitespace)

    Raises:
        UsernameValidationError: If username is invalid
    """
    username = username.strip()

    if not username:
        raise UsernameValidationError("Username cannot be empty")

    if len(username) < USERNAME_MIN_LENGTH:
        raise UsernameValidationError(
            f"Username must be at least {USERNAME_MIN_LENGTH} characters"
        )

    if len(username) > USERNAME_MAX_LENGTH:
        raise UsernameValidationError(
            f"Username must be at most {USERNAME_MAX_LENGTH} characters"
        )

    if not USERNAME_PATTERN.match(username):
        raise UsernameValidationError(
            "Username must contain only letters, numbers, underscores, and hyphens"
        )

    return username
