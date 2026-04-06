"""Tests for workflow/activity registration — mirrors Temporal's decorator behavior."""

import pytest


class TestWorkflowDefn:
    def test_registers_workflow_class(self):
        from screenshot_processor.workflows.engine import workflow
        from screenshot_processor.workflows.engine.registry import get_workflow_defn

        @workflow.defn
        class MyWorkflow:
            @workflow.run
            async def run(self) -> None:
                pass

        defn = get_workflow_defn("MyWorkflow")
        assert defn.cls is MyWorkflow
        assert defn.name == "MyWorkflow"

    def test_custom_name(self):
        from screenshot_processor.workflows.engine import workflow
        from screenshot_processor.workflows.engine.registry import get_workflow_defn

        @workflow.defn(name="custom_wf")
        class AnotherWorkflow:
            @workflow.run
            async def run(self) -> None:
                pass

        defn = get_workflow_defn("custom_wf")
        assert defn.cls is AnotherWorkflow
        assert defn.name == "custom_wf"

    def test_missing_run_raises(self):
        from screenshot_processor.workflows.engine import workflow

        with pytest.raises(ValueError, match="must have exactly one @workflow.run"):

            @workflow.defn
            class NoRunWorkflow:
                pass

    def test_run_must_be_async(self):
        from screenshot_processor.workflows.engine import workflow

        with pytest.raises(TypeError, match="must be async"):

            @workflow.defn
            class SyncRunWorkflow:
                @workflow.run
                def run(self) -> None:
                    pass


class TestActivityDefn:
    def test_registers_activity_function(self):
        from screenshot_processor.workflows.engine import activity
        from screenshot_processor.workflows.engine.registry import get_activity_defn

        @activity.defn
        async def my_activity(x: int) -> int:
            return x * 2

        defn = get_activity_defn("my_activity")
        assert defn.fn is my_activity
        assert defn.name == "my_activity"

    def test_custom_name(self):
        from screenshot_processor.workflows.engine import activity
        from screenshot_processor.workflows.engine.registry import get_activity_defn

        @activity.defn(name="custom_act")
        async def another_activity() -> None:
            pass

        defn = get_activity_defn("custom_act")
        assert defn.fn is another_activity
        assert defn.name == "custom_act"

    def test_sync_activity(self):
        from screenshot_processor.workflows.engine import activity
        from screenshot_processor.workflows.engine.registry import get_activity_defn

        @activity.defn
        def sync_activity(path: str) -> dict:
            return {"path": path}

        defn = get_activity_defn("sync_activity")
        assert defn.fn is sync_activity
        assert not defn.is_async


class TestSignalAndQuery:
    def test_signal_registered(self):
        from screenshot_processor.workflows.engine import workflow
        from screenshot_processor.workflows.engine.registry import get_workflow_defn

        @workflow.defn
        class WfWithSignal:
            @workflow.run
            async def run(self) -> None:
                pass

            @workflow.signal
            async def my_signal(self, data: str) -> None:
                pass

        defn = get_workflow_defn("WfWithSignal")
        assert "my_signal" in defn.signals

    def test_query_registered(self):
        from screenshot_processor.workflows.engine import workflow
        from screenshot_processor.workflows.engine.registry import get_workflow_defn

        @workflow.defn
        class WfWithQuery:
            @workflow.run
            async def run(self) -> None:
                pass

            @workflow.query
            def get_status(self) -> str:
                return "ok"

        defn = get_workflow_defn("WfWithQuery")
        assert "get_status" in defn.queries
