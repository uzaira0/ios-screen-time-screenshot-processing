"""
Structured JSON logging configuration for production environments.

Usage:
    from screenshot_processor.web.logging_config import setup_logging
    setup_logging()  # Call once at startup

Features:
    - JSON format in production (LOG_FORMAT=json)
    - Human-readable format in development (default)
    - Request context (request_id, user, etc.)
    - Configurable via environment variables
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location info
        if record.pathname:
            log_obj["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        # These are added via logger.info("msg", extra={"key": "value"})
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_obj[key] = value

        return json.dumps(log_obj, default=str)


class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for development with colors."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        # Format: TIMESTAMP | LEVEL | LOGGER | MESSAGE
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"{timestamp} | {color}{record.levelname:8}{reset} | {record.name} | {record.getMessage()}"

        # Add exception if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def setup_logging(
    level: str | None = None,
    log_format: str | None = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to LOG_LEVEL env var or INFO.
        log_format: 'json' for structured JSON, 'text' for human-readable.
                   Defaults to LOG_FORMAT env var or 'text'.
    """
    level = level or os.getenv("LOG_LEVEL", "INFO")
    log_format = log_format or os.getenv("LOG_FORMAT", "text")

    # Get the root logger
    root_logger = logging.getLogger()

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Set formatter based on format type
    if log_format.lower() == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(DevelopmentFormatter())

    # Configure root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Usage:
        from screenshot_processor.web.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Message", extra={"user_id": 123, "action": "login"})
    """
    return logging.getLogger(name)


# Context manager for adding request context to logs
class LogContext:
    """Context manager for adding request-scoped fields to log records."""

    _context: dict[str, Any] = {}

    @classmethod
    def set(cls, **kwargs: Any) -> None:
        """Set context fields that will be added to all log records."""
        cls._context.update(kwargs)

    @classmethod
    def clear(cls) -> None:
        """Clear all context fields."""
        cls._context.clear()

    @classmethod
    def get(cls) -> dict[str, Any]:
        """Get current context."""
        return cls._context.copy()
