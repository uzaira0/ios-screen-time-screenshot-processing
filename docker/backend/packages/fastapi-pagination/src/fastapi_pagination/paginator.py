"""Pagination utilities for SQLAlchemy queries."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .params import PaginationParams
from .response import PaginatedResponse

T = TypeVar("T")


async def paginate(
    db: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> PaginatedResponse[Any]:
    """Paginate a SQLAlchemy query.

    Args:
        db: Async database session
        query: SQLAlchemy select statement
        params: Pagination parameters

    Returns:
        PaginatedResponse with items and pagination metadata

    Example:
        @app.get("/items", response_model=PaginatedResponse[ItemOut])
        async def list_items(
            pagination: PaginationParams = Depends(),
            db: AsyncSession = Depends(get_db),
        ):
            query = select(Item).order_by(Item.created_at.desc())
            return await paginate(db, query, pagination)
    """
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated items
    paginated_query = query.offset(params.offset).limit(params.limit)
    result = await db.execute(paginated_query)
    items = list(result.scalars().all())

    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


async def paginate_query(
    db: AsyncSession,
    query: Select,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResponse[Any]:
    """Paginate a query with explicit page and page_size.

    Convenience function when not using PaginationParams dependency.

    Args:
        db: Async database session
        query: SQLAlchemy select statement
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        PaginatedResponse with items and pagination metadata
    """
    params = PaginationParams.__new__(PaginationParams)
    params.page = page
    params.page_size = page_size
    return await paginate(db, query, params)
