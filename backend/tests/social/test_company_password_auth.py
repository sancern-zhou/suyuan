"""公司平台账号密码登录（APP 端后端代理）的国密格式与路由契约测试。

国密格式已与 web 前端 JS 实现（sm-crypto / gm-crypt）双向交叉验证：
本文件的参考向量来自 frontend node_modules 真实运行输出。
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from app.social import app_identity, company_password_auth as cpa
from app.api.social_app_routes import router as app_router
from app.auth.models import CurrentUser
from config.settings import settings

# —— 与 frontend/src/auth 一致的参考向量（node + sm-crypto/gm-crypt 生成） ——
SM4_KEY = "GJwsXX_BzW=gJWJW"
SM3_VECTOR_INPUT = "/auth/token/authentication,1764130000000,platform-token"
SM3_VECTOR_OUTPUT = "3dacdbc60b64bfada72b732aac4f3679019a2b4b85e97b797b0ae5dc552e2860"
SM4_VECTOR_PLAIN = "digest,1764130000000,platform-token,uuid-1234"
SM4_VECTOR_CIPHER = "KGzDMw0xwAl4wYQ8uyR8NGeuxYsoyA18Miz58btOHMXVpZ0l+vho8DXxuimiFFQN"

# node sm-crypto generateKeyPairHex 生成的测试密钥对（非平台真实密钥）
SM2_PUBLIC_KEY = "040a59760d53fefaea09b0e3668c0b0e99b7901a79ea618264fb3a6562d0ea685ce25a7557c340af784daee365b446f680c6375878ebe87b14c5f5c6d2dfc7b03c"
SM2_PRIVATE_KEY = "6552d4149d98f355d7774f97a2a211a0bebf76f8028682d484a89ce84eb5bbbc"


@pytest.fixture(autouse=True)
def sm_keys(monkeypatch):
    monkeypatch.setattr(cpa.settings, "company_sm4_secret_key", SM4_KEY)
    monkeypatch.setattr(cpa.settings, "company_sm2_public_key", SM2_PUBLIC_KEY)


def test_sm3_matches_web_frontend_vector():
    from gmssl import sm3

    assert sm3.sm3_hash(list(SM3_VECTOR_INPUT.encode())) == SM3_VECTOR_OUTPUT


def test_sm4_cbc_base64_matches_web_frontend_vector():
    assert cpa.encrypt_sm4_base64(SM4_VECTOR_PLAIN) == SM4_VECTOR_CIPHER


def test_sm2_encrypt_matches_js_wire_format_roundtrip():
    from gmssl import sm2 as gm_sm2

    plaintext = "zhangsan|密码|公司账号"
    cipher_hex = cpa.encrypt_sm2_hex(plaintext)
    # sm-crypto doEncrypt 输出：C1(64B 无 04 前缀) + C3(32B) + C2(明文等长)
    assert len(cipher_hex) == 128 + 64 + 2 * len(plaintext.encode())
    assert not cipher_hex.startswith("04")
    crypt = gm_sm2.CryptSM2(public_key=SM2_PUBLIC_KEY[2:], private_key=SM2_PRIVATE_KEY, mode=1)
    assert crypt.decrypt(bytes.fromhex(cipher_hex)).decode() == plaintext


def test_build_sign_is_deterministic_and_wraps_sm3_digest():
    sign = cpa.build_sign("/auth/token/authentication", "platform-token", timestamp="1764130000000", nonce="uuid-1234")
    expected = cpa.encrypt_sm4_base64(f"{SM3_VECTOR_OUTPUT},1764130000000,platform-token,uuid-1234")
    assert sign == expected
    headers = cpa.build_request_headers("/auth/token/authentication")
    assert headers["encryptType"] == cpa.encrypt_sm4_base64("SM2")
    assert headers["Sign"]


def _patch_http(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        if kwargs.get("transport") is not None:
            # 测试外层的 ASGI client 原样放行，只拦截路由内新建的平台调用 client。
            return real_client(**kwargs)
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs.setdefault("timeout", 5)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_fetch_company_captcha_returns_image(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"pngbytes", headers={"content-type": "image/png"})

    _patch_http(monkeypatch, handler)
    payload = await cpa.fetch_company_captcha(httpx.AsyncClient())
    assert payload["image_base64"] == "cG5nYnl0ZXM="
    assert payload["content_type"] == "image/png"
    assert len(payload["captcha_key"]) >= 32
    assert "auth/token/captcha" in seen["url"]
    assert "type=1" in seen["url"] or "type=3" in seen["url"]


class StubAuthService:
    def __init__(self):
        self.calls = []

    async def authenticate(self, token: str, sys_code: str):
        self.calls.append((token, sys_code))
        return CurrentUser(
            id="u-1", username="zhangsan", display_name="张三", role_codes=("agent.user",), sys_code="SUYUAN"
        )


def _build_app(auth_service):
    app = FastAPI()
    app.include_router(app_router)
    app.state.auth_service = auth_service
    return app


@pytest.mark.asyncio
async def test_company_login_issues_company_identity(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        assert request.url.path.endswith("/auth/token/authentication")
        assert request.headers["SysCode"] == "JCXT"
        assert request.headers["Sign"] and request.headers["encryptType"]
        body = json.loads(request.content.decode())
        assert body["isEncry"] is True and body["isLog"] == "1" and body["logType"] == "5"
        assert body["verifyCode"] == "1234" and body["captchaKey"] == "cap-key"
        assert isinstance(body["secretName"], str) and isinstance(body["secretCode"], str)
        return httpx.Response(200, json={"success": True, "result": {"accessToken": "platform-token-1"}})

    _patch_http(monkeypatch, handler)
    auth_service = StubAuthService()
    app = _build_app(auth_service)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/social/app/auth/company/login",
            json={"username": "zhangsan", "password": "secret", "verify_code": "1234", "captcha_key": "cap-key"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == "u-1"
    assert body["social_user_id"] == "company:u-1"
    assert body["display_name"] == "张三"
    assert auth_service.calls == [("platform-token-1", settings.auth_sys_code)]
    # company 身份的角色码应可从签发的 access token 解回（身份匹配与守卫依赖）
    resolved = app_identity.resolve_access_token(body["access_token"])
    assert resolved.role_codes == ("agent.user",)
    assert resolved.as_current_user().auth_source == "company"


@pytest.mark.asyncio
async def test_company_login_rejection_surfaces_platform_message(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False, "msg": "验证码错误"})

    _patch_http(monkeypatch, handler)
    app = _build_app(StubAuthService())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/social/app/auth/company/login",
            json={"username": "zhangsan", "password": "secret", "verify_code": "0000", "captcha_key": "cap-key"},
        )
    assert response.status_code == 401
    assert "验证码错误" in response.json()["detail"]


@pytest.mark.asyncio
async def test_company_endpoints_disabled_by_setting(monkeypatch):
    monkeypatch.setattr(settings, "app_company_password_login_enabled", False)
    app = _build_app(StubAuthService())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        captcha = await client.get("/api/social/app/auth/company/captcha")
        login = await client.post(
            "/api/social/app/auth/company/login",
            json={"username": "u", "password": "p", "verify_code": "1", "captcha_key": "k"},
        )
    assert captcha.status_code == 503 and login.status_code == 503
