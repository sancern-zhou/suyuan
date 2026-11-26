"""公司平台账号密码登录（APP 端后端代理）的国密格式与路由契约测试。

国密格式已与 web 前端 JS 实现（sm-crypto / gm-crypt）双向交叉验证：
本文件的 SM3/SM4 参考向量来自 frontend node_modules 真实运行输出，
SM2 密文参考向量来自 android-native CompanyCrypto（APP 端加密）真实运行输出。
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

# android-native CompanyCrypto.encryptSm2Hex 用上面测试公钥的真实运行输出（随机数 k 每次不同，故取定值）；
# sm-crypto doDecrypt 与 gmssl decrypt 均已解回下列明文。同批已知答案向量见 CompanyCryptoTest.kt。
APP_SM2_VECTORS = {
    "zhangsan": (
        "eba11053b3f54206847991c946b7fa5a44a74cf9389205a7bd49d9964259242e4848a5e6ef20e54111c9fc8e2fc0e663"
        "e37f9eff8dd896325d93cc7817141312f3c2ac94f58f187f71299b6d36b0841bbcffdc8f77818514f4c4151d765fbae8"
        "16215deb5d040998"
    ),
    "张三|密码|公司账号": (
        "06217441638f700125928d49b914f031532068f5654dfc73b57eb413fcf369b721a51a3b134b247901a02a7fd4f2bbf8"
        "ae085625ed81b09dafbd95eccc1dce0cccdfe2694adb1ea06ed1ae4757898875bf62e40b51efd70bd6a59472f1826021"
        "caa37db40249cb6a54d7158857e2b0e1599ba572cebab5774342"
    ),
    # 33 字节明文：KDF 跨两个 SM3 块
    "B" * 33: (
        "17fc0755d663b6a0e7c122a529654aacf2c663e6c0c2c98949e16d5737df7ec65642e1593de1bbad4e421ca194bb9072"
        "452dbb70067a03f971da15e219dbd85fe5789e03bdc4b7b3139288e5f411891490c9e724d663f9c7a5b7f83440839dfa"
        "5f0aae8fd200c264034cee834356c6a45b9fe6872c51f30927336e0ac5cee624db"
    ),
}


@pytest.fixture(autouse=True)
def company_platform(monkeypatch):
    """自带平台地址与 SM4 密钥，不依赖部署机 .env（AUTH_SERVICE_URL 未配时路由返回 503）。"""
    monkeypatch.setattr(cpa.settings, "auth_service_url", "https://company-platform.test")
    monkeypatch.setattr(cpa.settings, "company_sm4_secret_key", SM4_KEY)


def test_sm3_matches_web_frontend_vector():
    from gmssl import sm3

    assert sm3.sm3_hash(list(SM3_VECTOR_INPUT.encode())) == SM3_VECTOR_OUTPUT


def test_sm4_cbc_base64_matches_web_frontend_vector():
    assert cpa.encrypt_sm4_base64(SM4_VECTOR_PLAIN) == SM4_VECTOR_CIPHER


def test_app_sm2_ciphertext_decrypts_in_web_wire_format():
    from gmssl import sm2 as gm_sm2

    crypt = gm_sm2.CryptSM2(public_key=SM2_PUBLIC_KEY[2:], private_key=SM2_PRIVATE_KEY, mode=1)
    for plaintext, cipher_hex in APP_SM2_VECTORS.items():
        # 线上格式同 sm-crypto doEncrypt：C1(64B 无 04 前缀) + C3(32B) + C2(明文等长)
        assert len(cipher_hex) == 128 + 64 + 2 * len(plaintext.encode())
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


def _sm2_ciphertext(plaintext: str) -> str:
    """测试密钥对下按线上格式生成的 SM2 密文（明文不落到请求里）。"""
    from gmssl import sm2 as gm_sm2

    crypt = gm_sm2.CryptSM2(public_key=SM2_PUBLIC_KEY[2:], private_key=SM2_PRIVATE_KEY, mode=1)
    return crypt.encrypt(plaintext.encode()).hex()


def _company_login_payload() -> dict:
    return {
        "secret_name": APP_SM2_VECTORS["zhangsan"],
        "secret_code": _sm2_ciphertext("plain-password-不得外传"),
        "verify_code": "1234",
        "captcha_key": "cap-key",
    }


@pytest.mark.asyncio
async def test_company_login_issues_company_identity(monkeypatch):
    monkeypatch.setattr(app_identity.settings, "app_auth_secret", "test-signing-secret")
    payload = _company_login_payload()
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        assert request.url.path.endswith("/auth/token/authentication")
        assert request.headers["SysCode"] == "JCXT"
        assert request.headers["Sign"] and request.headers["encryptType"]
        content = request.content.decode()
        body = json.loads(content)
        assert body["isEncry"] is True and body["isLog"] == "1" and body["logType"] == "5"
        assert body["verifyCode"] == "1234" and body["captchaKey"] == "cap-key"
        # APP 端密文原样转发；明文账号密码不出现在发往平台的请求里
        assert body["secretName"] == payload["secret_name"]
        assert body["secretCode"] == payload["secret_code"]
        assert "zhangsan" not in content and "不得外传" not in content
        return httpx.Response(200, json={"success": True, "result": {"accessToken": "platform-token-1"}})

    _patch_http(monkeypatch, handler)
    auth_service = StubAuthService()
    app = _build_app(auth_service)
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/social/app/auth/company/login", json=payload)
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
            json={**_company_login_payload(), "verify_code": "0000"},
        )
    assert response.status_code == 401
    assert "验证码错误" in response.json()["detail"]


@pytest.mark.asyncio
async def test_company_login_rejects_plaintext_or_malformed_credentials(monkeypatch):
    """只收 APP 端 SM2 密文：明文字段或格式不合法的密文一律 422，且不会打到平台。"""
    platform_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        platform_calls.append(request)
        return httpx.Response(200, json={"success": True, "result": {"accessToken": "platform-token"}})

    _patch_http(monkeypatch, handler)
    app = _build_app(StubAuthService())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    good = _company_login_payload()
    valid = APP_SM2_VECTORS["zhangsan"]
    rejected_bodies = [
        # 明文账号密码（后端不再代为加密）
        {"username": "zhangsan", "password": "secret", "verify_code": "1234", "captcha_key": "cap-key"},
        {**good, "secret_name": "zhangsan"},
        # 非 hex / 奇数位 / 过短（缺 C2）/ 过长
        {**good, "secret_name": valid[:-2] + "zz"},
        {**good, "secret_name": valid[:-1]},
        {**good, "secret_name": valid[:192]},
        {**good, "secret_code": valid + "0" * (2242 - len(valid))},
    ]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for body in rejected_bodies:
            response = await client.post("/api/social/app/auth/company/login", json=body)
            assert response.status_code == 422, body
    assert platform_calls == []


@pytest.mark.asyncio
async def test_company_endpoints_disabled_by_setting(monkeypatch):
    monkeypatch.setattr(settings, "app_company_password_login_enabled", False)
    app = _build_app(StubAuthService())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        captcha = await client.get("/api/social/app/auth/company/captcha")
        login = await client.post("/api/social/app/auth/company/login", json=_company_login_payload())
    assert captcha.status_code == 503 and login.status_code == 503
