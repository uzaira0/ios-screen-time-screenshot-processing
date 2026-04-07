from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from .models import BlockingIssue

if TYPE_CHECKING:
    from .models import Issue

logger = logging.getLogger(__name__)


class IssueManager:
    def __init__(self) -> None:
        self._issues: list[Issue] = []
        self._observers: list[Callable[[], None]] = []

    def register_observer(self, observer: Callable[[], None]) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unregister_observer(self, observer: Callable[[], None]) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self) -> None:
        for observer in self._observers:
            try:
                observer()
            except Exception:
                logger.exception("Observer notification failed")

    def add_issue(self, issue: Issue) -> None:
        self.remove_issues_of_class(issue.__class__)
        self._issues.append(issue)
        self.notify_observers()

    def remove_issue(self, issue: Issue) -> None:
        if issue in self._issues:
            self._issues.remove(issue)
            self.notify_observers()

    def remove_issues_of_class(self, issue_class: type[Issue]) -> None:
        self._issues = [i for i in self._issues if not isinstance(i, issue_class)]
        self.notify_observers()

    def remove_all_issues(self) -> None:
        self._issues.clear()
        self.notify_observers()

    def has_issues(self) -> bool:
        return len(self._issues) > 0

    def has_blocking_issues(self) -> bool:
        return any(isinstance(issue, BlockingIssue) for issue in self._issues)

    def has_issue_of_class(self, issue_class: type[Issue]) -> bool:
        return any(isinstance(issue, issue_class) for issue in self._issues)

    def get_issues(self) -> list[Issue]:
        return self._issues.copy()

    def get_first_blocking_issue(self) -> Issue | None:
        blocking_issues = [issue for issue in self._issues if isinstance(issue, BlockingIssue)]
        return blocking_issues[0] if blocking_issues else None

    def get_most_important_issue(self) -> Issue | None:
        blocking_issue = self.get_first_blocking_issue()
        if blocking_issue:
            return blocking_issue
        return self._issues[0] if self._issues else None
