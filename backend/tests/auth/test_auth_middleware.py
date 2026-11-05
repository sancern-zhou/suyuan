import httpx
import pytest
from fastapi import FastAPI, Request

from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.models import CurrentUser
from app.auth.share_access import ShareAccessService, resource_preview_identity
from config.settings import Settings


class FakeAuthService:
    def __init__(self, *, error=None):
        self.error = error
        self.calls = []

    async def authenticate(self, token, sys_code):
        self.calls.append((token, sys_code))
        if self.error:
            raise self.error
        return CurrentUser(
            id="u1", username="zhangsan", display_name="张三", is_admin=False
        )


def _settings(**overrides):
    values = {
        "_env_file": None,
        "auth_mode": "company",
        "auth_sys_code": "SUYUAN",
        "trusted_gateway_networks": "127.0.0.1/32,10.10.204.0/24",
    }
    values.update(overrides)
    return Settings(**values)


def _app(service=None, **setting_overrides):
    app = FastAPI()
    service = service or FakeAuthService()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(**setting_overrides),
        auth_service=service,
        share_access=ShareAccessService("test-preview-secret", ttl_seconds=60),
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/ready")
    async def ready():
        return {"ok": True}

    @app.get("/api/health")
    async def api_health():
        return {"ok": True}

    @app.get("/api/ready")
    async def api_ready():
        return {"ok": True}

    @app.get("/api/auth/runtime-config")
    async def auth_runtime_config():
        return {"authMode": "company", "sysCode": "SUYUAN"}

    @app.get("/login")
    @app.get("/knowledge-base")
    @app.get("/session/{session_id}")
    async def frontend_entry(session_id: str | None = None):
        return {"entry": True}

    @app.get("/assets/{path:path}")
    async def asset(path: str):
        return {"path": path}

    @app.get("/api/sessions/{session_id}/resources/{resource_id}/content/{asset:path}")
    @app.get("/api/sessions/{session_id}/resources/{resource_id}/content")
    async def resource_content(session_id: str, resource_id: str, asset: str = ""):
        return {"session_id": session_id, "resource_id": resource_id, "asset": asset}

    @app.get("/api/shared-conversations")
    @app.get("/api/shared-conversations/{share_id}/resources/{resource_id}")
    @app.get("/api/private")
    async def private(request: Request):
        return {
            "id": request.state.current_user.id,
            "is_admin": request.state.current_user.is_admin,
            "user_header": request.headers.get("x-user-id"),
            "admin_header": request.headers.get("x-is-admin"),
        }

    return app, service


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/shared-conversations", "/api/shared-conversations/s1/resources/r1"])
async def test_shared_routes_accept_signed_app_identity_without_company_gateway(monkeypatch, path):
    from app.social import app_identity

    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-app-signing-secret")
    token = app_identity.issue_access_token_for_identity(app_identity.AppIdentity(
        "account-1", "App user", "company:user-1", 0, auth_source="company",
    ))
    app, service = _app()
    response = await _get(app, path, client_host="203.0.113.1", headers={
        "Authorization": f"Bearer {token}", "X-User-Id": "attacker", "X-Is-Admin": "true",
    })
    assert response.status_code == 200
    assert response.json() == {
        "id": "company:user-1", "is_admin": False, "user_header": None, "admin_header": None,
    }
    assert service.calls == []
    assert (await _get(app, "/api/private", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await _get(app, "/api/shared-conversations-evil", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await _get(app, path)).status_code == 401
    assert (await _get(app, path, headers={"Authorization": f"Bearer {token}tampered"})).status_code == 401
    expired = app_identity._sign({"sub": "account-1", "exp": 1, "typ": "access"})
    assert (await _get(app, path, headers={"Authorization": f"Bearer {expired}"})).status_code == 401
    refresh = app_identity._sign({"sub": "account-1", "exp": 9999999999, "typ": "refresh"})
    assert (await _get(app, path, headers={"Authorization": f"Bearer {refresh}"})).status_code == 401


@pytest.mark.asyncio
async def test_shared_routes_preserve_company_web_authentication():
    app, service = _app()
    response = await _get(app, "/api/shared-conversations", headers={
        "Authorization": "Bearer web-session", "SysCode": "SUYUAN",
    })
    assert response.status_code == 200
    assert response.json()["id"] == "u1"
    assert service.calls == [("web-session", "SUYUAN")]


async def _get(app, path, *, client_host="127.0.0.1", headers=None):
    transport = httpx.ASGITransport(app=app, client=(client_host, 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/ready",
        "/api/health",
        "/api/ready",
        "/api/auth/runtime-config",
        "/login",
        "/knowledge-base",
        "/session/session-1",
        "/assets/app.js",
    ],
)
async def test_exact_public_routes_do_not_authenticate(path):
    app, service = _app()

    response = await _get(app, path)

    assert response.status_code == 200
    assert service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/health/private",
        "/login/private",
        "/session",
        "/api/reports/share",
        "/api/reports/share/grant",
        "/api/reports/share/grant/private",
        "/api/html-artifacts/share/grant/private",
        "/api/html-artifacts/share/grant",
        "/api/signed-media",
        "/api/signed-media/a/b.png?expires=1&signature=x",
        "/api/auth/runtime-config/private",
    ],
)
async def test_similarly_named_routes_remain_private(path):
    app, _ = _app()

    response = await _get(app, path)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_bearer_token_is_401():
    app, service = _app()
    response = await _get(app, "/api/private", headers={"SysCode": "SUYUAN"})
    assert response.status_code == 401
    assert service.calls == []


@pytest.mark.asyncio
async def test_wrong_sys_code_is_401_without_authentication_call():
    app, service = _app()
    response = await _get(
        app,
        "/api/private",
        headers={"Authorization": "Bearer valid", "SysCode": "OTHER"},
    )
    assert response.status_code == 401
    assert service.calls == []


@pytest.mark.asyncio
async def test_untrusted_immediate_peer_is_rejected_and_forwarded_for_is_ignored():
    app, service = _app()
    response = await _get(
        app,
        "/api/private",
        client_host="203.0.113.5",
        headers={
            "Authorization": "Bearer valid",
            "SysCode": "SUYUAN",
            "X-Forwarded-For": "127.0.0.1",
        },
    )
    assert response.status_code == 403
    assert service.calls == []


@pytest.mark.asyncio
async def test_authentication_outage_is_503():
    app, _ = _app(
        FakeAuthService(error=AuthenticationUnavailable("authentication unavailable"))
    )
    response = await _get(
        app,
        "/api/private",
        headers={"Authorization": "Bearer valid", "SysCode": "SUYUAN"},
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_rejected_token_is_401():
    app, _ = _app(FakeAuthService(error=AuthenticationRejected("rejected")))
    response = await _get(
        app,
        "/api/private",
        headers={"Authorization": "Bearer rejected", "SysCode": "SUYUAN"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_identity_is_injected_and_spoofed_headers_are_removed():
    app, service = _app()
    response = await _get(
        app,
        "/api/private",
        headers={
            "Authorization": "Bearer valid",
            "SysCode": "SUYUAN",
            "X-User-Id": "attacker",
            "X-Is-Admin": "true",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "u1",
        "is_admin": False,
        "user_header": None,
        "admin_header": None,
    }
    assert service.calls == [("valid", "SUYUAN")]


@pytest.mark.asyncio
async def test_docs_are_private_by_default_and_explicitly_public_when_enabled():
    private_app, _ = _app()
    public_app, _ = _app(auth_docs_public=True)

    assert (await _get(private_app, "/openapi.json")).status_code == 401
    assert (await _get(public_app, "/openapi.json")).status_code == 200


@pytest.mark.asyncio
async def test_session_resource_preview_ticket_allows_only_bound_content_subtree():
    app, service = _app()
    ticket = ShareAccessService("test-preview-secret", ttl_seconds=60).issue(
        "session-resource",
        resource_preview_identity("session-1", "resource-1"),
    )

    allowed = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-1/content/assets/style.css?preview_ticket={ticket}",
    )
    inherited = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-1/content/_preview/{ticket}/assets/style.css",
    )
    wrong_resource = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-2/content/_preview/{ticket}/assets/style.css",
    )

    assert allowed.status_code == 200
    assert inherited.status_code == 200
    assert wrong_resource.status_code == 401
    assert service.calls == []


@pytest.mark.asyncio
async def test_session_resource_path_ticket_allows_bound_content_subtree():
    app, service = _app()
    ticket = ShareAccessService("test-preview-secret", ttl_seconds=60).issue(
        "session-resource",
        resource_preview_identity("session-1", "resource-1"),
    )

    entry = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-1/content/_t/{ticket}/",
    )
    asset = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-1/content/_t/{ticket}/report_files/quarto.js",
    )
    wrong_resource = await _get(
        app,
        f"/api/sessions/session-1/resources/resource-2/content/_t/{ticket}/",
    )
    no_ticket = await _get(
        app,
        "/api/sessions/session-1/resources/resource-1/content/_t/not-valid/report_files/quarto.js",
    )

    assert entry.status_code == 200
    assert asset.status_code == 200
    assert wrong_resource.status_code == 401
    assert no_ticket.status_code == 401
    assert service.calls == []


@pytest.mark.asyncio
async def test_dashboard_access_token_allows_only_configured_prefix_gets():
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(
            dashboard_api_prefix="/api/dashboard-example",
            dashboard_access_token="screen-token-abc",
        ),
        auth_service=FakeAuthService(),
        share_access=ShareAccessService("test-preview-secret", ttl_seconds=60),
    )

    @app.get("/api/dashboard-example/screen-snapshot")
    async def snapshot():
        return {"ok": True}

    @app.post("/api/dashboard-example/screen-snapshot")
    async def post_snapshot():
        return {"ok": True}

    @app.get("/api/private")
    async def private():
        return {"ok": True}

    async def get(path, method="GET"):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path)

    ok = await get("/api/dashboard-example/screen-snapshot?access_token=screen-token-abc")
    assert ok.status_code == 200
    # 错误令牌 401
    wrong = await get("/api/dashboard-example/screen-snapshot?access_token=wrong")
    assert wrong.status_code == 401
    # 令牌只放行配置前缀
    outside = await get("/api/private?access_token=screen-token-abc")
    assert outside.status_code == 401
    # 非 GET 不放行
    post = await get(
        "/api/dashboard-example/screen-snapshot?access_token=screen-token-abc",
        method="POST",
    )
    assert post.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_access_token_disabled_by_default():
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(),
        auth_service=FakeAuthService(),
        share_access=ShareAccessService("test-preview-secret", ttl_seconds=60),
    )

    @app.get("/api/dashboard-example/screen-snapshot")
    async def snapshot():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/dashboard-example/screen-snapshot?access_token=screen-token-abc"
        )
    assert response.status_code == 401
