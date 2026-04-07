"""Pagination parameters."""

from __future__ import annotations

from fastapi import Query


class PaginationParams:
    """Pagination parameters as FastAPI dependency.

    Usage:
        @app.get("/items")
        async def list_items(pagination: PaginationParams = Depends()):
            ...

    Query parameters:
        - page: Page number (1-indexed, default: 1)
        - page_size: Items per page (default: 20, max: 100)
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        """Calculate offset for SQL query."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for SQL query (same as page_size)."""
        return self.page_size
