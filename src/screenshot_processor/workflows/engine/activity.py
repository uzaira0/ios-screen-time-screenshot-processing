"""Activity decorators and context functions — interface-identical to temporalio.activity.

Usage:
    from screenshot_processor.workflows.engine import activity

    @activity.defn
    async def my_activity(screenshot_id: int) -> None:
        activity.heartbeat(progress=50.0)
        info = activity.info()
        print(f"Attempt {info.attempt}")

When migrating to Temporal, change the import to:
    from temporalio import activity
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable

from screenshot_processor.workflows.engine.registry import register_activity
from screenshot_processor.workflows.engine.types import ActivityInfo

# Context variable holding the current activity's info during execution.
# Set by the WorkflowWorker before calling the activity function.
_current_info: contextvars.ContextVar[ActivityInfo | None] = contextvars.ContextVar(
    "_current_activity_info", default=None
)

# Context variable holding the heartbeat callback during execution.
# Set by the WorkflowWorker to a function that updates ActivityExecution.progress_pct.
_heartbeat_fn: contextvars.ContextVar[Callable[..., None] | None] = contextvars.ContextVar(
    "_heartbeat_fn", default=None
)


def defn(
    fn: Callable | None = None,
    *,
    name: str | None = None,
) -> Any:
    """Function decorator matching temporalio.activity.defn."""
    def decorator(fn: Callable) -> Callable:
        return register_activity(fn, name=name)

    if fn is not None:
        return decorator(fn)
    return decorator


def heartbeat(*details: Any) -> None:
    """Send a heartbeat for the current activity. Matches temporalio.activity.heartbeat.

    In our engine, the first positional arg is treated as progress_pct (float 0-100)
    if it's a number. The WorkflowWorker updates ActivityExecution.progress_pct.
    """
    fn = _heartbeat_fn.get()
    if fn is not None:
        fn(*details)


def info() -> ActivityInfo:
    """Return metadata about the currently executing activity. Matches temporalio.activity.info."""
    current = _current_info.get()
    if current is None:
        raise RuntimeError(
            "activity.info() called outside of activity execution context."
        )
    return current
