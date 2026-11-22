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


def test_project_task_sync_migrates_legacy_agent_task_to_seeded_workflow(tmp_path):
    storage = TaskStorage(tmp_path / "state")
    existing = ScheduledTask(
        task_id="task_report",
        name="报告",
        description="报告",
        execution_mode="custom",
        tool_names=["legacy_tool"],
        trigger_type="event",
        event_type="xuchang.station_deviation.alert_created",
        target_user_ids=["app:android:android_demo"],
        broadcast_enabled=True,
        prompt="旧 Agent 指令",
    )
    existing.enabled = False
    existing.total_runs = 7
    storage.create(existing)

    seed = ScheduledTask(
        task_id="task_report",
        name="报告",
        description="报告",
        execution_mode="workflow",
        workflow_name="xuchang_station_deviation_alert",
        trigger_type="event",
        event_type="xuchang.station_deviation.alert_created",
        prompt="确定性工作流指令",
    )
    _write_definition(tmp_path, seed)

    result = sync_project_scheduled_tasks(
        project_id="demo", task_ids=["task_report"], service=_Service(storage), project_root=tmp_path
    )

    migrated = storage.get("task_report")
    assert result[0]["action"] == "migrated_workflow"
    assert migrated.execution_mode == "workflow"
    assert migrated.workflow_name == "xuchang_station_deviation_alert"
    assert migrated.tool_names is None
    assert migrated.skill_id is None
    assert migrated.prompt == "确定性工作流指令"
    assert migrated.enabled is False
    assert migrated.total_runs == 7
    assert migrated.target_user_ids == ["app:android:android_demo"]


def test_project_task_sync_migrates_workflow_task_to_seeded_agent_mode(tmp_path):
    """种子从工作流改为 Agent 模式时反向迁移：执行契约与投递目标随种子走，
    运行时运营状态（enabled/统计）保留。"""
    storage = TaskStorage(tmp_path / "state")
    existing = ScheduledTask(
        task_id="task_report",
        name="报告",
        description="报告",
        execution_mode="workflow",
        workflow_name="xuchang_pollution_cause_analysis",
        workflow_args={},
        trigger_type="event",
        event_type="xuchang.pollution_cause_analysis.triggered",
        target_user_ids=["app:android:android_demo"],
        broadcast_enabled=True,
        prompt="旧工作流指令",
        timeout_seconds=600,
    )
    existing.enabled = False
    existing.total_runs = 7
    storage.create(existing)

    seed = ScheduledTask(
        task_id="task_report",
        name="报告",
        description="报告",
        execution_mode="report",
        trigger_type="event",
        event_type="xuchang.pollution_cause_analysis.triggered",
        target_user_ids=["app:android:大气科1", "app:android:大气科2"],
        broadcast_enabled=True,
        prompt="报告模式 Agent 指令",
        timeout_seconds=900,
    )
    _write_definition(tmp_path, seed)

    result = sync_project_scheduled_tasks(
        project_id="demo", task_ids=["task_report"], service=_Service(storage), project_root=tmp_path
    )

    migrated = storage.get("task_report")
    assert result[0]["action"] == "migrated_agent_mode"
    assert migrated.execution_mode == "report"
    assert migrated.workflow_name is None
    assert migrated.workflow_args == {}
    assert migrated.tool_names is None
    assert migrated.prompt == "报告模式 Agent 指令"
    assert migrated.timeout_seconds == 900
    assert migrated.target_user_ids == ["app:android:大气科1", "app:android:大气科2"]
    assert migrated.broadcast_enabled is True
    assert migrated.enabled is False
    assert migrated.total_runs == 7


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


def _monitor_task(prompt="旧监控指令", tool_names=None):
    return ScheduledTask(
        task_id="task_runtime_monitor",
        name="后台运行监控",
        description="监控",
        execution_mode="custom",
        tool_names=tool_names or ["query_runtime_anomalies"],
        schedule_type="cron",
        cron="5 * * * *",
        target_user_ids=["app:android:android_demo"],
        broadcast_enabled=True,
        prompt=prompt,
        timeout_seconds=300,
        tags=["runtime-monitor", "watchdog"],
        history_learning={"enabled": False},
    )


def _write_monitor_definition(root, task):
    path = root / "projects" / "demo" / "scheduled_tasks" / "task_runtime_monitor.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")


def test_monitor_seed_propagates_code_owned_fields(tmp_path):
    """监控任务（runtime-monitor tag）是代码拥有的基础设施：种子变更需同步。"""
    storage = TaskStorage(tmp_path / "state")
    existing = _monitor_task()
    existing.enabled = False  # 运维在界面关掉过
    existing.total_runs = 9
    storage.create(existing)

    seed = _monitor_task(
        prompt="新监控指令",
        tool_names=["query_runtime_anomalies", "retry_scheduled_task", "trigger_fetcher"],
    )
    _write_monitor_definition(tmp_path, seed)
    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_runtime_monitor"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_runtime_monitor")
    assert result[0]["action"] == "updated_monitor_definition"
    # 代码拥有字段随种子更新
    assert updated.prompt == "新监控指令"
    assert updated.tool_names == ["query_runtime_anomalies", "retry_scheduled_task", "trigger_fetcher"]
    # 运行时字段不动：禁用状态、推送目标、统计都保留
    assert updated.enabled is False
    assert updated.target_user_ids == ["app:android:android_demo"]
    assert updated.total_runs == 9


def test_monitor_seed_unchanged_when_definition_matches(tmp_path):
    storage = TaskStorage(tmp_path / "state")
    storage.create(_monitor_task())
    _write_monitor_definition(tmp_path, _monitor_task())
    result = sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_runtime_monitor"],
        service=_Service(storage),
        project_root=tmp_path,
    )
    assert result[0]["action"] == "unchanged"


def test_monitor_seed_flips_broadcast_switch_with_channel_migration(tmp_path):
    """通报通道迁移（直推→助手会话）：broadcast_enabled 随种子关闭，推送目标保留。"""
    storage = TaskStorage(tmp_path / "state")
    existing = _monitor_task()  # 旧部署：直推开着
    existing.broadcast_enabled = True
    storage.create(existing)

    seed = _monitor_task(tool_names=["query_runtime_anomalies", "submit_monitor_report"])
    seed.broadcast_enabled = False
    seed.target_user_ids = []
    _write_monitor_definition(tmp_path, seed)
    sync_project_scheduled_tasks(
        project_id="demo",
        task_ids=["task_runtime_monitor"],
        service=_Service(storage),
        project_root=tmp_path,
    )

    updated = storage.get("task_runtime_monitor")
    # 通道开关是代码拥有的：旧直推被种子关闭，避免与新通报通道双重投递
    assert updated.broadcast_enabled is False
    assert "submit_monitor_report" in updated.tool_names
    # 推送目标仍是运行时字段：部署侧的收件人配置保留（通道关闭后为惰性字段）
    assert updated.target_user_ids == ["app:android:android_demo"]
