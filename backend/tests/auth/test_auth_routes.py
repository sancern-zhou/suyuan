from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.routes import get_auth_settings, router
from config.settings import Settings


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_auth_settings] = lambda: settings
    return TestClient(app)


def test_company_runtime_config_exposes_only_safe_mode_fields():
    settings = Settings(
        _env_file=None,
        auth_mode="company",
        auth_service_url="http://secret-internal-auth/api",
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"authMode": "company", "sysCode": "SUYUAN"}
    assert "secret-internal-auth" not in response.text


def test_mock_runtime_config_returns_the_stable_administrator():
    settings = Settings(
        _env_file=None,
        auth_mode="mock",
        auth_mock_enabled=True,
        auth_mock_user_id="local-developer",
        auth_mock_username="local-developer",
        auth_mock_display_name="本地开发用户",
        auth_mock_role_codes="viewer",
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.status_code == 200
    assert response.json() == {
        "authMode": "mock",
        "sysCode": "SUYUAN",
        "mockUser": {
            "id": "local-developer",
            "userName": "local-developer",
            "name": "本地开发用户",
            "roleCodes": ["SUYUAN_ADMIN", "viewer"],
            "isAdmin": True,
            "sysCode": "SUYUAN",
            "authSource": "mock",
        },
    }


def test_disabled_mock_mode_falls_back_to_company_runtime_behavior():
    settings = Settings(
        _env_file=None,
        auth_mode="mock",
        auth_mock_enabled=False,
    )

    response = _client(settings).get("/api/auth/runtime-config")

    assert response.json() == {"authMode": "company", "sysCode": "SUYUAN"}
