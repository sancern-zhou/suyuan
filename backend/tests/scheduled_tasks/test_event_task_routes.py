from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import scheduled_task_routes as routes


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


class FakeService:
    def __init__(self):
        self.tasks = {}
        self.retry_execution_id = None

    def create_task(self, task):
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
    app = FastAPI()
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


def test_retry_delivery_endpoint_uses_existing_execution(monkeypatch):
    client, service = _client(monkeypatch)

    response = client.post(
        "/api/scheduled-tasks/executions/exec-1/retry-delivery"
    )

    assert response.status_code == 200
    assert response.json()["retried_user_ids"] == ["admin-2"]
    assert service.retry_execution_id == "exec-1"
