"""Protocol definitions for framework-agnostic callbacks.

This module defines callback interfaces using Protocol to allow the core business logic
to communicate with any UI framework (tkinter, PyQt, web, CLI) without coupling to them.
"""

from __future__ import annotations

from typing import Literal, Protocol


class ProgressCallback(Protocol):
    """Protocol for reporting progress during processing."""

    def __call__(self, current: int, total: int, message: str = "") -> None:
        """Report progress to the user interface.

        Args:
            current: Current item number being processed
            total: Total number of items to process
            message: Optional progress message
        """
        ...


class CancellationCheck(Protocol):
    """Protocol for checking if the operation should be cancelled."""

    def __call__(self) -> bool:
        """Check if the operation should be cancelled.

        Returns:
            True if the operation should be cancelled, False otherwise
        """
        ...


class LogCallback(Protocol):
    """Protocol for logging messages."""

    def __call__(self, level: Literal["info", "warning", "error"], message: str) -> None:
        """Log a message.

        Args:
            level: Log level (info, warning, error)
            message: Log message
        """
        ...
