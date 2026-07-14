import json

import httpx
import pytest

from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.platform_client import PlatformAuthClient


class RecordingLogger:
    def __init__(self):
        self.events = []

    def info(self, event, **values):
        self.events.append(("info", event, values))

    def warning(self, event, **values):
        self.events.append(("warning", event, values))


@pytest.mark.asyncio
async def test_current_user_forwards_company_headers_and_maps_admin_role():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "state": 200,
                "success": True,
                "result": {
                    "id": "user-1",
                    "userName": "zhangsan",
                    "name": "张三",
                    "roles": [{"code": "SUYUAN_ADMIN"}, {"code": "viewer"}],
                },
            },
        )

    client = PlatformAuthClient(
        base_url="http://platform-gateway/api",
        current_user_path="/auth/account/getCurrentUser",
        admin_role_codes={"SUYUAN_ADMIN"},
        transport=httpx.MockTransport(handler),
    )

    user = await client.get_current_user("company-token", "SUYUAN")
    await client.close()

    assert seen["headers"]["authorization"] == "Bearer company-token"
    assert seen["headers"]["syscode"] == "SUYUAN"
    assert seen["params"] == {"isLog": "1", "logType": "4"}
    assert user.id == "user-1"
    assert user.username == "zhangsan"
    assert user.display_name == "张三"
    assert user.role_codes == ("SUYUAN_ADMIN", "viewer")
    assert user.is_admin is True
    assert user.auth_source == "company"


@pytest.mark.asyncio
async def test_role_codes_accept_supported_company_shapes_and_deduplicate():
    responses = [
        {"roleCodes": ["viewer", "viewer", "editor"]},
        {"roleList": [{"roleCode": "operator"}, "auditor"]},
    ]

    for role_fields, expected in zip(
        responses,
        [("viewer", "editor"), ("operator", "auditor")],
    ):
        payload = {"id": "u1", "userName": "user", "name": "User", **role_fields}
        transport = httpx.MockTransport(
            lambda request, payload=payload: httpx.Response(
                200,
                json={"state": 200, "result": payload},
            )
        )
        client = PlatformAuthClient(
            base_url="http://auth",
            current_user_path="/current",
            admin_role_codes=set(),
            transport=transport,
        )

        user = await client.get_current_user("token", "SUYUAN")
        await client.close()

        assert user.role_codes == expected
        assert user.is_admin is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"detail": "expired"}),
        httpx.Response(200, json={"state": 100, "msg": "登录过期"}),
        httpx.Response(200, json={"state": 403, "msg": "未授权"}),
    ],
)
async def test_authentication_rejection_has_a_stable_error(response):
    client = PlatformAuthClient(
        base_url="http://auth",
        current_user_path="/current",
        admin_role_codes=set(),
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(AuthenticationRejected, match="company authentication rejected"):
        await client.get_current_user("expired-token", "SUYUAN")
    await client.close()


@pytest.mark.asyncio
async def test_missing_user_id_is_rejected():
    client = PlatformAuthClient(
        base_url="http://auth",
        current_user_path="/current",
        admin_role_codes=set(),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"state": 200, "result": {"userName": "missing-id"}},
            )
        ),
    )

    with pytest.raises(AuthenticationRejected, match="missing user id"):
        await client.get_current_user("token", "SUYUAN")
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(503, json={"detail": "unavailable"}),
        lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout")),
    ],
)
async def test_transport_and_server_failures_are_unavailable(handler):
    client = PlatformAuthClient(
        base_url="http://auth",
        current_user_path="/current",
        admin_role_codes=set(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AuthenticationUnavailable, match="company authentication unavailable"):
        await client.get_current_user("token", "SUYUAN")
    await client.close()


@pytest.mark.asyncio
async def test_logs_contain_only_token_fingerprint():
    logger = RecordingLogger()
    token = "complete-secret-company-token"
    client = PlatformAuthClient(
        base_url="http://auth",
        current_user_path="/current",
        admin_role_codes=set(),
        logger=logger,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"state": 200, "result": {"id": "u1", "userName": "user"}},
            )
        ),
    )

    await client.get_current_user(token, "SUYUAN")
    await client.close()

    serialized = json.dumps(logger.events, ensure_ascii=False)
    assert token not in serialized
    assert "token_fingerprint" in serialized
