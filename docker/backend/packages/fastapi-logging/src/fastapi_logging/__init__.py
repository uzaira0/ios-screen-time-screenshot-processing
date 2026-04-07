"""Structured logging for FastAPI applications.

Example usage:
    from fastapi_logging import setup_logging, get_logger, RequestLoggingMiddleware

    setup_logging(json_format=settings.is_production)

    app.add_middleware(RequestLoggingMiddleware)

    logger = get_logger(__name__)
    logger.info("Processing item", item_id=123)
"""

from __future__ import annotations

from .config import setup_logging
from .logger import get_logger
from .middleware import RequestLoggingMiddleware
from .context import request_id_var, get_request_id, set_request_id

__all__ = [
    "setup_logging",
    "get_logger",
    "RequestLoggingMiddleware",
    "request_id_var",
    "get_request_id",
    "set_request_id",
]

__version__ = "0.1.0"
