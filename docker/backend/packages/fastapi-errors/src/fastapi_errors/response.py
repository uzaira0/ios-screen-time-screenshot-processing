"""Error response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response format.

    All error responses follow this structure:
    {
        "error": {
            "code": "NOT_FOUND",
            "message": "User with id=123 not found",
            "details": {}
        },
        "request_id": "abc-123"  # Optional
    }
    """

    error: ErrorDetail
    request_id: str | None = None


class ErrorDetail(BaseModel):
    """Error detail within response."""

    code: str
    message: str
    details: dict[str, Any] = {}
