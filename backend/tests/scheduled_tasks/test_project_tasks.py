import json

from app.scheduled_tasks.models import ScheduledTask, TaskStep
from app.scheduled_tasks.project_tasks import sync_project_scheduled_tasks
from app.scheduled_tasks.storage.task_storage import TaskStorage


class _Service:
    def __init__(self, storage):
        self.task_storage = storage

    def create_task(self, task):
        return self.task_storage.create(task)

    def update_task(self, task):
        return self.task_storage.update(task)


def _task(prompt="生成报告"):
    return ScheduledTask(
        task_id="task_report",
        name="报告",
        description="报告",
        execution_mode="report",
        trigger_type="event",
        event_type="xuchang.station_daily_source_analysis.completed",
        steps=[TaskStep(step_id="report", description="报告", agent_prompt=prompt)],
    )


def _write_definition(root, task):
    path = root / "projects" / "xuchang" / "scheduled_tasks" / "task_report.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(task.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")


def test_project_task_sync_creates_then_remains_idempotent(tmp_path):
    _write_definition(tmp_path, _task())
    service = _Service(TaskStorage(tmp_path / "state"))

    created = sync_project_scheduled_tasks(
        project_id="xuchang", task_ids=["task_report"], service=service, project_root=tmp_path
    )
    unchanged = sync_project_scheduled_tasks(
        project_id="xuchang", task_ids=["task_report"], service=service, project_root=tmp_path
    )

    assert created[0]["action"] == "created"
    assert unchanged[0]["action"] == "unchanged"


def test_project_task_sync_updates_prompt_and_preserves_runtime_state(tmp_path):
    storage = TaskStorage(tmp_path / "state")
    existing = _task("旧提示")
    existing.enabled = False
    existing.total_runs = 7
    storage.create(existing)
    _write_definition(tmp_path, _task("新提示"))

    result = sync_project_scheduled_tasks(
        project_id="xuchang",
        task_ids=["task_report"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_report")
    assert result[0]["action"] == "updated"
    assert updated.steps[0].agent_prompt == "新提示"
    assert updated.enabled is False
    assert updated.total_runs == 7
