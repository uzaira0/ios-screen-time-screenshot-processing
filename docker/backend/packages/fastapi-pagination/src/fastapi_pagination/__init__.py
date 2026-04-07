"""Pagination utilities for FastAPI with SQLAlchemy.

Example usage:
    from fastapi_pagination import PaginationParams, PaginatedResponse, paginate

    @app.get("/items", response_model=PaginatedResponse[ItemOut])
    async def list_items(
        pagination: PaginationParams = Depends(),
        db: AsyncSession = Depends(get_db),
    ):
        query = select(Item)
        return await paginate(db, query, pagination)
"""

from __future__ import annotations

from .params import PaginationParams
from .response import PaginatedResponse
from .paginator import paginate, paginate_query

__all__ = [
    "PaginationParams",
    "PaginatedResponse",
    "paginate",
    "paginate_query",
]

__version__ = "0.1.0"
