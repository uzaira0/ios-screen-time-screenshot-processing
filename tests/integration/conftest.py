"""
Integration test fixtures.

This module provides integration-specific fixtures.
Shared fixtures are inherited from tests/conftest.py.
"""

from __future__ import annotations


def auth_headers(username: str) -> dict[str, str]:
    """
    Helper function to create authentication headers.

    The application uses header-based authentication via X-Username header.
    """
    return {"X-Username": username}
