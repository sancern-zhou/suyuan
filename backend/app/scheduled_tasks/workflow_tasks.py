"""Deterministic scheduled-workflow runners.

Workflow tasks deliberately bypass the Agent.  A handler owns both the fixed
workflow invocation and any deterministic delivery required by the task, so a
successful execution always represents a business outcome.  Handlers receive
the triggering ``TaskEvent`` (if any) because event-driven workflows read their
input from ``event.payload`` instead of an agent prompt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
from typing import Any

from .models import ScheduledTask
from .models.event import TaskEvent
from .models.execution import TaskExecution

WorkflowHandler = Callable[
    [ScheduledTask, TaskExecution, TaskEvent | None, str | None],
    Awaitable[dict[str, Any]],
]

_WORKFLOW_HANDLERS: dict[str, WorkflowHandler] = {}


def register_workflow_handler(name: str, handler: WorkflowHandler) -> None:
    """Register a deterministic handler for one workflow name."""
    _WORKFLOW_HANDLERS[name] = handler


def registered_workflows() -> list[str]:
    """Names of all registered deterministic workflows, sorted for UI display."""
    return sorted(_WORKFLOW_HANDLERS)


async def _run_xuchang_station_alert(
    task: ScheduledTask,
    execution: TaskExecution,
    event: TaskEvent | None,
    history_section: str | None = None,
) -> dict[str, Any]:
    from app.scenarios.xuchang_station_deviation.alert_notification import (
        run_station_alert_workflow,
    )

    return await run_station_alert_workflow(
        task=task, execution=execution, event=event, history_section=history_section
    )


register_workflow_handler("xuchang_station_deviation_alert", _run_xuchang_station_alert)


async def execute_workflow_task(
    task: ScheduledTask,
    execution: TaskExecution,
    event: TaskEvent | None = None,
    history_section: str | None = None,
) -> dict[str, Any]:
    if not task.workflow_name:
        raise RuntimeError("workflow task 未配置 workflow_name")
    handler = _WORKFLOW_HANDLERS.get(task.workflow_name)
    if handler is None:
        raise RuntimeError(f"未注册的 workflow：{task.workflow_name}")
    parameters = inspect.signature(handler).parameters
    if "history_section" in parameters:
        return await handler(task, execution, event, history_section)
    return await handler(task, execution, event)
