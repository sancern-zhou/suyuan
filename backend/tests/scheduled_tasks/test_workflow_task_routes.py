from types import SimpleNamespace

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import scheduled_task_routes as routes
    from app.auth.dependencies import require_current_user
    from app.auth.models import CurrentUser
except Exception as import_error:  # pragma: no cover
    pytest.skip(
        f"scheduled_task_routes 尚不可导入，合并 main 后自动生效：{import_error}",
        allow_module_level=True,
    )

WORKFLOW_EVENT = "xuchang.station_deviation.alert_created"
REGISTERED = ["xuchang_station_deviation_alert"]


class FakeService:
    def __init__(self):
        self.tasks = {}

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


def _fake_event_definitions():
    return [SimpleNamespace(event_type=WORKFLOW_EVENT, label="站点告警", description="", filter_fields=["city"])]


def _client(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(routes, "get_social_user_registry", lambda: SimpleNamespace(get_user=None))
    monkeypatch.setattr(
        "app.scheduled_tasks.workflow_tasks.registered_workflows", lambda: REGISTERED
    )
    monkeypatch.setattr(routes, "get_event_definitions", _fake_event_definitions)
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


def _workflow_payload(**overrides):
    payload = {
        "name": "站点快速污染抬升告警",
        "description": "确定性工作流告警通报",
        "execution_mode": "workflow",
        "workflow_name": "xuchang_station_deviation_alert",
        "workflow_args": {},
        "trigger_type": "event",
        "schedule_type": None,
        "event_type": WORKFLOW_EVENT,
        "event_filters": {"city": "许昌市"},
        "broadcast_enabled": True,
        "target_user_ids": ["app:android:android_demo"],
        "enabled": True,
        "prompt": "确定性工作流任务",
        "timeout_seconds": 120,
        "tags": ["workflow"],
    }
    payload.update(overrides)
    return payload


def test_list_workflows_returns_registered_names(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.get("/api/scheduled-tasks/workflows")

    assert response.status_code == 200
    assert response.json() == {"workflows": REGISTERED}


def test_create_workflow_task_with_registered_name(monkeypatch):
    client, service = _client(monkeypatch)

    response = client.post("/api/scheduled-tasks", json=_workflow_payload())

    assert response.status_code == 200
    task = response.json()["task"]
    assert task["execution_mode"] == "workflow"
    assert task["workflow_name"] == "xuchang_station_deviation_alert"
    assert service.tasks[task["task_id"]].workflow_args == {}


def test_create_workflow_task_with_unknown_name_is_rejected(monkeypatch):
    client, service = _client(monkeypatch)

    response = client.post(
        "/api/scheduled-tasks", json=_workflow_payload(workflow_name="missing_workflow")
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_task_workflow"
    assert detail["registered"] == REGISTERED
    assert service.tasks == {}


def test_update_workflow_task_cannot_change_execution_mode(monkeypatch):
    client, service = _client(monkeypatch)
    created = client.post("/api/scheduled-tasks", json=_workflow_payload()).json()["task"]
    task_id = created["task_id"]

    response = client.put(
        f"/api/scheduled-tasks/{task_id}",
        json={"execution_mode": "social"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "workflow_mode_immutable"
    assert service.tasks[task_id].execution_mode == "workflow"


def test_update_workflow_task_preserves_workflow_fields(monkeypatch):
    client, service = _client(monkeypatch)
    created = client.post("/api/scheduled-tasks", json=_workflow_payload()).json()["task"]
    task_id = created["task_id"]

    response = client.put(f"/api/scheduled-tasks/{task_id}", json={"enabled": False})

    assert response.status_code == 200
    task = service.tasks[task_id]
    assert task.enabled is False
    assert task.workflow_name == "xuchang_station_deviation_alert"
