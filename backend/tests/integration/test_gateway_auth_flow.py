from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.auth.dependencies import require_current_user
from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.identity_cache import IdentityCache
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.models import CurrentUser
from app.auth.routes import router as auth_router
from app.auth.service import AuthenticationService
from app.auth.share_access import ShareAccessService, resource_preview_identity
from app.auth.ws_tickets import WebSocketTicketService
from config.settings import Settings


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)

    async def getdel(self, key):
        return self.data.pop(key, None)


class FakePlatform:
    async def get_current_user(self, token, sys_code):
        if token == "outage":
            raise AuthenticationUnavailable("unavailable")
        if token != "valid":
            raise AuthenticationRejected("rejected")
        return CurrentUser(id="viewer", username="viewer", display_name="Viewer")

    async def close(self):
        pass


class FakeEventBus:
    async def connect(self, websocket):
        await websocket.accept()

    def disconnect(self, websocket):
        pass


@pytest.mark.asyncio
async def test_fake_infrastructure_gateway_flow(monkeypatch):
    from app.api import scheduled_task_ws

    redis = FakeRedis()
    settings = Settings(
        _env_file=None,
        auth_mode="company",
        auth_sys_code="SUYUAN",
        trusted_gateway_networks="127.0.0.1/32",
    )
    auth = AuthenticationService(
        settings=settings,
        cache=IdentityCache(redis, key_prefix="test:", max_ttl_seconds=60),
        platform_client=FakePlatform(),
    )
    shares = ShareAccessService("secret", ttl_seconds=60)
    app = FastAPI()
    app.state.ws_ticket_service = WebSocketTicketService(
        redis, key_prefix="test:", ttl_seconds=30
    )
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=settings,
        auth_service=auth,
        share_access=shares,
    )
    app.include_router(auth_router, prefix="/api")
    monkeypatch.setattr(scheduled_task_ws, "get_event_bus", lambda: FakeEventBus())
    app.include_router(scheduled_task_ws.router)

    @app.get("/api/info")
    async def info(user: CurrentUser = Depends(require_current_user)):
        return {"id": user.id, "is_admin": user.is_admin}

    @app.get("/api/events")
    async def events(user: CurrentUser = Depends(require_current_user)):
        async def content():
            yield f"data: {user.id}\n\n"
        return StreamingResponse(content(), media_type="text/event-stream")

    @app.get("/api/sessions/{session_id}/resources/{resource_id}/content/{path:path}")
    async def resource_asset(session_id: str, resource_id: str, path: str):
        return {"session_id": session_id, "resource_id": resource_id, "path": path}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
    headers = {
        "Authorization": "Bearer valid",
        "SysCode": "SUYUAN",
        "X-User-Id": "owner",
        "X-Is-Admin": "true",
    }
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        anonymous = await client.get("/api/info")
        valid = await client.get("/api/info", headers=headers)
        outage = await client.get(
            "/api/info",
            headers={"Authorization": "Bearer outage", "SysCode": "SUYUAN"},
        )
        sse = await client.get("/api/events", headers=headers)
        ticket_response = await client.post("/api/auth/ws-ticket", headers=headers)
        grant = shares.issue(
            "session-resource",
            resource_preview_identity("session-1", "resource-1"),
        )
        shared = await client.get(
            f"/api/sessions/session-1/resources/resource-1/content/assets/chart.png?preview_ticket={grant}",
        )

    assert anonymous.status_code == 401
    assert valid.json() == {"id": "viewer", "is_admin": False}
    assert outage.status_code == 503
    assert sse.text == "data: viewer\n\n"
    assert shared.status_code == 200

    ticket = ticket_response.json()["ticket"]
    with TestClient(app).websocket_connect(
        f"/ws/scheduled-tasks?ticket={ticket}"
    ) as websocket:
        websocket.send_text("ping")
        assert websocket.receive_text() == "pong"


def test_authenticated_social_account_request_keeps_identity_across_worker_proxy(
    monkeypatch,
):
    from app.api import social_account_routes
    from app.core.social_account_worker_proxy import SocialAccountWorkerProxyMiddleware
    from app.lifecycle.social_worker_api import create_social_worker_api_app

    class FakeAuthService:
        async def authenticate(self, token, sys_code):
            assert token == "local-mock"
            assert sys_code == "SUYUAN"
            return CurrentUser(
                id="social-user-1",
                username="social-user",
                display_name="社交用户",
            )

    class FakeBindings:
        async def list_visible(self, user):
            assert user.id == "social-user-1"
            return [SimpleNamespace(account_id="weixin-1")]

    channel = SimpleNamespace(
        config=SimpleNamespace(name="微信账号", enabled=True),
        is_running=True,
        bot_account="bot-1",
        _token="worker-token",
        _current_qr_code_path=None,
    )
    worker_app = create_social_worker_api_app(
        SimpleNamespace(
            channel_manager=SimpleNamespace(
                channels={"weixin:weixin-1": channel},
            ),
        ),
        internal_token="worker-secret",
    )
    worker_app.dependency_overrides[
        social_account_routes.get_social_binding_service
    ] = lambda: FakeBindings()

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
        SocialAccountWorkerProxyMiddleware,
        app_role="web",
        worker_base_url="http://worker",
        worker_token="worker-secret",
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

    try:
        response = TestClient(web_app).get("/api/social/accounts")
    finally:
        social_account_routes.set_channel_manager_override(None)

    assert response.status_code == 200
    assert response.json() == [{
        "id": "weixin-1",
        "name": "微信账号",
        "type": "weixin",
        "enabled": True,
        "running": True,
        "bot_account": "bot-1",
        "login_status": "logged_in",
        "qr_code_available": False,
    }]
