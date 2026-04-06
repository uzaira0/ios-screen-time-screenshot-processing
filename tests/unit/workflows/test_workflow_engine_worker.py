"""Tests for the WorkflowWorker — error classification, retry, backoff."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from screenshot_processor.web.database.models import Base
from screenshot_processor.workflows.engine.models import (
    ActivityExecution,
    WorkflowExecution,
    WorkflowSignal,
)
from screenshot_processor.workflows.engine.types import (
    ActivityStatus,
    NonRetryableError,
    RetryPolicy,
    WorkflowStatus,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def workflow_with_activities(db_session):
    """Create a workflow with one pending activity."""
    wf = WorkflowExecution(
        screenshot_id=1,
        workflow_type="preprocessing",
        status="running",
        current_activity="device_detection",
    )
    db_session.add(wf)
    db_session.flush()

    act = ActivityExecution(
        workflow_id=wf.id,
        activity_name="device_detection",
        status="pending",
        attempt=1,
        is_blocking=True,
    )
    db_session.add(act)
    db_session.commit()
    return wf, act


class TestErrorClassification:
    def test_transient_errors(self):
        from screenshot_processor.workflows.engine.worker import classify_error

        assert classify_error(OSError("disk full")) == "transient"
        assert classify_error(TimeoutError()) == "transient"
        assert classify_error(ConnectionError()) == "transient"

    def test_permanent_errors(self):
        from screenshot_processor.workflows.engine.worker import classify_error

        assert classify_error(ValueError("bad CSV")) == "permanent"
        assert classify_error(KeyError("missing column")) == "permanent"
        assert classify_error(FileNotFoundError()) == "permanent"

    def test_non_retryable_error_is_permanent(self):
        from screenshot_processor.workflows.engine.worker import classify_error

        err = NonRetryableError("permanent", cause=ValueError("bad"))
        assert classify_error(err) == "permanent"

    def test_custom_non_retryable_types(self):
        from screenshot_processor.workflows.engine.worker import classify_error

        policy = RetryPolicy(non_retryable_error_types=["RuntimeError"])
        assert classify_error(RuntimeError("nope"), policy=policy) == "permanent"


class TestRetryBackoff:
    def test_backoff_calculation(self):
        from screenshot_processor.workflows.engine.worker import compute_retry_delay

        policy = RetryPolicy(
            initial_interval=timedelta(seconds=10),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(minutes=5),
        )
        # attempt 1 → 10s, attempt 2 → 20s, attempt 3 → 40s
        assert compute_retry_delay(policy, attempt=1) == timedelta(seconds=10)
        assert compute_retry_delay(policy, attempt=2) == timedelta(seconds=20)
        assert compute_retry_delay(policy, attempt=3) == timedelta(seconds=40)

    def test_backoff_capped_by_maximum_interval(self):
        from screenshot_processor.workflows.engine.worker import compute_retry_delay

        policy = RetryPolicy(
            initial_interval=timedelta(seconds=60),
            backoff_coefficient=3.0,
            maximum_interval=timedelta(seconds=120),
        )
        # attempt 3 → 60 * 3^2 = 540s → capped to 120s
        assert compute_retry_delay(policy, attempt=3) == timedelta(seconds=120)

    def test_should_retry_within_max_attempts(self):
        from screenshot_processor.workflows.engine.worker import should_retry

        policy = RetryPolicy(maximum_attempts=3)
        assert should_retry(policy, attempt=1, error_class="transient") is True
        assert should_retry(policy, attempt=2, error_class="transient") is True
        assert should_retry(policy, attempt=3, error_class="transient") is False

    def test_should_not_retry_permanent(self):
        from screenshot_processor.workflows.engine.worker import should_retry

        policy = RetryPolicy(maximum_attempts=3)
        assert should_retry(policy, attempt=1, error_class="permanent") is False

    def test_unlimited_retries_when_zero(self):
        from screenshot_processor.workflows.engine.worker import should_retry

        policy = RetryPolicy(maximum_attempts=0)
        assert should_retry(policy, attempt=100, error_class="transient") is True
