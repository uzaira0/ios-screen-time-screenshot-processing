"""Request context management using context variables."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# Context variable for request ID
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Get the current request ID."""
    return request_id_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID for the current context.

    Args:
        request_id: Request ID to set, or None to generate a new one

    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]  # Short UUID
    request_id_var.set(request_id)
    return request_id
