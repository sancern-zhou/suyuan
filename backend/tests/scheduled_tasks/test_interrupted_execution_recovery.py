import asyncio
import json

import pytest

from app.scheduled_tasks.models import (
    ScheduledTask,
    TaskEvent,
    TaskExecution,
)
from app.scheduled_tasks.service import ScheduledTaskService
from app.scheduled_tasks.storage import (
    EventClaimStorage,
    ExecutionStorage,
    TaskStorage,
)


def test_service_startup_fails_execution_interrupted_by_worker_restart(tmp_path):
    tasks = TaskStorage(tmp_path)
    executions = ExecutionStorage(tmp_path)
    claims = EventClaimStorage(tmp_path)
    task = ScheduledTask(
        task_id="event-task",
        name="事件任务",
        description="事件任务",
        execution_mode="assistant",
        trigger_type="event",
        event_type="jiangsu.station_fault.detected",
        prompt="执行",
    )
    tasks.create(task)
    event = TaskEvent(
        event_id="event-1",
        event_type=task.event_type,
        attributes={},
        payload={},
    )
    claim = claims.try_claim(task.task_id, event)
    claims.mark_status(claim.claim_id, "running", execution_id="execution-1")
    executions.create(TaskExecution(
        execution_id="execution-1",
        task_id=task.task_id,
        task_name=task.name,
        status="running",
        total_steps=1,
        trigger_type="event",
        event_id=event.event_id,
        event_type=event.event_type,
    ))

    ScheduledTaskService(
        task_storage=tasks,
        execution_storage=executions,
        claim_storage=claims,
    )

    recovered = executions.get("execution-1")
    assert recovered.status.value == "failed"
    assert recovered.completed_at is not None
    assert recovered.error_message == "后台 Worker 重启，上一轮执行已中断"
    assert claims.get(task.task_id, event.event_id).status == "failed"


class _SuccessfulAgent:
    async def analyze(self, prompt, **kwargs):
        yield {
            "type": "final_response",
            "content": json.dumps({"success": True}),
        }


@pytest.mark.asyncio
async def test_service_resumes_claimed_event_that_was_queued_before_restart(
    tmp_path,
):
    tasks = TaskStorage(tmp_path)
    executions = ExecutionStorage(tmp_path)
    claims = EventClaimStorage(tmp_path)
    task = ScheduledTask(
        task_id="queued-event-task",
        name="queued event task",
        description="queued event task",
        execution_mode="assistant",
        trigger_type="event",
        event_type="jiangsu.station_fault.detected",
        prompt="执行",
    )
    tasks.create(task)
    event = TaskEvent(
        event_id="queued-event-1",
        event_type=task.event_type,
        attributes={},
        payload={},
    )
    claim = claims.try_claim(task.task_id, event)

    service = ScheduledTaskService(
        agent_factory=_SuccessfulAgent,
        task_storage=tasks,
        execution_storage=executions,
        claim_storage=claims,
    )
    service._resume_claimed_event_tasks()
    await asyncio.gather(*list(service._event_tasks))

    recovered_claim = claims.get(task.task_id, event.event_id)
    assert recovered_claim.claim_id == claim.claim_id
    assert recovered_claim.status == "succeeded"
