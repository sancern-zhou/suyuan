"""校验统一鉴权平台签发的第三方入口 JWT 与 des 加密串。

入口形态一（getThirdUrl ?token=<HS256 JWT>）：
- 密钥：Base64.getEncoder().encode(JWT_SECRET_KEY 字典 SECRET_KEY 的 UTF-8 字节)
- claims：jti=平台用户ID、sub=登录名、custom=字典 param（#{userName} 替换为用户姓名）、
  exp=签发时间+PHONE_CODE_TOKEN_EXPIRE（默认 120 秒）

入口形态二（dockingThirdUrl/url ?des=<3DES 密文>）：
- 明文：fastjson JSON {"ACCESS_TOKEN": 平台会话令牌, "ACCESS_USER_ID": 用户ID,
  "ACCESS_SYS_CODE": 应用编码, "ACCESS_LOGIN": true}
- 加密：DESede/ECB/PKCS5Padding，密钥=平台内置字串前 24 字节（hutool DESede）
"""

import base64
import hashlib
import hmac
import json
import time

CLOCK_SKEW_SECONDS = 60

# 平台 AuthController /url 内置的对称加密密钥字面量（反汇编确认）
THIRD_PARTY_DES_KEY = "d3b246fdcf3511eba4d6000c29a4d755"


class ThirdPartyJwtError(ValueError):
    """入口 JWT 无效（格式/签名/过期）。"""


class ThirdPartyDesError(ValueError):
    """入口 des 密文无效（格式/解密失败/缺令牌）。"""


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


def decrypt_third_party_des(des_b64: str, key_text: str = THIRD_PARTY_DES_KEY) -> str:
    """解密平台 dockingThirdUrl 生成的 des 参数，返回其中的 accessToken。

    3DESede/ECB/PKCS5Padding，密钥=平台内置字面量前 24 字节（JDK DESede
    对 32 字节密钥按 K1K2K3K1 处理，等价于前 24 字节的标准 3DES）。
    """
    if not des_b64 or not key_text:
        raise ThirdPartyDesError("missing des or key")
    from cryptography.hazmat.primitives import padding as crypto_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    try:
        cipher_text = base64.b64decode(des_b64)
    except (ValueError, base64.binascii.Error) as exc:
        raise ThirdPartyDesError("malformed des base64") from exc
    try:
        key = algorithms.TripleDES(key_text.encode()[:24])
        decryptor = Cipher(key, modes.ECB()).decryptor()
        padded = decryptor.update(cipher_text) + decryptor.finalize()
        unpadder = crypto_padding.PKCS7(64).unpadder()
        plain = unpadder.update(padded) + unpadder.finalize()
    except Exception as exc:  # 密钥/填充不符都会走到这里
        raise ThirdPartyDesError("des decrypt failed") from exc
    try:
        data = json.loads(plain)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ThirdPartyDesError("des payload is not json") from exc
    access_token = str(data.get("ACCESS_TOKEN") or "").strip()
    if not access_token:
        raise ThirdPartyDesError("des payload has no access token")
    return access_token
