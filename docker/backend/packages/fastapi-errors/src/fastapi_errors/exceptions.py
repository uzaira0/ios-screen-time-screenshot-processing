"""Standard exception classes for FastAPI applications."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base exception for application errors.

    All custom exceptions should inherit from this.
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppError):
    """Resource not found (404).

    Example:
        raise NotFoundError("User", user_id)  # "User 123 not found"
        raise NotFoundError("File", filename, field="filename")
    """

    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(
        self,
        resource: str,
        identifier: Any = None,
        *,
        field: str = "id",
        details: dict[str, Any] | None = None,
    ):
        if identifier is not None:
            message = f"{resource} with {field}={identifier!r} not found"
        else:
            message = f"{resource} not found"
        super().__init__(message, details=details)
        self.resource = resource
        self.identifier = identifier


class ConflictError(AppError):
    """Resource conflict (409).

    Example:
        raise ConflictError("User with this email already exists")
        raise ConflictError("File", filename, field="filename")
    """

    status_code = 409
    error_code = "CONFLICT"

    def __init__(
        self,
        message_or_resource: str,
        identifier: Any = None,
        *,
        field: str = "id",
        details: dict[str, Any] | None = None,
    ):
        if identifier is not None:
            message = f"{message_or_resource} with {field}={identifier!r} already exists"
        else:
            message = message_or_resource
        super().__init__(message, details=details)


class ValidationError(AppError):
    """Validation error (422).

    Example:
        raise ValidationError("Invalid email format", field="email")
        raise ValidationError("Value must be positive", field="amount", value=-5)
    """

    status_code = 422
    error_code = "VALIDATION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        details: dict[str, Any] | None = None,
    ):
        _details = details or {}
        if field:
            _details["field"] = field
        if value is not None:
            _details["value"] = value
        super().__init__(message, details=_details)


class ForbiddenError(AppError):
    """Access forbidden (403).

    Example:
        raise ForbiddenError("You don't have permission to access this resource")
    """

    status_code = 403
    error_code = "FORBIDDEN"


class UnauthorizedError(AppError):
    """Authentication required (401).

    Example:
        raise UnauthorizedError("Invalid credentials")
    """

    status_code = 401
    error_code = "UNAUTHORIZED"


class BadRequestError(AppError):
    """Bad request (400).

    Example:
        raise BadRequestError("Invalid JSON format")
    """

    status_code = 400
    error_code = "BAD_REQUEST"


class InternalError(AppError):
    """Internal server error (500).

    Example:
        raise InternalError("Database connection failed")
    """

    status_code = 500
    error_code = "INTERNAL_ERROR"
