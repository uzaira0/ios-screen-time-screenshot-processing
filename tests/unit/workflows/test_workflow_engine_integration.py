"""Integration test — execute_activity persists state to DB."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from screenshot_processor.web.database.models import Base
from screenshot_processor.workflows.engine import activity, workflow
from screenshot_processor.workflows.engine.models import (
    ActivityExecution,
    WorkflowExecution,
)
from screenshot_processor.workflows.engine.types import RetryPolicy
from screenshot_processor.workflows.engine.worker import (
    execute_activity_with_persistence,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


# Register test activities
@activity.defn
async def add_numbers(a: int, b: int) -> int:
    return a + b


@activity.defn
async def failing_activity() -> None:
    raise ValueError("bad data")


class TestExecuteActivityWithPersistence:
    def test_successful_activity_updates_db(self, db_session):
        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="test",
            status="running",
        )
        db_session.add(wf)
        db_session.flush()

        act = ActivityExecution(
            workflow_id=wf.id,
            activity_name="add_numbers",
            status="pending",
            attempt=1,
            is_blocking=False,
        )
        db_session.add(act)
        db_session.commit()

        import asyncio

        result = asyncio.run(
            execute_activity_with_persistence(
                db_session, act, args=[3, 4], retry_policy=RetryPolicy()
            )
        )

        db_session.refresh(act)
        assert act.status == "completed"
        assert act.completed_at is not None
        assert act.error_message is None

    def test_permanent_failure_marks_failed(self, db_session):
        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="test",
            status="running",
        )
        db_session.add(wf)
        db_session.flush()

        act = ActivityExecution(
            workflow_id=wf.id,
            activity_name="failing_activity",
            status="pending",
            attempt=1,
            is_blocking=False,
        )
        db_session.add(act)
        db_session.commit()

        import asyncio

        with pytest.raises(ValueError):
            asyncio.run(
                execute_activity_with_persistence(
                    db_session, act, args=[], retry_policy=RetryPolicy(maximum_attempts=1)
                )
            )

        db_session.refresh(act)
        assert act.status == "failed"
        assert act.error_class == "permanent"
        assert "bad data" in act.error_message
