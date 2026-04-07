"""Standard error handling for FastAPI applications.

Example usage:
    from fastapi_errors import setup_error_handlers, NotFoundError

    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/items/{id}")
    async def get_item(id: int):
        item = await find_item(id)
        if not item:
            raise NotFoundError("Item", id)
        return item
"""

from __future__ import annotations

from .exceptions import (
    AppError,
    NotFoundError,
    ConflictError,
    ValidationError,
    ForbiddenError,
    UnauthorizedError,
    BadRequestError,
    InternalError,
)
from .handlers import setup_error_handlers
from .response import ErrorResponse

__all__ = [
    # Setup
    "setup_error_handlers",
    # Base exception
    "AppError",
    # HTTP exceptions
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "ForbiddenError",
    "UnauthorizedError",
    "BadRequestError",
    "InternalError",
    # Response model
    "ErrorResponse",
]

__version__ = "0.1.0"
