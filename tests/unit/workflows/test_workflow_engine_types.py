"""Tests for workflow engine types — must match Temporal Python SDK interfaces."""

from datetime import timedelta

import pytest


class TestRetryPolicy:
    def test_default_values_match_temporal(self):
        """RetryPolicy defaults must match temporalio.common.RetryPolicy."""
        from screenshot_processor.workflows.engine.types import RetryPolicy

        rp = RetryPolicy()
        assert rp.initial_interval == timedelta(seconds=1)
        assert rp.backoff_coefficient == 2.0
        assert rp.maximum_interval is None
        assert rp.maximum_attempts == 0
        assert rp.non_retryable_error_types is None

    def test_custom_values(self):
        from screenshot_processor.workflows.engine.types import RetryPolicy

        rp = RetryPolicy(
            initial_interval=timedelta(seconds=30),
            backoff_coefficient=3.0,
            maximum_interval=timedelta(minutes=10),
            maximum_attempts=5,
            non_retryable_error_types=["ValueError", "KeyError"],
        )
        assert rp.maximum_attempts == 5
        assert rp.non_retryable_error_types == ["ValueError", "KeyError"]


class TestNonRetryableError:
    def test_wraps_cause(self):
        from screenshot_processor.workflows.engine.types import NonRetryableError

        cause = ValueError("bad CSV format")
        err = NonRetryableError("permanent failure", cause=cause)
        assert err.__cause__ is cause
        assert str(err) == "permanent failure"

    def test_without_cause(self):
        from screenshot_processor.workflows.engine.types import NonRetryableError

        err = NonRetryableError("file not found")
        assert err.__cause__ is None


class TestWorkflowStatus:
    def test_enum_values(self):
        from screenshot_processor.workflows.engine.types import WorkflowStatus

        assert WorkflowStatus.PENDING == "pending"
        assert WorkflowStatus.RUNNING == "running"
        assert WorkflowStatus.COMPLETED == "completed"
        assert WorkflowStatus.FAILED == "failed"
        assert WorkflowStatus.CANCELLED == "cancelled"


class TestActivityStatus:
    def test_enum_values(self):
        from screenshot_processor.workflows.engine.types import ActivityStatus

        assert ActivityStatus.PENDING == "pending"
        assert ActivityStatus.RUNNING == "running"
        assert ActivityStatus.COMPLETED == "completed"
        assert ActivityStatus.FAILED == "failed"
        assert ActivityStatus.SKIPPED == "skipped"


class TestActivityInfo:
    def test_fields(self):
        from screenshot_processor.workflows.engine.types import ActivityInfo

        info = ActivityInfo(
            activity_id="123",
            activity_type="device_detection",
            attempt=2,
            workflow_id="wf-456",
            workflow_type="preprocessing",
        )
        assert info.activity_id == "123"
        assert info.attempt == 2
        assert info.workflow_type == "preprocessing"
