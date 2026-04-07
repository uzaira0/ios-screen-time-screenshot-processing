"""Exception handlers for FastAPI."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from .exceptions import AppError
from .response import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def setup_error_handlers(app: FastAPI, *, debug: bool = False) -> None:
    """Register standard error handlers on the FastAPI app.

    Args:
        app: FastAPI application
        debug: If True, include exception details in 500 errors

    Example:
        app = FastAPI()
        setup_error_handlers(app)
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle custom application errors."""
        request_id = _get_request_id(request)

        response = ErrorResponse(
            error=ErrorDetail(
                code=exc.error_code,
                message=exc.message,
                details=exc.details,
            ),
            request_id=request_id,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle Pydantic validation errors from request parsing."""
        request_id = _get_request_id(request)

        # Format validation errors
        errors = []
        for error in exc.errors():
            loc = ".".join(str(x) for x in error["loc"])
            errors.append({"field": loc, "message": error["msg"]})

        response = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": errors},
            ),
            request_id=request_id,
        )

        return JSONResponse(
            status_code=422,
            content=response.model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        request_id = _get_request_id(request)

        # Always log unexpected errors
        logger.exception(f"Unhandled exception on {request.method} {request.url}: {exc}")

        # In debug mode, include exception details
        message = str(exc) if debug else "An unexpected error occurred"

        response = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message=message,
                details={},
            ),
            request_id=request_id,
        )

        return JSONResponse(
            status_code=500,
            content=response.model_dump(exclude_none=True),
        )


def _get_request_id(request: Request) -> str | None:
    """Extract request ID from request state or headers."""
    # Try request state first (set by logging middleware)
    if hasattr(request.state, "request_id"):
        return request.state.request_id

    # Try common request ID headers
    for header in ["X-Request-ID", "X-Correlation-ID", "Request-ID"]:
        if value := request.headers.get(header):
            return value

    return None
