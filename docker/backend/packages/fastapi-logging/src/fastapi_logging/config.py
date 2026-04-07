"""Logging configuration."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(
    *,
    level: str = "INFO",
    json_format: bool = False,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, output JSON logs (for production)

    Example:
        # Development - pretty console output
        setup_logging(level="DEBUG", json_format=False)

        # Production - JSON output for log aggregators
        setup_logging(level="INFO", json_format=True)
    """
    # Shared processors for all output
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_request_id,
    ]

    if json_format:
        # JSON output for production
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Pretty console output for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(level),
    )


def _add_request_id(logger, method_name, event_dict):
    """Add request ID to log event if available."""
    from .context import get_request_id

    request_id = get_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict
