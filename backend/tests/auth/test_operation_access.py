"""Unit tests for the operation-platform roster access policy and its
enforcement at the gateway middleware and the operation-session route."""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth.middleware import GatewayAuthenticationMiddleware
from app.auth.models import CurrentUser
from app.auth.operation_access import OperationAccessPolicy
from app.auth.routes import (
    get_auth_service,
    get_auth_settings,
    get_operation_access_policy,
    require_admin_user,
    router,
)
from config.settings import Settings


def _settings(**overrides):
    values = {
        "_env_file": None,
        "auth_mode": "operation",
        "auth_sys_code": "SUYUAN",
        "trusted_gateway_networks": "127.0.0.1/32",
        "auth_operation_access_control_enabled": True,
        "auth_operation_allowed_usertypes": "1,5",
        "auth_operation_admin_usernames": "admin01",
    }
    values.update(overrides)
    return Settings(**values)


def _row(login, name=None, usertype="3", status="Enabled", dept="某运维公司", data_state="1"):
    return {
        "LOGINID": login,
        "USERNAME": name or login,
        "USERTYPE": usertype,
        "STATUS": status,
        "DATASTATE": data_state,
        "DEPARTMENT": dept,
        "MAINTENANCE_UNIT": dept,
        "ROLE_NAMES": "评价网运维成员",
    }


def _roster():
    return [
        _row("zhangsan", "张三", usertype="1", dept="监测二室"),
        _row("lishi", "李四", usertype="5", dept="地市级"),
        _row("opscomp", "运维小王", usertype="3"),
        _row("reviewer", "复审账号", usertype="6"),
    ]


def _throwaway_snapshot():
    """Isolated snapshot path so tests never touch the real data registry."""
    base = Path(tempfile.gettempdir()) / "operation_access_tests"
    return base / f"{uuid.uuid4().hex}.json"


def _policy(rows=None, snapshot_path=None, **overrides):
    return OperationAccessPolicy(
        settings=_settings(**overrides),
        snapshot_path=snapshot_path or _throwaway_snapshot(),
        fetch_roster=lambda: rows if rows is not None else _roster(),
    )


# ---------------------------------------------------------------------------
# Policy decisions


def test_bureau_usertypes_allowed_and_external_blocked():
    policy = _policy()
    policy.apply_roster(_roster())

    assert policy.decide("zhangsan") == (True, "bureau_usertype")
    assert policy.decide("lishi") == (True, "bureau_usertype")
    assert policy.decide("opscomp") == (False, "external_usertype")
    assert policy.decide("reviewer") == (False, "external_usertype")


def test_display_name_alias_resolves_to_same_entry():
    policy = _policy()
    policy.apply_roster(_roster())

    assert policy.decide("运维小王") == (False, "external_usertype")
    assert policy.decide("张三") == (True, "bureau_usertype")


def test_display_name_never_shadows_another_accounts_login():
    rows = [
        _row("czj", "陈梓杰", usertype="3", dept="202805科迪隆"),
        _row("陈梓杰", "陈梓杰（省中心）", usertype="1", dept="监测二室"),
    ]
    for order in (rows, list(reversed(rows))):
        policy = _policy()
        policy.apply_roster(order)

        assert policy.decide("czj") == (False, "external_usertype")
        assert policy.decide("陈梓杰") == (True, "bureau_usertype")


def test_duplicate_login_prefers_the_live_bureau_record():
    dead_external = _row("zyy", "张媛媛", usertype="2", status="Disabled", data_state="-1")
    superseded_bureau = _row("zyy", "张媛媛", usertype="1", dept="监测二室", data_state="-1")
    live_bureau = _row("zyy", "张媛媛", usertype="1", dept="监测中心")

    for order in (
        [dead_external, superseded_bureau, live_bureau],
        [live_bureau, dead_external, superseded_bureau],
    ):
        policy = _policy()
        policy.apply_roster(order)

        assert policy.decide("zyy") == (True, "bureau_usertype")


def test_duplicate_login_live_external_record_still_blocks():
    superseded_bureau = _row("xws", "肖文梭", usertype="4", data_state="-1")
    live_external = _row("xws", "肖文梭", usertype="3", dept="某某运维")

    for order in ([superseded_bureau, live_external], [live_external, superseded_bureau]):
        policy = _policy()
        policy.apply_roster(order)

        assert policy.decide("xws") == (False, "external_usertype")


def test_static_whitelist_and_admin_override_roster():
    policy = _policy(auth_operation_allowed_usernames="opscomp")
    policy.apply_roster(_roster())

    assert policy.decide("opscomp") == (True, "static_whitelist")
    assert policy.decide("admin01") == (True, "static_whitelist")
    assert policy.decide("Admin01") == (True, "static_whitelist")


def test_blocked_list_overrides_whitelist():
    policy = _policy(
        auth_operation_allowed_usernames="opscomp",
        auth_operation_blocked_usernames="opscomp,zhangsan",
    )
    policy.apply_roster(_roster())

    assert policy.decide("opscomp") == (False, "blocked_list")
    assert policy.decide("zhangsan") == (False, "blocked_list")


def test_unknown_user_fails_open_before_first_roster_and_denied_after():
    policy = OperationAccessPolicy(
        settings=_settings(),
        snapshot_path=_throwaway_snapshot(),
        fetch_roster=lambda: [],
    )

    assert policy.decide("ghost") == (True, "roster_unavailable")

    policy.apply_roster(_roster())
    assert policy.decide("ghost") == (False, "unknown_user")


def test_summary_counts_and_roster_state():
    policy = _policy()
    summary = policy.summary()
    assert summary["roster_loaded"] is False

    policy.apply_roster(_roster())
    summary = policy.summary()
    assert summary["roster_loaded"] is True
    assert summary["counts"] == {"total": 4, "allowed": 2, "blocked": 2}
    assert summary["synced_at"] is not None


def test_snapshot_round_trip_denies_unknown_users_after_reload(tmp_path):
    snapshot = tmp_path / "roster.json"
    first = OperationAccessPolicy(
        settings=_settings(),
        snapshot_path=snapshot,
        fetch_roster=lambda: _roster(),
    )
    first.apply_roster(_roster())
    assert snapshot.is_file()
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert len(payload["entries"]) == 4

    def _must_not_fetch():
        raise AssertionError("reload must serve from the snapshot")

    second = OperationAccessPolicy(
        settings=_settings(),
        snapshot_path=snapshot,
        fetch_roster=_must_not_fetch,
    )

    assert second.decide("zhangsan") == (True, "bureau_usertype")
    assert second.decide("ghost") == (False, "unknown_user")


def test_refresh_failure_keeps_last_roster():
    policy = _policy()
    policy.apply_roster(_roster())

    def _boom():
        raise RuntimeError("ops db down")

    policy._fetch_roster = _boom

    assert asyncio.run(policy.refresh()) is False
    assert policy._last_error is not None
    assert policy.decide("opscomp") == (False, "external_usertype")


def test_fetch_without_ops_config_is_reported_not_fatal():
    policy = OperationAccessPolicy(
        settings=_settings(ops_sqlserver_host=""),
        snapshot_path=_throwaway_snapshot(),
        fetch_roster=None,
    )

    assert asyncio.run(policy.refresh()) is False
    assert policy.decide("anyone") == (True, "roster_unavailable")


# ---------------------------------------------------------------------------
# Middleware enforcement


class FakeOperationAuthService:
    def __init__(self, cookie_user=None, token_user=None):
        self.cookie_user = cookie_user
        self.token_user = token_user
        self.authenticate_calls = []

    def resolve_session_token(self, raw):
        return self.token_user if raw == "session-token" else None

    async def authenticate(self, token, sys_code):
        self.authenticate_calls.append((token, sys_code))
        return self.cookie_user

    async def close(self):
        return None


def _operation_user(username, auth_source="operation"):
    return CurrentUser(
        id=f"ops-{username}",
        username=username,
        display_name=username,
        sys_code="SUYUAN",
        auth_source=auth_source,
    )


def _operation_app(service, policy):
    app = FastAPI()
    app.add_middleware(
        GatewayAuthenticationMiddleware,
        settings=_settings(),
        auth_service=service,
        share_access=None,
        access_policy=policy,
    )

    @app.get("/api/private")
    async def private(request: Request):
        return {"user": request.state.current_user.username}

    return app


async def _get(app, path, *, headers=None):
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers)


@pytest.mark.asyncio
async def test_blocked_account_is_denied_on_session_token_path():
    policy = _policy()
    policy.apply_roster(_roster())
    service = FakeOperationAuthService(
        token_user=_operation_user("opscomp")
    )
    app = _operation_app(service, policy)

    response = await _get(app, "/api/private", headers={
        "Authorization": "Bearer session-token",
    })

    assert response.status_code == 403
    assert response.json() == {"detail": "operation_account_blocked"}


@pytest.mark.asyncio
async def test_bureau_account_passes_on_session_token_path():
    policy = _policy()
    policy.apply_roster(_roster())
    service = FakeOperationAuthService(
        token_user=_operation_user("zhangsan")
    )
    app = _operation_app(service, policy)

    response = await _get(app, "/api/private", headers={
        "Authorization": "Bearer session-token",
    })

    assert response.status_code == 200
    assert response.json() == {"user": "zhangsan"}


@pytest.mark.asyncio
async def test_blocked_account_is_denied_on_cookie_path():
    policy = _policy()
    policy.apply_roster(_roster())
    service = FakeOperationAuthService(cookie_user=_operation_user("opscomp"))
    app = _operation_app(service, policy)

    response = await _get(app, "/api/private", headers={
        "Authorization": "Bearer unrecognized-token",
        "Cookie": "GDOperation=cookie-value",
    })

    assert response.status_code == 403
    assert response.json() == {"detail": "operation_account_blocked"}
    assert service.authenticate_calls


@pytest.mark.asyncio
async def test_company_source_identity_is_not_subject_to_roster():
    policy = _policy()
    policy.apply_roster(_roster())
    service = FakeOperationAuthService(token_user=_operation_user(
        "opscomp", auth_source="company"
    ))
    app = _operation_app(service, policy)

    response = await _get(app, "/api/private", headers={
        "Authorization": "Bearer session-token",
    })

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Operation-session route


class RouteAuthService(FakeOperationAuthService):
    def resolve_session_token(self, raw):
        return None


def _route_app(settings, service, policy):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_auth_settings] = lambda: settings
    app.dependency_overrides[get_auth_service] = lambda: service
    app.state.operation_access_policy = policy
    return app


def test_operation_session_returns_403_with_message_for_blocked_account():
    policy = _policy()
    policy.apply_roster(_roster())
    service = RouteAuthService(cookie_user=_operation_user("opscomp"))
    app = _route_app(_settings(), service, policy)

    response = TestClient(app).post(
        "/api/auth/operation-session",
        cookies={"GDOperation": "cookie-value"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "operation_account_blocked"
    assert "无权访问" in body["message"]


def test_operation_session_allows_bureau_account():
    policy = _policy()
    policy.apply_roster(_roster())
    service = RouteAuthService(cookie_user=_operation_user("zhangsan"))
    app = _route_app(_settings(), service, policy)

    response = TestClient(app).post(
        "/api/auth/operation-session",
        cookies={"GDOperation": "cookie-value"},
    )

    assert response.status_code == 200
    assert response.json()["authenticated"] is True


# ---------------------------------------------------------------------------
# Admin inspection endpoint


def _admin_app(policy):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    admin = CurrentUser(
        id="ops-admin01",
        username="admin01",
        display_name="管理员",
        sys_code="SUYUAN",
        auth_source="operation",
        is_admin=True,
    )
    app.dependency_overrides[require_admin_user] = lambda: admin
    app.state.operation_access_policy = policy
    return app


def test_operation_access_endpoint_reports_disabled_without_policy():
    app = _admin_app(None)
    response = TestClient(app).get("/api/auth/operation-access")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_operation_access_endpoint_exposes_summary():
    policy = _policy()
    policy.apply_roster(_roster())
    app = _admin_app(policy)

    response = TestClient(app).get("/api/auth/operation-access")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["counts"]["total"] == 4
    assert any(entry["login_id"] == "opscomp" for entry in body["entries"])
