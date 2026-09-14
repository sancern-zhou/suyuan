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

REGISTERED = ["jiangsu_network_inspection_workflow"]


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


class FakeCaseStorage:
    def __init__(self, cases=None):
        self.cases = cases or []
        self.saved = None

    def update_case(self, execution_id, case):
        self.saved = (execution_id, case)
        for index, item in enumerate(self.cases):
            if str(item.get("execution_id")) == str(execution_id):
                self.cases[index] = case
                return True
        return False

    def recent_cases(self, limit):
        return list(self.cases)


def _client(monkeypatch, service=None):
    service = service or FakeService()
    monkeypatch.setattr(routes, "get_scheduled_task_service", lambda: service)
    monkeypatch.setattr(routes, "get_social_user_registry", lambda: SimpleNamespace(get_user=None))
    monkeypatch.setattr(
        "app.scheduled_tasks.workflow_tasks.registered_workflows", lambda: REGISTERED
    )
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
        "name": "江苏全网巡检值守",
        "description": "确定性工作流值守结论",
        "execution_mode": "workflow",
        "workflow_name": "jiangsu_network_inspection_workflow",
        "workflow_args": {"period": "day"},
        "trigger_type": "schedule",
        "schedule_type": "daily_8am",
        "broadcast_enabled": False,
        "target_user_ids": [],
        "enabled": True,
        "prompt": "生成 200-300 字值守短结论",
        "timeout_seconds": 600,
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
    assert task["workflow_name"] == "jiangsu_network_inspection_workflow"
    assert service.tasks[task["task_id"]].workflow_args == {"period": "day"}


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
    assert task.workflow_name == "jiangsu_network_inspection_workflow"
    assert task.workflow_args == {"period": "day"}


def test_update_history_case_rewrites_and_reports_missing(monkeypatch):
    service = FakeService()
    service.tasks["jiangsu_network_inspection_watch"] = SimpleNamespace(
        task_id="jiangsu_network_inspection_watch",
        owner_user_id="creator-1",
        created_by="user",
    )
    client, _ = _client(monkeypatch, service)
    storage = FakeCaseStorage([
        {"execution_id": "exec_1", "status": "success", "summary": "旧结论"},
    ])
    monkeypatch.setattr(routes, "TaskCaseStorage", lambda task_id: storage)

    ok = client.put(
        "/api/scheduled-tasks/jiangsu_network_inspection_watch/history/cases/exec_1",
        json={"case": {"execution_id": "exec_1", "status": "success", "summary": "新结论"}},
    )
    assert ok.status_code == 200
    assert ok.json()["case"]["summary"] == "新结论"
    assert storage.saved[0] == "exec_1"

    missing = client.put(
        "/api/scheduled-tasks/jiangsu_network_inspection_watch/history/cases/exec_404",
        json={"case": {"summary": "无效"}},
    )
    assert missing.status_code == 404
