from fastapi import FastAPI
from fastapi.testclient import TestClient

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

    def create_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def update_task(self, task):
        self.tasks[task.task_id] = task
        return task

    def get_scheduler_status(self):
        return {"scheduled_tasks": []}

    async def retry_failed_delivery(self, execution_id):
        self.retry_execution_id = execution_id
        return {
            "success": True,
            "retried_user_ids": ["admin-2"],
            "delivery_results": [{"user_id": "admin-2", "sent": True}],
        }


def _client(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(routes, "get_social_user_registry", lambda: FakeRegistry())
    monkeypatch.setattr(routes, "get_tool_registry", lambda: FakeToolRegistry())
    app = FastAPI()
    app.dependency_overrides[require_current_user] = lambda: CurrentUser(
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
        "steps": [{
            "step_id": "report",
            "description": "生成运城告警报告",
            "agent_prompt": "执行运城告警溯源报告任务",
            "timeout_seconds": 1800,
            "retry_on_failure": False,
        }],
        "tags": ["yuncheng", "event"],
    }


def test_list_event_types(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.get("/api/scheduled-tasks/event-types")

    assert response.status_code == 200
    assert response.json()[0]["event_type"] == "yuncheng.alert.created"


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


def test_event_task_cannot_be_executed_manually(monkeypatch):
    client, service = _client(monkeypatch)
    task_id = "event-task"
    service.create_task(routes.ScheduledTask(
        task_id=task_id,
        name="event task",
        description="event task",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        steps=[routes.TaskStep(
            step_id="step-1",
            description="run",
            agent_prompt="run",
        )],
    ))

    response = client.post(f"/api/scheduled-tasks/{task_id}/execute")

    assert response.status_code == 400
    assert response.json()["detail"] == "Event-triggered tasks cannot be executed manually"


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
