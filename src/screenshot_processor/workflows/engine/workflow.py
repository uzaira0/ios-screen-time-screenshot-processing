"""Workflow decorators — interface-identical to temporalio.workflow.

Usage:
    from screenshot_processor.workflows.engine import workflow

    @workflow.defn
    class MyWorkflow:
        @workflow.run
        async def run(self, arg: str) -> None:
            await workflow.execute_activity(my_activity, args=[arg])

When migrating to Temporal, change the import to:
    from temporalio import workflow
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Sequence

from screenshot_processor.workflows.engine.registry import (
    _WORKFLOW_QUERY_MARKER,
    _WORKFLOW_RUN_MARKER,
    _WORKFLOW_SIGNAL_MARKER,
    register_workflow,
)
from screenshot_processor.workflows.engine.types import RetryPolicy


def defn(
    cls: type | None = None,
    *,
    name: str | None = None,
    sandboxed: bool = True,
) -> Any:
    """Class decorator matching temporalio.workflow.defn."""
    def decorator(cls: type) -> type:
        return register_workflow(cls, name=name)

    if cls is not None:
        return decorator(cls)
    return decorator


def run(fn: Callable) -> Callable:
    """Method decorator matching temporalio.workflow.run."""
    setattr(fn, _WORKFLOW_RUN_MARKER, True)
    return fn


def signal(
    fn: Callable | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Method decorator matching temporalio.workflow.signal."""
    def decorator(fn: Callable) -> Callable:
        sig_name = name or fn.__name__
        setattr(fn, _WORKFLOW_SIGNAL_MARKER, sig_name)
        return fn

    if fn is not None:
        return decorator(fn)
    return decorator


def query(
    fn: Callable | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Method decorator matching temporalio.workflow.query."""
    def decorator(fn: Callable) -> Callable:
        q_name = name or fn.__name__
        setattr(fn, _WORKFLOW_QUERY_MARKER, q_name)
        return fn

    if fn is not None:
        return decorator(fn)
    return decorator


async def execute_activity(
    activity: Callable | str,
    *,
    arg: Any = None,
    args: Sequence[Any] | None = None,
    start_to_close_timeout: timedelta | None = None,
    schedule_to_close_timeout: timedelta | None = None,
    heartbeat_timeout: timedelta | None = None,
    retry_policy: RetryPolicy | None = None,
    activity_id: str | None = None,
) -> Any:
    """Execute an activity within a workflow — interface matches temporalio.workflow.execute_activity.

    In our Postgres-backed engine, this is called by the WorkflowWorker
    which intercepts the call, persists an ActivityExecution row,
    runs the activity function, and updates the row on completion/failure.

    This function is a placeholder that gets monkey-patched by the worker
    at execution time with the actual implementation that manages persistence.
    """
    raise RuntimeError(
        "workflow.execute_activity() called outside of workflow execution context. "
        "This function is only callable within a @workflow.run method "
        "being executed by the WorkflowWorker."
    )
