from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    def __call__(self, current: int, total: int, message: str = "") -> None: ...


class IssueCallback(Protocol):
    def __call__(self) -> None: ...


class CancellationCheck(Protocol):
    def __call__(self) -> bool: ...


class LogCallback(Protocol):
    def __call__(self, level: str, message: str) -> None: ...
