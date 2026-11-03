"""校验统一鉴权平台签发的第三方入口 JWT。

平台 getThirdUrl 生成的访问地址形如 <子系统URL>?token=<HS256 JWT>：
- 密钥：Base64.getEncoder().encode(JWT_SECRET_KEY 字典 SECRET_KEY 的 UTF-8 字节)
- claims：jti=平台用户ID、sub=登录名、custom=字典 param（#{userName} 替换为用户姓名）、
  exp=签发时间+PHONE_CODE_TOKEN_EXPIRE（默认 120 秒）
"""

import base64
import hashlib
import hmac
import json
import time

CLOCK_SKEW_SECONDS = 60


class ThirdPartyJwtError(ValueError):
    """入口 JWT 无效（格式/签名/过期）。"""


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def verify_third_party_jwt(token: str, secret: str, *, now: float | None = None) -> str:
    """校验签名与有效期，返回登录名（sub）。非法时抛 ThirdPartyJwtError。"""
    if not token or not secret:
        raise ThirdPartyJwtError("missing token or secret")
    parts = token.split(".")
    if len(parts) != 3:
        raise ThirdPartyJwtError("malformed jwt")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ThirdPartyJwtError("malformed jwt") from exc
    if header.get("alg") != "HS256":
        raise ThirdPartyJwtError("unsupported alg")

    # 平台 JwtUtils：signWith(HS256, Base64.getEncoder().encode(secret.getBytes()))
    key = base64.b64encode(secret.encode())
    expected = hmac.new(key, f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, signature):
        raise ThirdPartyJwtError("invalid signature")

    username = str(payload.get("sub") or "").strip()
    if not username:
        raise ThirdPartyJwtError("missing subject")
    expiration = payload.get("exp")
    current = time.time() if now is None else now
    if isinstance(expiration, (int, float)) and current > expiration + CLOCK_SKEW_SECONDS:
        raise ThirdPartyJwtError("expired")
    return username
