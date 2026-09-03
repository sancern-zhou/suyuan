import json

from app.scheduled_tasks.models import ScheduledTask
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
        event_type="yuncheng.alert.created",
        prompt=prompt,
    )


def _write_definition(root, task):
    path = root / "projects" / "demo" / "scheduled_tasks" / "task_report.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(task.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")


def test_project_task_sync_creates_then_remains_idempotent(tmp_path):
    _write_definition(tmp_path, _task())
    service = _Service(TaskStorage(tmp_path / "state"))

    created = sync_project_scheduled_tasks(
        project_id="demo", task_ids=["task_report"], service=service, project_root=tmp_path
    )
    unchanged = sync_project_scheduled_tasks(
        project_id="demo", task_ids=["task_report"], service=service, project_root=tmp_path
    )

    assert created[0]["action"] == "created"
    assert unchanged[0]["action"] == "unchanged"


def test_project_task_sync_never_overwrites_existing_tasks(tmp_path):
    """用户在界面/API 修改过的配置（含 system 任务）必须跨重启持久化。"""
    storage = TaskStorage(tmp_path / "state")
    existing = _task("旧提示")
    existing.created_by = "system"
    existing.timeout_seconds = 600
    existing.enabled = False
    existing.total_runs = 7
    storage.create(existing)

    seed = _task("新提示")
    seed.timeout_seconds = 1800
    _write_definition(tmp_path, seed)

    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_report"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_report")
    assert result[0]["action"] == "unchanged"
    assert updated.prompt == "旧提示"
    assert updated.timeout_seconds == 600
    assert updated.enabled is False
    assert updated.total_runs == 7
    assert updated.created_by == "system"


def test_project_task_sync_ignores_legacy_steps_in_runtime_store(tmp_path):
    """历史 steps 字段加载时被忽略，同步与执行都不受影响。"""
    storage = TaskStorage(tmp_path / "state")
    storage.create(_task("运行时提示"))
    state_file = tmp_path / "state" / "tasks.json"
    raw = json.loads(state_file.read_text(encoding="utf-8"))
    raw[0]["steps"] = [{
        "step_id": "step_1",
        "description": "遗留包装",
        "agent_prompt": "旧提示",
        "timeout_seconds": 600,
    }]
    state_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    _write_definition(tmp_path, _task("运行时提示"))

    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_report"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    assert result[0]["action"] == "unchanged"
    loaded = storage.get("task_report")
    assert loaded.prompt == "运行时提示"
    assert "steps" not in loaded.model_dump()
