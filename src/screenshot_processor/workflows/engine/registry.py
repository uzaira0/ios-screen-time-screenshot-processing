"""Workflow and activity registration — mirrors Temporal's decorator-based discovery."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class WorkflowDefinition:
    """Metadata collected from @workflow.defn decorated class."""

    cls: type
    name: str
    run_method: str  # name of the @workflow.run method
    signals: dict[str, str] = field(default_factory=dict)  # signal_name → method_name
    queries: dict[str, str] = field(default_factory=dict)  # query_name → method_name


@dataclass
class ActivityDefinition:
    """Metadata collected from @activity.defn decorated function."""

    fn: Callable
    name: str
    is_async: bool


_WORKFLOW_REGISTRY: dict[str, WorkflowDefinition] = {}
_ACTIVITY_REGISTRY: dict[str, ActivityDefinition] = {}

# Sentinel markers set on methods before class-level @workflow.defn collects them
_WORKFLOW_RUN_MARKER = "__temporal_workflow_run__"
_WORKFLOW_SIGNAL_MARKER = "__temporal_workflow_signal__"
_WORKFLOW_QUERY_MARKER = "__temporal_workflow_query__"


def register_workflow(cls: type, *, name: str | None = None) -> type:
    """Register a workflow class. Called by @workflow.defn."""
    wf_name = name or cls.__name__

    # Find the @workflow.run method
    run_methods = []
    signals: dict[str, str] = {}
    queries: dict[str, str] = {}

    for attr_name in dir(cls):
        attr = getattr(cls, attr_name, None)
        if attr is None:
            continue
        if getattr(attr, _WORKFLOW_RUN_MARKER, False):
            if not inspect.iscoroutinefunction(attr):
                msg = f"@workflow.run method {cls.__name__}.{attr_name} must be async"
                raise TypeError(msg)
            run_methods.append(attr_name)
        if hasattr(attr, _WORKFLOW_SIGNAL_MARKER):
            sig_name = getattr(attr, _WORKFLOW_SIGNAL_MARKER)
            signals[sig_name] = attr_name
        if hasattr(attr, _WORKFLOW_QUERY_MARKER):
            q_name = getattr(attr, _WORKFLOW_QUERY_MARKER)
            queries[q_name] = attr_name

    if len(run_methods) != 1:
        msg = f"@workflow.defn class {cls.__name__} must have exactly one @workflow.run method, found {len(run_methods)}"
        raise ValueError(msg)

    defn = WorkflowDefinition(
        cls=cls,
        name=wf_name,
        run_method=run_methods[0],
        signals=signals,
        queries=queries,
    )
    _WORKFLOW_REGISTRY[wf_name] = defn

    # Store metadata on class (matches Temporal's __temporal_workflow_definition)
    cls.__temporal_workflow_definition = defn  # type: ignore[attr-defined]

    return cls


def register_activity(fn: Callable, *, name: str | None = None) -> Callable:
    """Register an activity function. Called by @activity.defn."""
    act_name = name or fn.__name__
    defn = ActivityDefinition(
        fn=fn,
        name=act_name,
        is_async=inspect.iscoroutinefunction(fn),
    )
    _ACTIVITY_REGISTRY[act_name] = defn

    # Store metadata on function (matches Temporal's __temporal_activity_definition)
    fn.__temporal_activity_definition = defn  # type: ignore[attr-defined]

    return fn


def get_workflow_defn(name: str) -> WorkflowDefinition:
    """Look up a registered workflow by name."""
    if name not in _WORKFLOW_REGISTRY:
        available = sorted(_WORKFLOW_REGISTRY.keys())
        msg = f"Unknown workflow {name!r}. Available: {available}"
        raise KeyError(msg)
    return _WORKFLOW_REGISTRY[name]


def get_activity_defn(name: str) -> ActivityDefinition:
    """Look up a registered activity by name."""
    if name not in _ACTIVITY_REGISTRY:
        available = sorted(_ACTIVITY_REGISTRY.keys())
        msg = f"Unknown activity {name!r}. Available: {available}"
        raise KeyError(msg)
    return _ACTIVITY_REGISTRY[name]


def list_workflows() -> list[str]:
    """Return all registered workflow names."""
    return sorted(_WORKFLOW_REGISTRY.keys())


def list_activities() -> list[str]:
    """Return all registered activity names."""
    return sorted(_ACTIVITY_REGISTRY.keys())
