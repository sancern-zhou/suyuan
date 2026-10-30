"""手动“立即执行”与定时触发在执行记录上的区分标注。"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.scheduled_tasks.executor.task_executor import ScheduledTaskExecutor
from app.scheduled_tasks.models import ScheduledTask
from app.scheduled_tasks.models.task import ScheduleType
from app.scheduled_tasks.storage.execution_storage import ExecutionStorage
from app.scheduled_tasks.storage.task_storage import TaskStorage


def _make_executor(tmp_path):
    def agent_factory():
        class MockAgent:
            async def analyze(self, prompt, **kwargs):
                yield {"type": "final_response", "content": "完成"}

        return MockAgent()

    task_storage = TaskStorage(storage_dir=str(tmp_path / "tasks"))
    execution_storage = ExecutionStorage(storage_dir=str(tmp_path / "executions"))
    return ScheduledTaskExecutor(
        task_storage=task_storage,
        execution_storage=execution_storage,
        agent_factory=agent_factory,
    )


def _make_task(task_id: str) -> ScheduledTask:
    task = ScheduledTask(
        task_id=task_id,
        name="触发标注测试",
        description="验证手动/定时触发标注",
        schedule_type=ScheduleType.WEEKLY_CUSTOM,
        day_of_week=0,
        hour=10,
        minute=0,
        enabled=True,
        prompt="执行",
        timeout_seconds=10,
        history_learning={"enabled": False},
    )
    task.next_run_at = datetime(2026, 11, 2, 10, 0, 0)
    return task


def test_cron_execution_keeps_scheduled_label_with_next_slot(tmp_path):
    executor = _make_executor(tmp_path)
    task = _make_task("label_cron")
    executor.task_storage.create(task)

    execution = asyncio.run(executor.execute_task(task))

    assert execution.trigger_type == "scheduled"
    assert execution.scheduled_time == task.next_run_at


def test_manual_execution_is_labeled_manual_without_scheduled_time(tmp_path):
    executor = _make_executor(tmp_path)
    task = _make_task("label_manual")
    executor.task_storage.create(task)

    execution = asyncio.run(executor.execute_task(task, trigger_type="manual"))

    assert execution.trigger_type == "manual"
    assert execution.scheduled_time is None
