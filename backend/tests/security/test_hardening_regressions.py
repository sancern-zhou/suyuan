"""Security regression tests for the 2026-08 hardening sweep."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import scheduled_task_routes as st_routes
from app.auth.dependencies import require_current_user
from app.auth.internal_identity import decode_internal_user, encode_internal_user
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.models import CurrentUser
from app.auth.share_access import ShareAccessService
from app.tools.utility.bash_tool import BashTool
from app.utils.path_config import (
    BACKEND_ROOT,
    PROJECT_ROOT,
    is_agent_protected_write_path,
    is_agent_sensitive_path,
)


def _current_user(**overrides) -> CurrentUser:
    values = dict(
        id="user-1",
        username="user",
        display_name="用户",
        is_admin=False,
    )
    values.update(overrides)
    return CurrentUser(**values)


# ---------- share tickets must not fall back to a public constant ----------


def test_share_access_service_rejects_known_dev_constant(monkeypatch):
    import app.auth.share_access as share_access

    monkeypatch.setattr(
        share_access.settings,
        "share_signing_secret",
        None,
        raising=False,
    )
    monkeypatch.setattr(share_access.settings, "environment", "development")
    monkeypatch.setattr(share_access, "_service", None)

    service = share_access.get_share_access_service()
    legacy = ShareAccessService("development-share-grant-secret", ttl_seconds=60)
    ticket = legacy.issue("session-resource", "s:r")
    assert service.verify(ticket, "session-resource", "s:r") is False


def test_share_access_service_rejects_cross_purpose_minimax_key(monkeypatch):
    import app.auth.share_access as share_access

    monkeypatch.setattr(
        share_access.settings, "share_signing_secret", None, raising=False
    )
    monkeypatch.setattr(
        share_access.settings, "minimax_api_key", "sk-cross-purpose", raising=False
    )
    monkeypatch.setattr(share_access.settings, "environment", "development")
    monkeypatch.setattr(share_access, "_service", None)

    service = share_access.get_share_access_service()
    cross = ShareAccessService("sk-cross-purpose", ttl_seconds=60)
    ticket = cross.issue("session-resource", "s:r")
    assert service.verify(ticket, "session-resource", "s:r") is False


# ---------- mock auth must require a trusted (loopback/gateway) peer ----------


class _AlwaysOkAuthService:
    async def authenticate(self, token, sys_code):
        return _current_user()


def _mock_app():
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=SimpleNamespace(
            auth_mode="mock",
            auth_sys_code="SUYUAN",
            auth_docs_public=False,
            trusted_gateway_networks_list=["127.0.0.1/32"],
        ),
        auth_service=_AlwaysOkAuthService(),
    )

    @app.get("/api/private")
    async def private():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_mock_mode_rejects_untrusted_peer():
    import httpx

    transport = httpx.ASGITransport(app=_mock_app(), client=("203.0.113.9", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/api/private")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_mock_mode_allows_trusted_loopback_peer():
    import httpx

    transport = httpx.ASGITransport(app=_mock_app(), client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get("/api/private")
    assert response.status_code == 200


def test_public_paths_only_bypass_for_get_and_head():
    app = _mock_app()

    @app.post("/knowledge-base")
    async def kb_post():
        return {"ok": True}

    # untrusted peer + non-GET method on a whitelisted path must authenticate
    import httpx

    # TestClient 无法指定 peer，直接用 middleware 的行为做单元断言：
    from app.auth.middleware import GatewayAuthenticationMiddleware as M

    middleware = next(
        m.cls for m in app.user_middleware if m.cls is M
    )
    assert middleware is not None
    response = TestClient(app).post("/knowledge-base")
    # TestClient peer ("testclient") 不属于信任网段 → 403
    assert response.status_code == 403


# ---------- internal identity envelope must be signed ----------


def test_internal_identity_roundtrip_with_secret():
    user = _current_user(is_admin=True)
    envelope = encode_internal_user(user, secret="topsecret")
    decoded = decode_internal_user(envelope, secret="topsecret")
    assert decoded.id == user.id and decoded.is_admin


def test_internal_identity_rejects_unsigned_when_secret_configured():
    user = _current_user(is_admin=True)
    unsigned = encode_internal_user(user)
    with pytest.raises(ValueError):
        decode_internal_user(unsigned, secret="topsecret")


def test_internal_identity_rejects_tampered_envelope():
    user = _current_user(is_admin=False)
    envelope = encode_internal_user(user, secret="topsecret")
    forged = encode_internal_user(_current_user(is_admin=True), secret="other")
    encoded_part = forged.split(".", 1)[0]
    signature_part = envelope.split(".", 1)[1]
    with pytest.raises(ValueError):
        decode_internal_user(f"{encoded_part}.{signature_part}", secret="topsecret")


# ---------- bash tool must not allow interpreters/fetchers ----------


@pytest.mark.asyncio
async def test_bash_tool_rejects_python_inline_code():
    tool = BashTool()
    result = await tool.execute(
        command='python -c "import os; os.system(\'id\')"'
    )
    assert not result.get("success")


@pytest.mark.asyncio
async def test_bash_tool_rejects_curl():
    tool = BashTool()
    result = await tool.execute(command="curl http://169.254.169.254/latest/meta-data")
    assert not result.get("success")


# ---------- agent file tools must respect protected paths ----------


def test_sensitive_paths_are_flagged():
    assert is_agent_sensitive_path(BACKEND_ROOT / ".env")
    assert is_agent_sensitive_path(BACKEND_ROOT / ".env.jiangsu-ops")
    assert is_agent_sensitive_path(PROJECT_ROOT / ".git" / "config")
    assert is_agent_sensitive_path(BACKEND_ROOT / "config" / "social_config.yaml")
    assert not is_agent_sensitive_path(BACKEND_ROOT / "docs" / "skills" / "x.md")


def test_protected_write_paths_are_flagged():
    assert is_agent_protected_write_path(
        BACKEND_ROOT / "app" / "tools" / "utility" / "evil_tool.py"
    )
    assert is_agent_protected_write_path(BACKEND_ROOT / ".env")
    assert is_agent_protected_write_path(PROJECT_ROOT / "deploy" / "nginx" / "x")
    assert not is_agent_protected_write_path(
        BACKEND_ROOT / "docs" / "skills" / ".drafts" / "d.md"
    )


# ---------- scheduled task endpoints enforce ownership ----------


class _TaskService:
    def __init__(self, task):
        self.task = task
        self.deleted = False
        self.executed = False

    def get_task(self, task_id):
        return self.task if task_id == self.task.task_id else None

    def delete_task(self, task_id):
        self.deleted = True
        return True

    async def execute_task_now(self, task_id):
        self.executed = True
        from app.scheduled_tasks.models import TaskExecution, ExecutionStatus
        from datetime import datetime

        return TaskExecution(
            execution_id="exec-1",
            task_id=task_id,
            task_name=self.task.name,
            status=ExecutionStatus.SUCCESS,
            started_at=datetime.now(),
        )


def _task(owner_user_id):
    from app.scheduled_tasks.models import ScheduledTask, TaskStep

    return ScheduledTask(
        task_id="task-1",
        name="t",
        description="t",
        execution_mode="assistant",
        trigger_type="schedule",
        schedule_type="daily_custom",
        hour=8,
        minute=0,
        steps=[TaskStep(step_id="s", description="d", agent_prompt="p")],
        owner_user_id=owner_user_id,
        owner_username=owner_user_id,
    )


def _st_app(service, user, monkeypatch):
    app = FastAPI()
    app.dependency_overrides[require_current_user] = lambda: user
    monkeypatch.setattr(
        st_routes, "get_scheduled_task_service", lambda: service
    )
    app.include_router(st_routes.router)
    return app


def test_non_admin_cannot_delete_foreign_task(monkeypatch):
    service = _TaskService(_task("someone-else"))
    app = _st_app(service, _current_user(), monkeypatch)
    response = TestClient(app).delete("/api/scheduled-tasks/task-1")
    assert response.status_code == 404
    assert service.deleted is False


def test_owner_can_delete_own_task(monkeypatch):
    service = _TaskService(_task("user-1"))
    app = _st_app(service, _current_user(), monkeypatch)
    response = TestClient(app).delete("/api/scheduled-tasks/task-1")
    assert response.status_code == 200
    assert service.deleted is True


def test_non_admin_cannot_execute_foreign_task(monkeypatch):
    service = _TaskService(_task("someone-else"))
    app = _st_app(service, _current_user(), monkeypatch)
    response = TestClient(app).post("/api/scheduled-tasks/task-1/execute")
    assert response.status_code == 404
    assert service.executed is False


def test_admin_can_delete_any_task(monkeypatch):
    service = _TaskService(_task("someone-else"))
    app = _st_app(service, _current_user(is_admin=True), monkeypatch)
    response = TestClient(app).delete("/api/scheduled-tasks/task-1")
    assert response.status_code == 200
