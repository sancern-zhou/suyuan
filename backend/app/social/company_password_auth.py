"""公司平台账号密码登录（与 web 前端同协议：图形验证码 + 国密签名）。

web 前端（frontend/src/auth/）在浏览器里直调平台 /api/auth/token/authentication；
APP 端不重复实现国密，由后端代理同一协议。加密格式已与前端 JS 实现
（sm-crypto / gm-crypt）双向交叉验证：
- SM2 公钥加密：C1C3C2、无 04 前缀 hex（gmssl CryptSM2 mode=1 原生一致）
- SM4-CBC（PKCS7）base64，key 与 iv 相同
- Sign 头：sm3("{path},{timestamp_ms},{token}") 后拼
  "{digest},{timestamp},{token},{uuid}" 再整体 SM4 加密
"""

from __future__ import annotations

import base64
import random
import time
import uuid
from typing import Any

import httpx
from fastapi import HTTPException
from gmssl import sm2 as gm_sm2
from gmssl import sm3 as gm_sm3
from gmssl import sm4 as gm_sm4

from app.auth.models import CurrentUser
from config.settings import settings


def _sm4_cipher() -> tuple[gm_sm4.CryptSM4, bytes]:
    key = settings.company_sm4_secret_key.encode("utf-8")
    if len(key) != 16:
        raise RuntimeError("company_sm4_secret_key must be 16 bytes")
    return gm_sm4.CryptSM4(), key


def encrypt_sm4_base64(value: str) -> str:
    cipher, key = _sm4_cipher()
    cipher.set_key(key, gm_sm4.SM4_ENCRYPT)
    return base64.b64encode(cipher.crypt_cbc(key, value.encode("utf-8"))).decode("ascii")


def encrypt_sm2_hex(value: str) -> str:
    public_key = settings.company_sm2_public_key.strip()
    if public_key.startswith("04"):
        public_key = public_key[2:]
    if len(public_key) != 128:
        raise RuntimeError("company_sm2_public_key must be 65-byte uncompressed hex (04…)")
    crypt = gm_sm2.CryptSM2(public_key=public_key, private_key="", mode=1)
    encrypted = crypt.encrypt(value.encode("utf-8"))
    return encrypted.hex()


def build_sign(path: str, token: str = "", *, timestamp: str | None = None, nonce: str | None = None) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    ts = timestamp or str(int(time.time() * 1000))
    digest = gm_sm3.sm3_hash(list(f"{normalized_path},{ts},{token}".encode("utf-8")))
    return encrypt_sm4_base64(f"{digest},{ts},{token or ''},{nonce or uuid.uuid4()}")


def build_request_headers(path: str, token: str = "") -> dict[str, str]:
    return {
        "Sign": build_sign(path, token),
        "encryptType": encrypt_sm4_base64("SM2"),
        "Content-Type": "application/json;charset=UTF-8",
    }


def new_captcha_challenge(previous_key: str = "") -> dict[str, Any]:
    """镜像 web 前端 createCaptchaChallenge：客户端生成 key，type 在 1/3 中随机。"""
    return {
        "key": str(uuid.uuid4()),
        "old_key": previous_key,
        "type": str(random.choice((1, 3))),
    }


def captcha_url(challenge: dict[str, Any]) -> str:
    base = settings.auth_service_url.rstrip("/")
    return (
        f"{base}/auth/token/captcha"
        f"?oldKey={challenge['old_key']}&key={challenge['key']}&type={challenge['type']}&d={int(time.time() * 1000)}"
    )


async def fetch_company_captcha(client: httpx.AsyncClient, previous_key: str = "") -> dict[str, Any]:
    challenge = new_captcha_challenge(previous_key)
    response = await client.get(captcha_url(challenge))
    if response.status_code != 200 or not response.content:
        raise HTTPException(status_code=503, detail="company_captcha_unavailable")
    return {
        "captcha_key": challenge["key"],
        "image_base64": base64.b64encode(response.content).decode("ascii"),
        "content_type": response.headers.get("content-type", "image/png"),
    }


def _parse_access_token(body: dict[str, Any]) -> str:
    result = body.get("result")
    if not isinstance(result, dict):
        return ""
    token = str(result.get("accessToken") or result.get("access_token") or "").strip()
    return token


async def login_company_user(
    client: httpx.AsyncClient,
    *,
    username: str,
    password: str,
    verify_code: str,
    captcha_key: str,
) -> str:
    """平台账号密码登录，返回平台 accessToken；拒绝时透出平台 msg。"""
    if not settings.auth_service_url.strip():
        raise HTTPException(status_code=503, detail="company_auth_not_configured")
    path = "/auth/token/authentication"
    form = {
        "secretName": encrypt_sm2_hex(username.strip()),
        "secretCode": encrypt_sm2_hex(password),
        "isEncry": True,
        "verifyCode": verify_code.strip(),
        "captchaKey": captcha_key.strip(),
        "isLog": "1",
        "logType": "5",
    }
    headers = build_request_headers(path)
    headers["SysCode"] = settings.auth_platform_sys_code
    response = await client.post(f"{settings.auth_service_url.rstrip('/')}{path}", json=form, headers=headers)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400 or body.get("success") is False or not _parse_access_token(body):
        message = str(body.get("msg") or body.get("message") or "").strip() or "账号或密码错误"
        raise HTTPException(status_code=401, detail=f"company_login_rejected:{message}")
    return _parse_access_token(body)


def app_identity_from_current_user(user: CurrentUser) -> dict[str, Any]:
    """把平台解析出的 CurrentUser 映射为 APP company 身份字段（与 OIDC 路径同构）。"""
    return {
        "account_id": user.id,
        "display_name": user.display_name,
        "social_user_id": f"company:{user.id}",
        "expires_at": 0,
        "auth_source": "company",
        "username": user.username,
        "sys_code": user.sys_code or settings.auth_sys_code,
        "role_codes": user.role_codes,
    }
