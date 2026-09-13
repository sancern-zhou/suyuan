"""Deterministic workflow execution-mode tests (registry + executor branch)."""

import asyncio

import pytest
from pydantic import ValidationError

from app.scheduled_tasks.executor import ScheduledTaskExecutor
from app.scheduled_tasks.models import ScheduledTask, TaskEvent, TaskExecution
from app.scheduled_tasks.models.execution import ExecutionStatus
from app.scheduled_tasks.storage import ExecutionStorage, TaskStorage
from app.scheduled_tasks.workflow_tasks import (
    execute_workflow_task,
    register_workflow_handler,
)


def _workflow_task(**overrides) -> ScheduledTask:
    payload = {
        "task_id": "task-workflow",
        "name": "工作流任务",
        "description": "确定性工作流任务",
        "execution_mode": "workflow",
        "workflow_name": "unit_test_workflow",
        "trigger_type": "event",
        "event_type": "unit.event",
        "prompt": "执行工作流",
        "history_learning": {"enabled": False},
    }
    payload.update(overrides)
    return ScheduledTask(**payload)


def test_workflow_mode_requires_workflow_name():
    with pytest.raises(ValidationError, match="workflow_name is required"):
        _workflow_task(workflow_name=None)
    with pytest.raises(ValidationError, match="workflow_name/workflow_args are only valid"):
        _workflow_task(execution_mode="expert")
    with pytest.raises(ValidationError, match="tool_names is only valid"):
        _workflow_task(tool_names=["read_file"])


def test_execute_workflow_task_dispatches_by_name():
    seen = {}

    async def handler(task, execution, event):
        seen["names"] = (task.workflow_name, event.event_id if event else None)
        return {"summary": "done"}

    register_workflow_handler("unit_test_dispatch", handler)

    task = _workflow_task(workflow_name="unit_test_dispatch")
    execution = TaskExecution(execution_id="exec-1", task_id=task.task_id, task_name=task.name, status="running", total_steps=1)
    event = TaskEvent(event_id="evt-1", event_type="unit.event")
    result = asyncio.run(execute_workflow_task(task, execution, event=event))
    assert result["summary"] == "done"
    assert seen["names"] == ("unit_test_dispatch", "evt-1")

    unknown = _workflow_task(workflow_name="missing_workflow")
    with pytest.raises(RuntimeError, match="未注册的 workflow"):
        asyncio.run(execute_workflow_task(unknown, execution, event=None))


class _UnusedAgent:
    async def analyze(self, prompt, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("workflow tasks must not start an agent")
        yield


class _RecordingPersistence:
    def __init__(self):
        self.calls = []

    async def persist_agent_session(self, **kwargs):
        self.calls.append(kwargs)
        return True

    async def publish_conversation(self, **kwargs):
        self.calls.append({"published": kwargs})

    async def ensure_terminal_session(self, **kwargs):
        self.calls.append({"ensured": kwargs})


@pytest.mark.asyncio
async def test_executor_runs_workflow_without_agent_or_conversation(tmp_path):
    async def handler(task, execution, event):
        assert event is not None and event.payload["marker"] == "value"
        return {"summary": "工作流完成", "data_ids": ["review-1"], "tool_call_details": {"media_count": 2}}

    register_workflow_handler("unit_test_executor", handler)
    persistence = _RecordingPersistence()
    task = _workflow_task(workflow_name="unit_test_executor")
    task_storage = TaskStorage(storage_dir=tmp_path)
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=_UnusedAgent,
        conversation_persistence=persistence,
    )
    event = TaskEvent(event_id="evt-2", event_type="unit.event", payload={"marker": "value"})

    execution = await executor.execute_task(task, event=event)

    assert execution.status == ExecutionStatus.SUCCESS
    step = execution.steps[0]
    assert step.step_id == "workflow"
    assert step.agent_prompt == "workflow:unit_test_executor"
    assert step.agent_response == "工作流完成"
    assert step.result_data_ids == ["review-1"]
    assert step.tool_calls[0]["tool"] == "unit_test_executor"
    assert step.tool_calls[0]["media_count"] == 2
    assert persistence.calls == []


@pytest.mark.asyncio
async def test_executor_marks_workflow_failure(tmp_path):
    async def failing(task, execution, event):
        raise RuntimeError("证据包缺失")

    register_workflow_handler("unit_test_failure", failing)
    task = _workflow_task(workflow_name="unit_test_failure")
    task_storage = TaskStorage(storage_dir=tmp_path)
    task_storage.create(task)
    executor = ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=ExecutionStorage(storage_dir=tmp_path),
        agent_factory=_UnusedAgent,
        conversation_persistence=_RecordingPersistence(),
    )

    execution = await executor.execute_task(task)

    assert execution.status == ExecutionStatus.FAILED
    assert "证据包缺失" in (execution.error_message or "")
