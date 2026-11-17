import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.sso import SsoSessionStore, SsoTicketService
from app.auth.sso_routes import get_auth_settings, router
from config.settings import Settings


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def setex(self, key, ttl, value):
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)


def _client(**overrides) -> TestClient:
    values = {
        "_env_file": None,
        "auth_mode": "company",
        "sso_shared_secret": "sso-secret",
        "sso_default_roles": "viewer",
        "auth_admin_role_codes": "SUYUAN_ADMIN",
    }
    values.update(overrides)
    settings = Settings(**values)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_auth_settings] = lambda: settings
    app.state.sso_session_store = SsoSessionStore(
        FakeRedis(), key_prefix="test:", ttl_seconds=600
    )
    return TestClient(app)


def _ticket(claims, secret="sso-secret"):
    return SsoTicketService(secret, ttl_seconds=60).issue(claims)


def test_config_reports_enabled_and_sys_code():
    response = _client().get("/api/auth/sso/config")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"enabled": True, "sysCode": "SUYUAN"}


def test_exchange_disabled_without_shared_secret():
    response = _client(sso_shared_secret="").post(
        "/api/auth/sso/exchange", json={"ticket": "anything"}
    )

    assert response.status_code == 404


def test_exchange_issues_a_local_session_from_signed_claims():
    client = _client()
    ticket = _ticket({"u": "u1", "n": "zhangsan", "r": ["SUYUAN_ADMIN"]})

    response = client.post("/api/auth/sso/exchange", json={"ticket": ticket})

    assert response.status_code == 200
    body = response.json()
    assert body["sysCode"] == "SUYUAN"
    assert body["expiresIn"] == 600
    assert body["user"] == {
        "id": "u1",
        "userName": "zhangsan",
        "name": "zhangsan",
        "roleCodes": ["SUYUAN_ADMIN"],
        "isAdmin": True,
        "sysCode": "SUYUAN",
        "authSource": "company",
    }
    assert body["token"]
    assert ticket not in response.text


def test_exchange_applies_default_roles_when_ticket_has_none():
    client = _client()

    response = client.post("/api/auth/sso/exchange", json={"ticket": _ticket({"u": "u2"})})

    assert response.status_code == 200
    assert response.json()["user"]["roleCodes"] == ["viewer"]
    assert response.json()["user"]["isAdmin"] is False


@pytest.mark.parametrize(
    "ticket",
    [
        "",
        "not-a-ticket",
        _ticket({"u": "u1"}, secret="another-secret"),
    ],
)
def test_exchange_rejects_invalid_tickets(ticket):
    response = _client().post("/api/auth/sso/exchange", json={"ticket": ticket})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_sso_ticket"


def test_exchange_rejects_a_replayed_ticket():
    client = _client()
    ticket = _ticket({"u": "u1"})

    assert client.post("/api/auth/sso/exchange", json={"ticket": ticket}).status_code == 200
    replay = client.post("/api/auth/sso/exchange", json={"ticket": ticket})

    assert replay.status_code == 401
    assert replay.json()["detail"] == "sso_ticket_replayed"
