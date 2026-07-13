from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse


def test_scheduled_task_proxy_matches_full_namespace_for_web_only():
    from app.core.scheduled_task_worker_proxy import (
        build_worker_scheduled_tasks_url,
        should_proxy_scheduled_tasks_request,
    )

    assert should_proxy_scheduled_tasks_request("/api/scheduled-tasks", "web")
    assert should_proxy_scheduled_tasks_request(
        "/api/scheduled-tasks/task-1/execute",
        "web",
    )
    assert should_proxy_scheduled_tasks_request(
        "/api/scheduled-tasks/executions/exec-1/retry-delivery",
        "web",
    )
    assert not should_proxy_scheduled_tasks_request(
        "/api/scheduled-tasks",
        "worker",
    )
    assert not should_proxy_scheduled_tasks_request("/api/social/users", "web")
    assert (
        build_worker_scheduled_tasks_url(
            "http://127.0.0.1:8011/",
            "/api/scheduled-tasks",
            "enabled_only=true",
        )
        == "http://127.0.0.1:8011/api/scheduled-tasks?enabled_only=true"
    )


def test_worker_internal_api_exposes_scheduled_tasks(monkeypatch):
    from app.api import scheduled_task_routes
    from app.lifecycle.social_worker_api import create_social_worker_api_app
    from app.scheduled_tasks.models import ScheduledTask, TaskStep

    task = ScheduledTask(
        task_id="task-event",
        name="event task",
        description="event task",
        execution_mode="social",
        trigger_type="event",
        event_type="yuncheng.alert.created",
        broadcast_enabled=False,
        steps=[TaskStep(
            step_id="step-1",
            description="run",
            agent_prompt="run",
        )],
    )

    class FakeService:
        def list_tasks(self, enabled_only=False):
            return [task]

        def get_scheduler_status(self):
            return {"scheduled_tasks": []}

    monkeypatch.setattr(
        scheduled_task_routes,
        "get_scheduled_task_service",
        lambda: FakeService(),
    )
    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    client = TestClient(app)

    assert client.get("/api/scheduled-tasks").status_code == 403
    response = client.get(
        "/api/scheduled-tasks",
        headers={"x-social-worker-token": "secret"},
    )

    assert response.status_code == 200
    assert response.json()[0]["task"]["task_id"] == "task-event"


def test_scheduled_task_proxy_returns_503_when_worker_is_unavailable(monkeypatch):
    from app.core.scheduled_task_worker_proxy import (
        ScheduledTaskWorkerProxyMiddleware,
    )

    async def fail_request(*args, **kwargs):
        request = httpx.Request("GET", "http://127.0.0.1:8011/api/scheduled-tasks")
        raise httpx.ConnectError("worker down", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "request", fail_request)
    app = FastAPI()

    @app.get("/api/scheduled-tasks")
    async def local_tasks():
        return JSONResponse({"source": "web"})

    app.add_middleware(
        ScheduledTaskWorkerProxyMiddleware,
        app_role="web",
        worker_base_url="http://127.0.0.1:8011",
        worker_token="secret",
    )
    response = TestClient(app).get("/api/scheduled-tasks")

    assert response.status_code == 503
    assert "Scheduled task worker unavailable" in response.json()["detail"]
