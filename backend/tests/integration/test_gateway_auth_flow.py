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
from app.auth.share_access import ShareAccessService
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

    @app.get("/api/reports/{report_id}/assets/{path:path}")
    async def report_asset(report_id: str, path: str):
        return {"report_id": report_id, "path": path}

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
        grant = shares.issue("report", "r1")
        shared = await client.get(
            "/api/reports/r1/assets/chart.png",
            cookies={"suyuan-share-grant": grant},
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
