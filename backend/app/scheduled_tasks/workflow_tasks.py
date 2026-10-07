"""Deterministic scheduled-workflow runners.

Workflow tasks deliberately bypass the Agent.  A handler owns both the fixed
workflow invocation and any deterministic hand-off required by the task, so a
successful execution always represents a business outcome.  Handlers receive
the triggering ``TaskEvent`` (if any) because event-driven workflows read their
input from ``event.payload`` instead of an agent prompt, and may declare a
``history_section`` parameter to receive task-scoped execution memory.

Handlers are registered by the modules that own them (project or feature code)
so this shared module stays free of project imports.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent.workflow.catalog import (
    FixedWorkflowDefinition,
    WorkflowPhaseDefinition,
    workflow_catalog,
)

from .models import ScheduledTask
from .models.event import TaskEvent
from .models.execution import TaskExecution

WorkflowHandler = Callable[..., Awaitable[dict[str, Any]]]

def register_workflow_handler(
    name: str,
    handler: WorkflowHandler,
    *,
    version: str = "1",
    description: str = "",
) -> None:
    """Register a deterministic handler in the shared workflow catalog."""
    workflow_catalog.register(FixedWorkflowDefinition(
        name=name,
        entrypoint="scheduled_task",
        version=version,
        description=description,
        phases=(WorkflowPhaseDefinition(
            name="execute",
            description=description or "执行确定性业务工作流并交付结果。",
            allow_completion=True,
        ),),
        handler=handler,
    ))


def registered_workflows() -> list[str]:
    """Names of all registered deterministic workflows, sorted for UI display."""
    return workflow_catalog.names("scheduled_task")


async def execute_workflow_task(
    task: ScheduledTask,
    execution: TaskExecution,
    event: TaskEvent | None = None,
    history_section: str | None = None,
) -> dict[str, Any]:
    if not task.workflow_name:
        raise RuntimeError("workflow task 未配置 workflow_name")
    definition = workflow_catalog.get("scheduled_task", task.workflow_name)
    handler = definition.handler if definition is not None else None
    if handler is None:
        raise RuntimeError(f"未注册的 workflow：{task.workflow_name}")
    parameters = inspect.signature(handler).parameters
    kwargs: dict[str, Any] = {}
    if "event" in parameters:
        kwargs["event"] = event
    if "history_section" in parameters:
        kwargs["history_section"] = history_section
    return await handler(task, execution, **kwargs)
