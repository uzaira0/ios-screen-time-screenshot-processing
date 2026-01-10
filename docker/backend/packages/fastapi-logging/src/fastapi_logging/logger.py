"""Logger factory."""

from __future__ import annotations

import structlog


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Bound structlog logger

    Example:
        logger = get_logger(__name__)
        logger.info("Processing item", item_id=123, user="jane")
    """
    return structlog.get_logger(name)
