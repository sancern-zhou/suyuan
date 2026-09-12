from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.api import scheduled_task_routes as routes
from app.auth.dependencies import require_current_user
from app.auth.models import CurrentUser


class FakeUser:
    def __init__(self, user_id, *, channel="weixin:auto", status="active"):
        self.id = user_id
        self.channel = channel
        self.status = status
        self.social_user_id = f"{channel}:bot:{user_id}"


class FakeRegistry:
    def __init__(self):
        self.users = {
            "admin-1": FakeUser("admin-1"),
            "admin-2": FakeUser("admin-2"),
            "qq-user": FakeUser("qq-user", channel="qq"),
        }

    async def get_user(self, user_id):
        return self.users.get(user_id)


class FakeToolRegistry:
    statuses = {"read_file": "enabled", "write_file": "enabled", "disabled": "disabled"}

    def get_tool_status(self, name):
        return self.statuses.get(name)

    def list_tools(self):
        return list(self.statuses)

    def get_tools_info(self):
        return [
            {"name": name, "status": status, "description": name}
            for name, status in self.statuses.items()
        ]


class FakeService:
    def __init__(self):
        self.tasks = {}
        self.retry_execution_id = None
        self.started_task_ids = []

    def create_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def list_tasks(self, enabled_only=False):
        tasks = list(self.tasks.values())
        if enabled_only:
            tasks = [task for task in tasks if task.enabled]
        return tasks

    def update_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def start_task_now(self, task_id):
        self.started_task_ids.append(task_id)

    def get_scheduler_status(self):
        return {"scheduled_tasks": []}

    def get_execution(self, execution_id):
        return None

    async def retry_failed_delivery(self, execution_id):
        self.retry_execution_id = execution_id
        return {
            "success": True,
            "retried_user_ids": ["admin-2"],
            "delivery_results": [{"user_id": "admin-2", "sent": True}],
        }


def _client(monkeypatch, user=None):
    service = FakeService()
    monkeypatch.setattr(routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(routes, "get_social_user_registry", lambda: FakeRegistry())
    monkeypatch.setattr(routes, "get_tool_registry", lambda: FakeToolRegistry())
    app = FastAPI()
    app.dependency_overrides[require_current_user] = lambda: user or CurrentUser(
        id="creator-1",
        username="creator",
        display_name="任务创建人",
        is_admin=True,
        auth_source="mock",
    )
    app.include_router(routes.router)
    return TestClient(app), service


def _event_payload():
    return {
        "name": "运城告警推送",
        "description": "有告警时生成报告并推送",
        "execution_mode": "social",
        "trigger_type": "event",
        "schedule_type": None,
        "event_type": "yuncheng.alert.created",
        "event_filters": {"city": "运城市"},
        "broadcast_enabled": True,
        "target_user_ids": ["admin-1", "admin-2"],
        "enabled": True,
        "prompt": "执行运城告警溯源报告任务",
        "timeout_seconds": 1800,
        "prompt": "执行运城告警溯源报告任务",
        "tags": ["yuncheng", "event"],
    }


def test_list_event_types(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.get("/api/scheduled-tasks/event-types")

    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "yuncheng.alert.created"


def test_super_admin_account_can_see_disabled_tasks(monkeypatch):
    client, service = _client(
        monkeypatch,
        user=CurrentUser(
            id="1",
            username="ScGuanLy",
            display_name="超级管理员",
            is_admin=False,
            auth_source="company",
        ),
    )
    task = routes.ScheduledTask(
        task_id="task-1",
        name="隐藏任务",
        description="disabled task",
        prompt="执行隐藏任务",
        trigger_type="schedule",
        schedule_type="daily_8am",
        enabled=False,
        owner_user_id="someone-else",
        owner_username="someone-else",
        owner_display_name="Someone Else",
    )
    service.tasks[task.task_id] = task

    response = client.get("/api/scheduled-tasks")

    assert response.status_code == 200
    assert [item["task"]["task_id"] for item in response.json()] == ["task-1"]


def test_non_admin_can_see_system_workspace_task(monkeypatch):
    client, service = _client(
        monkeypatch,
        user=CurrentUser(
            id="viewer-1",
            username="viewer",
            display_name="普通用户",
            is_admin=False,
            auth_source="company",
        ),
    )
    hidden_task = routes.ScheduledTask(
        task_id="task-hidden",
        name="其他用户任务",
        description="foreign task",
        prompt="执行其他用户任务",
        trigger_type="schedule",
        schedule_type="daily_8am",
        owner_user_id="someone-else",
        owner_username="someone-else",
        owner_display_name="Someone Else",
    )
    workspace_task = routes.ScheduledTask(
        task_id="task-system",
        name="系统工作区任务",
        description="system workspace task",
        prompt="执行系统工作区任务",
        trigger_type="schedule",
        schedule_type="daily_8am",
        created_by="system",
        owner_user_id="system",
        owner_username="scheduled-task",
        owner_display_name="定时任务",
        workspace_entry=routes.WorkspaceEntry(enabled=True, title="系统工作区任务"),
    )
    service.tasks[hidden_task.task_id] = hidden_task
    service.tasks[workspace_task.task_id] = workspace_task

    response = client.get("/api/scheduled-tasks")

    assert response.status_code == 200
    assert [item["task"]["task_id"] for item in response.json()] == ["task-system"]


def test_create_event_task_with_multiple_users(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.post("/api/scheduled-tasks", json=_event_payload())

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["trigger_type"] == "event"
    assert task["target_user_ids"] == ["admin-1", "admin-2"]
    assert task["schedule_type"] is None
    assert task["owner_user_id"] == "creator-1"
    assert task["owner_username"] == "creator"
    assert task["owner_display_name"] == "任务创建人"


def test_create_task_persists_selected_skill(monkeypatch):
    client, _ = _client(monkeypatch)
    loaded = []
    monkeypatch.setattr(
        routes,
        "load_skill_selection",
        lambda skill_id: loaded.append(skill_id) or SimpleNamespace(skill_id=skill_id),
    )
    payload = _event_payload()
    payload["skill_id"] = "station-alarm-diagnosis"

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 200
    assert response.json()["task"]["skill_id"] == "station-alarm-diagnosis"
    assert loaded == ["station-alarm-diagnosis"]


def test_create_scheduled_task_persists_selected_skill(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_skill_selection",
        lambda skill_id: SimpleNamespace(skill_id=skill_id),
    )
    payload = _event_payload()
    payload.update({
        "name": "定时诊断",
        "trigger_type": "schedule",
        "schedule_type": "daily_8am",
        "event_type": None,
        "event_filters": {},
        "broadcast_enabled": False,
        "target_user_ids": [],
        "skill_id": "station-alarm-diagnosis",
    })

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 200
    assert response.json()["task"]["trigger_type"] == "schedule"
    assert response.json()["task"]["skill_id"] == "station-alarm-diagnosis"


def test_update_task_can_clear_selected_skill(monkeypatch):
    client, service = _client(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_skill_selection",
        lambda skill_id: SimpleNamespace(skill_id=skill_id),
    )
    payload = _event_payload()
    payload["skill_id"] = "station-alarm-diagnosis"
    created = client.post("/api/scheduled-tasks", json=payload)
    task_id = created.json()["task"]["task_id"]

    response = client.put(
        f"/api/scheduled-tasks/{task_id}",
        json={"skill_id": None},
    )

    assert response.status_code == 200
    assert response.json()["task"]["skill_id"] is None
    assert service.get_task(task_id).skill_id is None


def test_create_task_rejects_missing_skill(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(
        routes,
        "load_skill_selection",
        lambda skill_id: (_ for _ in ()).throw(FileNotFoundError(skill_id)),
    )
    payload = _event_payload()
    payload["skill_id"] = "missing-skill"

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "invalid_task_skill",
        "skill_id": "missing-skill",
        "message": "Skill 不存在：missing-skill",
    }


def test_create_rejects_unregistered_event_type(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _event_payload()
    payload["event_type"] = "unknown.event"

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert "Unregistered event_type" in response.json()["detail"]


def test_create_rejects_non_wechat_recipient(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _event_payload()
    payload["target_user_ids"] = ["qq-user"]

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert "active bound WeChat user" in response.json()["detail"]


def test_create_rejects_empty_broadcast_recipient_list_as_bad_request(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _event_payload()
    payload["target_user_ids"] = []

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert "target_user_ids is required" in response.json()["detail"]


def test_update_rejects_empty_broadcast_recipient_list_as_bad_request(monkeypatch):
    client, service = _client(monkeypatch)
    created = client.post("/api/scheduled-tasks", json=_event_payload())
    task_id = created.json()["task"]["task_id"]

    response = client.put(
        f"/api/scheduled-tasks/{task_id}",
        json={"target_user_ids": []},
    )

    assert response.status_code == 400


def test_retry_delivery_endpoint_uses_existing_execution(monkeypatch):
    client, service = _client(monkeypatch)

    response = client.post(
        "/api/scheduled-tasks/executions/exec-1/retry-delivery"
    )

    assert response.status_code == 200
    assert response.json()["retried_user_ids"] == ["admin-2"]
    assert service.retry_execution_id == "exec-1"


def test_custom_task_rejects_invalid_tools_with_structured_details(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _event_payload()
    payload.update({
        "execution_mode": "custom",
        "tool_names": ["missing", "disabled"],
    })

    response = client.post("/api/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "invalid_custom_task_tools",
        "items": [
            {"name": "missing", "reason": "not_found"},
            {"name": "disabled", "reason": "disabled"},
        ],
    }


def test_updating_custom_task_to_existing_mode_clears_tool_names(monkeypatch):
    client, _ = _client(monkeypatch)
    payload = _event_payload()
    payload.update({"execution_mode": "custom", "tool_names": ["read_file"]})
    created = client.post("/api/scheduled-tasks", json=payload)
    task_id = created.json()["task"]["task_id"]

    response = client.put(
        f"/api/scheduled-tasks/{task_id}",
        json={"execution_mode": "assistant"},
    )

    assert response.status_code == 200
    assert response.json()["task"]["tool_names"] is None


def test_update_ignores_unknown_client_fields(monkeypatch):
    """客户端额外字段不得进入任务模型。"""
    client, service = _client(monkeypatch)
    created = client.post("/api/scheduled-tasks", json=_event_payload())
    task_id = created.json()["task"]["task_id"]

    response = client.put(
        f"/api/scheduled-tasks/{task_id}",
        json={
            "unused_field": {"prompt": "旧提示词", "timeout_seconds": 600},
        },
    )

    assert response.status_code == 200
    updated = service.get_task(task_id)
    assert "unused_field" not in updated.model_dump()
    assert updated.timeout_seconds == 1800


def test_execute_now_returns_immediately_without_waiting(monkeypatch):
    """手动立即执行必须后台运行并立即返回，避免网关 504。"""
    client, service = _client(monkeypatch)
    payload = _event_payload()
    payload.update({
        "trigger_type": "schedule",
        "schedule_type": "daily_8am",
        "event_type": None,
        "event_filters": {},
        "broadcast_enabled": False,
        "target_user_ids": [],
    })
    created = client.post("/api/scheduled-tasks", json=payload)
    task_id = created.json()["task"]["task_id"]

    response = client.post(f"/api/scheduled-tasks/{task_id}/execute")

    assert response.status_code == 202
    assert response.json()["success"] is True
    assert service.started_task_ids == [task_id]
