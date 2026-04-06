"""Tests for workflow engine SQLAlchemy models."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from screenshot_processor.web.database.models import Base


class TestWorkflowModels:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        """Create an in-memory SQLite DB with all tables."""
        from screenshot_processor.workflows.engine.models import (
            ActivityExecution,
            WorkflowAuditEntry,
            WorkflowExecution,
            WorkflowSignal,
        )

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        yield
        self.session.close()
        self.engine.dispose()

    def test_create_workflow_execution(self):
        from screenshot_processor.workflows.engine.models import WorkflowExecution

        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="preprocessing",
            status="pending",
        )
        self.session.add(wf)
        self.session.commit()

        result = self.session.execute(select(WorkflowExecution)).scalar_one()
        assert result.screenshot_id == 1
        assert result.status == "pending"
        assert result.current_activity is None

    def test_create_activity_execution(self):
        from screenshot_processor.workflows.engine.models import (
            ActivityExecution,
            WorkflowExecution,
        )

        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="preprocessing",
            status="running",
        )
        self.session.add(wf)
        self.session.flush()

        act = ActivityExecution(
            workflow_id=wf.id,
            activity_name="device_detection",
            status="pending",
            attempt=1,
            is_blocking=True,
        )
        self.session.add(act)
        self.session.commit()

        result = self.session.execute(select(ActivityExecution)).scalar_one()
        assert result.activity_name == "device_detection"
        assert result.is_blocking is True
        assert result.progress_pct == 0.0
        assert result.error_message is None
        assert result.result_json is None

    def test_create_workflow_signal(self):
        from screenshot_processor.workflows.engine.models import (
            WorkflowExecution,
            WorkflowSignal,
        )

        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="preprocessing",
            status="running",
        )
        self.session.add(wf)
        self.session.flush()

        sig = WorkflowSignal(
            workflow_id=wf.id,
            signal_name="cancel",
            payload_json={"reason": "user requested"},
            consumed=False,
        )
        self.session.add(sig)
        self.session.commit()

        result = self.session.execute(select(WorkflowSignal)).scalar_one()
        assert result.signal_name == "cancel"
        assert result.payload_json == {"reason": "user requested"}
        assert result.consumed is False

    def test_workflow_activities_relationship(self):
        from screenshot_processor.workflows.engine.models import (
            ActivityExecution,
            WorkflowExecution,
        )

        wf = WorkflowExecution(
            screenshot_id=1,
            workflow_type="preprocessing",
            status="running",
        )
        self.session.add(wf)
        self.session.flush()

        for name in ["device_detection", "cropping", "phi_detection"]:
            self.session.add(
                ActivityExecution(
                    workflow_id=wf.id,
                    activity_name=name,
                    status="pending",
                    attempt=1,
                    is_blocking=(name == "device_detection"),
                )
            )
        self.session.commit()

        self.session.refresh(wf)
        assert len(wf.activities) == 3
        blocking = [a for a in wf.activities if a.is_blocking]
        assert len(blocking) == 1
        assert blocking[0].activity_name == "device_detection"

    def test_create_audit_entry(self):
        from screenshot_processor.workflows.engine.models import WorkflowAuditEntry, WorkflowExecution

        wf = WorkflowExecution(
            screenshot_id=1, workflow_type="preprocessing", status="running",
        )
        self.session.add(wf)
        self.session.flush()

        entry = WorkflowAuditEntry(
            workflow_id=wf.id, activity_name="device_detection",
            event="started", attempt=1,
        )
        self.session.add(entry)
        self.session.commit()

        result = self.session.execute(select(WorkflowAuditEntry)).scalar_one()
        assert result.event == "started"
        assert result.activity_name == "device_detection"
        assert result.timestamp is not None

    def test_activity_result_json(self):
        from screenshot_processor.workflows.engine.models import (
            ActivityExecution,
            WorkflowExecution,
        )

        wf = WorkflowExecution(
            screenshot_id=1, workflow_type="preprocessing", status="running",
        )
        self.session.add(wf)
        self.session.flush()

        act = ActivityExecution(
            workflow_id=wf.id,
            activity_name="device_detection",
            status="completed",
            attempt=1,
            result_json={"device_category": "iphone", "confidence": 0.98},
        )
        self.session.add(act)
        self.session.commit()

        result = self.session.execute(select(ActivityExecution)).scalar_one()
        assert result.result_json["device_category"] == "iphone"
        assert result.result_json["confidence"] == 0.98
