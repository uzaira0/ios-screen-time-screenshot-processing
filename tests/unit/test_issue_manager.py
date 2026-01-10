"""Unit tests for issue_manager module — processing issue tracking."""

from __future__ import annotations

from screenshot_processor.core.issue_manager import IssueManager
from screenshot_processor.core.models import (
    BlockingIssue,
    GraphDetectionIssue,
    Issue,
    NonBlockingIssue,
    TitleMissingIssue,
    TotalNotFoundIssue,
    TotalOverestimationLargeIssue,
    TotalUnderestimationSmallIssue,
)


# Concrete issue for testing (NonBlockingIssue requires get_message)
class _TestNonBlockingIssue(NonBlockingIssue):
    def get_message(self) -> str:
        return f"Test non-blocking: {self.description}"


class _TestBlockingIssue(BlockingIssue):
    def get_message(self) -> str:
        return f"Test blocking: {self.description}"


class TestIssueManagerBasics:
    def test_initially_empty(self):
        mgr = IssueManager()
        assert not mgr.has_issues()
        assert mgr.get_issues() == []

    def test_add_issue(self):
        mgr = IssueManager()
        issue = _TestNonBlockingIssue("problem")
        mgr.add_issue(issue)
        assert mgr.has_issues()
        assert len(mgr.get_issues()) == 1

    def test_remove_issue(self):
        mgr = IssueManager()
        issue = _TestNonBlockingIssue("problem")
        mgr.add_issue(issue)
        mgr.remove_issue(issue)
        assert not mgr.has_issues()

    def test_remove_nonexistent_issue_noop(self):
        mgr = IssueManager()
        issue = _TestNonBlockingIssue("ghost")
        mgr.remove_issue(issue)  # should not raise
        assert not mgr.has_issues()

    def test_remove_all_issues(self):
        mgr = IssueManager()
        mgr.add_issue(_TestNonBlockingIssue("a"))
        mgr.add_issue(_TestBlockingIssue("b"))
        mgr.remove_all_issues()
        assert not mgr.has_issues()

    def test_get_issues_returns_copy(self):
        mgr = IssueManager()
        issue = _TestNonBlockingIssue("copy test")
        mgr.add_issue(issue)
        copy = mgr.get_issues()
        copy.clear()
        # Original should still have the issue
        assert mgr.has_issues()


class TestIssueManagerClassFiltering:
    def test_add_replaces_same_class(self):
        mgr = IssueManager()
        issue1 = _TestNonBlockingIssue("first")
        issue2 = _TestNonBlockingIssue("second")
        mgr.add_issue(issue1)
        mgr.add_issue(issue2)
        # Should have replaced the first one
        issues = mgr.get_issues()
        assert len(issues) == 1
        assert issues[0].description == "second"

    def test_remove_issues_of_class(self):
        mgr = IssueManager()
        mgr.add_issue(_TestNonBlockingIssue("nb"))
        mgr.add_issue(_TestBlockingIssue("b"))
        mgr.remove_issues_of_class(_TestNonBlockingIssue)
        issues = mgr.get_issues()
        assert len(issues) == 1
        assert isinstance(issues[0], _TestBlockingIssue)

    def test_has_issue_of_class(self):
        mgr = IssueManager()
        mgr.add_issue(_TestBlockingIssue("b"))
        assert mgr.has_issue_of_class(_TestBlockingIssue)
        assert not mgr.has_issue_of_class(_TestNonBlockingIssue)


class TestIssueManagerBlockingDetection:
    def test_has_blocking_issues(self):
        mgr = IssueManager()
        mgr.add_issue(_TestBlockingIssue("critical"))
        assert mgr.has_blocking_issues()

    def test_non_blocking_not_counted(self):
        mgr = IssueManager()
        mgr.add_issue(_TestNonBlockingIssue("minor"))
        assert not mgr.has_blocking_issues()

    def test_get_first_blocking_issue(self):
        mgr = IssueManager()
        blocking = _TestBlockingIssue("block")
        mgr.add_issue(_TestNonBlockingIssue("minor"))
        mgr.add_issue(blocking)
        assert mgr.get_first_blocking_issue() is blocking

    def test_get_first_blocking_issue_none(self):
        mgr = IssueManager()
        mgr.add_issue(_TestNonBlockingIssue("minor"))
        assert mgr.get_first_blocking_issue() is None

    def test_get_most_important_issue_prefers_blocking(self):
        mgr = IssueManager()
        nb = _TestNonBlockingIssue("minor")
        b = _TestBlockingIssue("critical")
        mgr.add_issue(nb)
        mgr.add_issue(b)
        assert mgr.get_most_important_issue() is b

    def test_get_most_important_issue_returns_first_when_no_blocking(self):
        mgr = IssueManager()
        nb = _TestNonBlockingIssue("minor")
        mgr.add_issue(nb)
        assert mgr.get_most_important_issue() is nb

    def test_get_most_important_issue_empty(self):
        mgr = IssueManager()
        assert mgr.get_most_important_issue() is None


class TestIssueManagerObservers:
    def test_observer_called_on_add(self):
        mgr = IssueManager()
        calls = []
        mgr.register_observer(lambda: calls.append("added"))
        mgr.add_issue(_TestNonBlockingIssue("x"))
        # add_issue calls remove_issues_of_class first (notify), then appends (notify)
        assert len(calls) >= 1

    def test_observer_called_on_remove(self):
        mgr = IssueManager()
        calls = []
        issue = _TestNonBlockingIssue("x")
        mgr.add_issue(issue)
        mgr.register_observer(lambda: calls.append("removed"))
        mgr.remove_issue(issue)
        assert len(calls) >= 1

    def test_unregister_observer(self):
        mgr = IssueManager()
        calls = []
        observer = lambda: calls.append("ping")
        mgr.register_observer(observer)
        mgr.unregister_observer(observer)
        mgr.add_issue(_TestNonBlockingIssue("x"))
        assert len(calls) == 0

    def test_duplicate_register_ignored(self):
        mgr = IssueManager()
        calls = []
        observer = lambda: calls.append("ping")
        mgr.register_observer(observer)
        mgr.register_observer(observer)  # duplicate
        mgr.add_issue(_TestNonBlockingIssue("x"))
        # Should only fire once per notification (not twice)
        assert calls.count("ping") <= 3  # at most from remove_of_class + append

    def test_failing_observer_does_not_break_others(self):
        mgr = IssueManager()
        calls = []

        def bad_observer():
            raise RuntimeError("boom")

        mgr.register_observer(bad_observer)
        mgr.register_observer(lambda: calls.append("ok"))
        mgr.add_issue(_TestNonBlockingIssue("x"))
        assert "ok" in calls


class TestConcreteIssueClasses:
    def test_graph_detection_issue_is_blocking(self):
        issue = GraphDetectionIssue("graph problem")
        assert isinstance(issue, BlockingIssue)
        assert "graph detection" in issue.get_message().lower()

    def test_title_missing_issue_is_non_blocking(self):
        issue = TitleMissingIssue("no title")
        assert isinstance(issue, NonBlockingIssue)
        assert "title" in issue.get_message().lower()
        # TitleMissingIssue uses rgb(255,165,0) which is orange
        assert "255,165,0" in issue.get_style()

    def test_total_not_found_is_non_blocking(self):
        issue = TotalNotFoundIssue("no total")
        assert isinstance(issue, NonBlockingIssue)
        assert "total" in issue.get_message().lower()

    def test_total_underestimation_small_is_non_blocking(self):
        issue = TotalUnderestimationSmallIssue("small diff")
        assert isinstance(issue, NonBlockingIssue)

    def test_total_overestimation_large_is_blocking(self):
        issue = TotalOverestimationLargeIssue("big diff")
        assert isinstance(issue, BlockingIssue)
        assert "WARNING" in issue.get_message()

    def test_styled_message_returns_tuple(self):
        issue = GraphDetectionIssue("test")
        msg, style = issue.get_styled_message()
        assert isinstance(msg, str)
        assert isinstance(style, str)
