from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from app.auth.models import CurrentUser
from app.auth.internal_identity import (
    INTERNAL_USER_HEADER,
    decode_internal_user,
    encode_internal_user,
)


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
    assert not should_proxy_scheduled_tasks_request(
        "/api/scheduled-tasks",
        "web",
        scheduled_tasks_enabled=False,
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


def test_proxy_replaces_spoofed_identity_with_authenticated_request_user(monkeypatch):
    from app.core.scheduled_task_worker_proxy import ScheduledTaskWorkerProxyMiddleware

    captured = {}

    async def capture_request(*args, **kwargs):
        captured.update(kwargs.get("headers") or {})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.AsyncClient, "request", capture_request)

    class InjectAuthenticatedUser:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            scope = dict(scope)
            scope["state"] = {
                **dict(scope.get("state") or {}),
                "current_user": CurrentUser(
                    id="creator-1",
                    username="creator",
                    display_name="任务创建人",
                    role_codes=("ADMIN",),
                    is_admin=True,
                    auth_source="mock",
                ),
            }
            await self.app(scope, receive, send)

    app = FastAPI()
    app.add_middleware(
        ScheduledTaskWorkerProxyMiddleware,
        app_role="web",
        worker_base_url="http://127.0.0.1:8011",
        worker_token="secret",
    )
    wrapped = InjectAuthenticatedUser(app)

    response = TestClient(wrapped).post(
        "/api/scheduled-tasks",
        headers={INTERNAL_USER_HEADER: encode_internal_user(CurrentUser(
            id="attacker",
            username="attacker",
            display_name="攻击者",
        ))},
        json={"name": "task"},
    )

    assert response.status_code == 200
    forwarded = decode_internal_user(captured[INTERNAL_USER_HEADER])
    assert forwarded.id == "creator-1"
    assert forwarded.username == "creator"
    assert forwarded.display_name == "任务创建人"
    assert forwarded.is_admin is True


def test_worker_restores_trusted_identity_for_task_creation(monkeypatch):
    from app.api import scheduled_task_routes
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    class FakeService:
        def __init__(self):
            self.created = None

        def create_task(self, task):
            self.created = task
            return task

        def get_scheduler_status(self):
            return {"scheduled_tasks": []}

    service = FakeService()
    monkeypatch.setattr(
        scheduled_task_routes,
        "get_scheduled_task_service",
        lambda: service,
    )
    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    user = CurrentUser(
        id="creator-1",
        username="creator",
        display_name="任务创建人",
        auth_source="mock",
    )

    response = TestClient(app).post(
        "/api/scheduled-tasks",
        headers={
            "x-social-worker-token": "secret",
            INTERNAL_USER_HEADER: encode_internal_user(user),
        },
        json={
            "name": "测试任务",
            "description": "测试内部身份传递",
            "workspace_entry": {
                "enabled": True,
                "title": "测试业务入口",
            },
            "schedule_type": "once",
            "run_at": "2026-07-18T12:00:00",
            "steps": [{
                "step_id": "step-1",
                "description": "执行",
                "agent_prompt": "执行",
            }],
        },
    )

    assert response.status_code == 200
    assert service.created.owner_user_id == "creator-1"
    assert service.created.owner_username == "creator"
    assert service.created.owner_display_name == "任务创建人"
    assert service.created.workspace_entry.enabled is True
    assert service.created.workspace_entry.title == "测试业务入口"
    assert response.json()["task"]["workspace_entry"] == {
        "enabled": True,
        "title": "测试业务入口",
    }


def test_worker_rejects_malformed_internal_identity_after_token_validation():
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    response = TestClient(app).post(
        "/api/scheduled-tasks",
        headers={
            "x-social-worker-token": "secret",
            INTERNAL_USER_HEADER: "not-base64!",
        },
        json={},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_internal_identity"}


@pytest.mark.asyncio
async def test_worker_rejects_unsigned_identity_from_non_loopback_peer():
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="",
    )
    transport = httpx.ASGITransport(
        app=app,
        client=("203.0.113.10", 12345),
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        response = await client.post(
            "/api/scheduled-tasks",
            headers={INTERNAL_USER_HEADER: encode_internal_user(CurrentUser(
                id="attacker",
                username="attacker",
                display_name="攻击者",
            ))},
            json={},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "internal_identity_transport_not_configured"}


def test_authenticated_web_request_creates_worker_task_for_resolved_user(
    monkeypatch,
):
    from app.api import scheduled_task_routes
    from app.auth.middleware import GatewayAuthenticationMiddleware
    from app.core.scheduled_task_worker_proxy import ScheduledTaskWorkerProxyMiddleware
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    class FakeService:
        def __init__(self):
            self.created = None

        def create_task(self, task):
            self.created = task
            return task

        def get_scheduler_status(self):
            return {"scheduled_tasks": []}

    class FakeAuthService:
        async def authenticate(self, token, sys_code):
            return CurrentUser(
                id="creator-e2e",
                username="e2e-user",
                display_name="端到端用户",
                auth_source="mock",
            )

    service = FakeService()
    monkeypatch.setattr(
        scheduled_task_routes,
        "get_scheduled_task_service",
        lambda: service,
    )
    worker_app = create_social_worker_api_app(
        SimpleNamespace(channel_manager=None),
        internal_token="secret",
    )
    original_request = httpx.AsyncClient.request

    async def forward_to_worker(self, method, url, **kwargs):
        transport = httpx.ASGITransport(
            app=worker_app,
            client=("127.0.0.1", 12345),
        )
        async with httpx.AsyncClient(transport=transport) as worker_client:
            return await original_request(worker_client, method, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "request", forward_to_worker)

    web_app = FastAPI()
    web_app.add_middleware(
        ScheduledTaskWorkerProxyMiddleware,
        app_role="web",
        worker_base_url="http://worker",
        worker_token="secret",
    )
    web_app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=SimpleNamespace(
            auth_mode="mock",
            auth_sys_code="SUYUAN",
            auth_docs_public=False,
            trusted_gateway_networks_list=["127.0.0.1/32"],
        ),
        auth_service=FakeAuthService(),
    )

    response = TestClient(web_app).post(
        "/api/scheduled-tasks",
        json={
            "name": "端到端任务",
            "description": "验证完整身份链路",
            "schedule_type": "once",
            "run_at": "2026-07-18T12:00:00",
            "steps": [{
                "step_id": "step-1",
                "description": "执行",
                "agent_prompt": "执行",
            }],
        },
    )

    assert response.status_code == 200
    assert service.created.owner_user_id == "creator-e2e"
    assert service.created.owner_username == "e2e-user"
    assert service.created.owner_display_name == "端到端用户"
