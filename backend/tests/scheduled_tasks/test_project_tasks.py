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
        event_type="xuchang.station_deviation.alert_created",
        prompt=prompt,
    )


def _write_definition(root, task):
    path = root / "projects" / "demo" / "scheduled_tasks" / "task_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
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


def test_project_task_sync_uses_declared_runtime_fields_only(tmp_path):
    """运行时存储中的额外字段不会进入任务模型。"""
    storage = TaskStorage(tmp_path / "state")
    storage.create(_task("运行时提示"))
    state_file = tmp_path / "state" / "tasks.json"
    raw = json.loads(state_file.read_text(encoding="utf-8"))
    raw[0]["unused_field"] = {"prompt": "旧提示", "timeout_seconds": 600}
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
    assert "unused_field" not in loaded.model_dump()


def _workflow_task(prompt="生成值守结论"):
    return ScheduledTask(
        task_id="task_watch",
        name="值守",
        description="值守",
        execution_mode="workflow",
        workflow_name="demo_workflow",
        workflow_args={"period": "day"},
        schedule_type="daily_8am",
        prompt=prompt,
    )


def _write_watch_definition(root, task):
    path = root / "projects" / "demo" / "scheduled_tasks" / "task_watch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")


def test_workflow_task_migrates_agent_task_to_workflow_contract(tmp_path):
    """Agent 模式种子升级为 workflow 时只迁移执行契约，保留运行时字段。"""
    storage = TaskStorage(tmp_path / "state")
    existing = _workflow_task("旧指令")
    existing.execution_mode = "ops"
    existing.workflow_name = None
    existing.workflow_args = {}
    existing.skill_id = "review-skill"
    existing.enabled = False
    existing.total_runs = 9
    storage.create(existing)

    _write_watch_definition(tmp_path, _workflow_task("新指令"))
    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_watch"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_watch")
    assert result[0]["action"] == "migrated_workflow"
    assert updated.execution_mode == "workflow"
    assert updated.workflow_name == "demo_workflow"
    assert updated.prompt == "新指令"
    assert updated.skill_id is None
    assert updated.enabled is False
    assert updated.total_runs == 9


def test_workflow_instruction_change_syncs_to_persisted_task(tmp_path):
    """workflow 指令由代码侧拥有，种子变更需同步到已存在任务。"""
    storage = TaskStorage(tmp_path / "state")
    storage.create(_workflow_task("旧指令"))

    _write_watch_definition(tmp_path, _workflow_task("新指令"))
    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_watch"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_watch")
    assert result[0]["action"] == "updated_workflow_instruction"
    assert updated.prompt == "新指令"


def test_mixed_seed_sync_handles_agent_and_workflow_tasks(tmp_path):
    """同一项目内 Agent 种子仅补缺，workflow 种子负责指令同步。"""
    storage = TaskStorage(tmp_path / "state")
    storage.create(_workflow_task("旧指令"))

    _write_watch_definition(tmp_path, _workflow_task("新指令"))
    _write_definition(tmp_path, _task("新提示"))
    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_report", "task_watch"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    actions = {row["task_id"]: row["action"] for row in result}
    assert actions["task_watch"] == "updated_workflow_instruction"
    assert actions["task_report"] == "created"
