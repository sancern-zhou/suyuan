import httpx
import pytest

from app.auth.errors import AuthenticationRejected, AuthenticationUnavailable
from app.auth.oauth_client import PlatformOAuthClient


def build_client(handler, *, client_id="suyuan-web", client_secret="secret-1"):
    return PlatformOAuthClient(
        base_url="http://platform-gateway/api",
        client_id=client_id,
        client_secret=client_secret,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_exchange_code_sends_contract_params_and_returns_token_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "state": 0,
                "msg": "操作成功",
                "success": True,
                "result": {
                    "accessToken": "access-1",
                    "refreshToken": "refresh-1",
                    "tokenType": "bearer",
                    "scope": "all",
                    "expiresIn": 3600,
                },
            },
        )

    client = build_client(handler)
    result = await client.exchange_code("one-time-code", "http://11.54.200.200:5175/")

    assert result["accessToken"] == "access-1"
    assert result["refreshToken"] == "refresh-1"
    assert result["expiresIn"] == 3600
    assert seen["url"].split("?")[0] == "http://platform-gateway/api/auth/oauth/token"
    assert seen["params"]["client_id"] == "suyuan-web"
    assert seen["params"]["client_secret"] == "secret-1"
    assert seen["params"]["grantType"] == "authorization_code"
    assert seen["params"]["code"] == "one-time-code"
    assert seen["params"]["redirectUri"] == "http://11.54.200.200:5175/"


@pytest.mark.asyncio
async def test_refresh_uses_refresh_token_grant():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "state": 0,
                "success": True,
                "result": {"accessToken": "access-2", "refreshToken": "refresh-2"},
            },
        )

    client = build_client(handler)
    result = await client.refresh("refresh-1")

    assert result["accessToken"] == "access-2"
    assert seen["params"]["grantType"] == "refresh_token"
    assert seen["params"]["refreshToken"] == "refresh-1"


@pytest.mark.asyncio
async def test_platform_rejection_raises_authentication_rejected_with_msg():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": 500, "msg": "回调地址不合法", "result": None, "success": False},
        )

    client = build_client(handler)
    with pytest.raises(AuthenticationRejected) as excinfo:
        await client.exchange_code("bad-code", "http://11.54.200.200:5175/")
    assert "回调地址不合法" in str(excinfo.value)


@pytest.mark.asyncio
async def test_missing_access_token_in_result_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": 0, "success": True, "result": {}})

    client = build_client(handler)
    with pytest.raises(AuthenticationRejected):
        await client.exchange_code("code", "http://11.54.200.200:5175/")


@pytest.mark.asyncio
async def test_transport_failure_raises_authentication_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("platform down")

    client = build_client(handler)
    with pytest.raises(AuthenticationUnavailable):
        await client.exchange_code("code", "http://11.54.200.200:5175/")


def test_configured_requires_both_credentials():
    configured = PlatformOAuthClient(
        base_url="http://platform-gateway/api",
        client_id="id",
        client_secret="secret",
    )
    missing_secret = PlatformOAuthClient(
        base_url="http://platform-gateway/api",
        client_id="id",
        client_secret="",
    )
    assert configured.configured is True
    assert missing_secret.configured is False
