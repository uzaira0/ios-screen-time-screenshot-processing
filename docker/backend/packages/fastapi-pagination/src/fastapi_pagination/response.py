"""Paginated response models."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, computed_field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model.

    Usage:
        @app.get("/items", response_model=PaginatedResponse[ItemOut])
        async def list_items(...):
            return PaginatedResponse(
                items=[...],
                total=100,
                page=1,
                page_size=20,
            )

    Response:
        {
            "items": [...],
            "total": 100,
            "page": 1,
            "page_size": 20,
            "pages": 5,
            "has_next": true,
            "has_prev": false
        }
    """

    items: list[T]
    total: int
    page: int
    page_size: int

    @computed_field
    @property
    def pages(self) -> int:
        """Total number of pages."""
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @computed_field
    @property
    def has_next(self) -> bool:
        """Whether there is a next page."""
        return self.page < self.pages

    @computed_field
    @property
    def has_prev(self) -> bool:
        """Whether there is a previous page."""
        return self.page > 1
