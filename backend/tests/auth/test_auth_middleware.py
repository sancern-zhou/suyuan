import httpx
import pytest
from fastapi import FastAPI, Request

from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.models import CurrentUser
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
    )

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/ready")
    async def ready():
        return {"ok": True}

    @app.get("/assets/{path:path}")
    async def asset(path: str):
        return {"path": path}

    @app.get("/api/signed-media/{path:path}")
    async def signed_media(path: str):
        return {"path": path}

    @app.get("/api/reports/share/{token}")
    async def report(token: str):
        return {"token": token}

    @app.get("/api/html-artifacts/share/{token}")
    async def artifact(token: str):
        return {"token": token}

    @app.get("/api/private")
    async def private(request: Request):
        return {
            "id": request.state.current_user.id,
            "is_admin": request.state.current_user.is_admin,
            "user_header": request.headers.get("x-user-id"),
            "admin_header": request.headers.get("x-is-admin"),
        }

    return app, service


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
        "/assets/app.js",
        "/api/signed-media/a/b.png?expires=1&signature=x",
        "/api/reports/share/grant",
        "/api/html-artifacts/share/grant",
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
        "/api/reports/share",
        "/api/reports/share/grant/private",
        "/api/html-artifacts/share/grant/private",
        "/api/signed-media",
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
