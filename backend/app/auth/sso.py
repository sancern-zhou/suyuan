"""Reuse an external platform's login session through signed one-time tickets.

外部平台（如江西省噪声平台）在用户已登录时，用共享密钥签发一次性票据并跳转
到溯源。溯源在公开端点校验票据、防重放，再签发本系统的短期会话令牌，前端
把它写入既有的 ``Access-Token`` 存储，后续请求走标准网关鉴权链路。

票据两种信任模式：

- ``t``（上游访问令牌）：优先使用。溯源用它在公司/平台认证服务复核身份，
  票据伪造无法越权，因为身份以认证服务返回为准。
- 仅声明（``u``/``n``/``r``）：票据本身由共享密钥 HMAC 签名，双方约定信任。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from .models import CurrentUser


class SsoTicketError(RuntimeError):
    """票据缺失、签名错误、过期或格式非法。"""


class SsoTicketService:
    """HMAC-SHA256 签名的一次性登录票据。"""

    def __init__(self, secret: str, *, ttl_seconds: int) -> None:
        if not secret:
            raise ValueError("sso shared secret is required")
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    def issue(
        self,
        claims: dict[str, Any],
        *,
        now: int | None = None,
        jti: str | None = None,
    ) -> str:
        issued_at = int(time.time()) if now is None else int(now)
        payload = {
            **{key: value for key, value in claims.items() if value not in (None, "", [])},
            "e": issued_at + self.ttl_seconds,
            "j": jti or secrets.token_urlsafe(18),
        }
        encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = _encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def verify(self, ticket: str, *, now: int | None = None) -> dict[str, Any]:
        if not ticket or len(ticket) > 8192:
            raise SsoTicketError("invalid_sso_ticket")
        try:
            encoded, supplied = ticket.split(".", 1)
            expected = _encode(
                hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(expected, supplied):
                raise SsoTicketError("invalid_sso_ticket")
            payload = json.loads(_decode(encoded))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise SsoTicketError("invalid_sso_ticket") from exc
        if not isinstance(payload, dict):
            raise SsoTicketError("invalid_sso_ticket")
        current = int(time.time()) if now is None else int(now)
        try:
            expires_at = int(payload.get("e", 0))
        except (TypeError, ValueError) as exc:
            raise SsoTicketError("invalid_sso_ticket") from exc
        if expires_at < current:
            raise SsoTicketError("sso_ticket_expired")
        if not str(payload.get("j") or "").strip():
            raise SsoTicketError("invalid_sso_ticket")
        if not str(payload.get("t") or payload.get("u") or "").strip():
            raise SsoTicketError("invalid_sso_ticket")
        return payload


class SsoSessionStore:
    """短期本地会话令牌：token 只以 SHA-256 摘要作为 Redis 键。"""

    def __init__(self, redis: Any, *, key_prefix: str, ttl_seconds: int) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def key_for_token(self, token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}sso-session:{digest}"

    def key_for_ticket(self, ticket_id: str) -> str:
        return f"{self._key_prefix}sso-ticket:{ticket_id}"

    async def consume_ticket(self, ticket_id: str) -> bool:
        """一次性消费票据标识；Redis 不可用时拒绝（fail closed）。"""
        try:
            stored = await self._redis.set(
                self.key_for_ticket(ticket_id),
                "1",
                ex=max(self.ttl_seconds, 60),
                nx=True,
            )
        except Exception as exc:
            raise SsoTicketError("sso_replay_guard_unavailable") from exc
        return bool(stored)

    async def issue(self, user: CurrentUser) -> str:
        token = secrets.token_urlsafe(32)
        try:
            await self._redis.setex(
                self.key_for_token(token), self.ttl_seconds, user.model_dump_json()
            )
        except Exception as exc:
            raise SsoTicketError("sso_session_unavailable") from exc
        return token

    async def get(self, token: str) -> CurrentUser | None:
        try:
            value = await self._redis.get(self.key_for_token(token))
        except Exception:
            return None
        if value is None:
            return None
        try:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return CurrentUser.model_validate_json(value)
        except (ValueError, TypeError, UnicodeDecodeError):
            return None


def build_sso_user(
    claims: dict[str, Any],
    *,
    default_roles: set[str],
    admin_role_codes: set[str],
    sys_code: str,
) -> CurrentUser:
    user_id = str(claims.get("u") or "").strip()
    if not user_id:
        raise SsoTicketError("invalid_sso_ticket")
    username = str(claims.get("n") or user_id).strip() or user_id
    display_name = str(claims.get("d") or username).strip() or username
    raw_roles = claims.get("r")
    roles: list[str] = []
    if isinstance(raw_roles, list):
        for item in raw_roles:
            code = str(item).strip()
            if code and code not in roles:
                roles.append(code)
    if not roles:
        roles = sorted(default_roles)
    return CurrentUser(
        id=user_id,
        username=username,
        display_name=display_name,
        role_codes=tuple(roles),
        is_admin=bool(set(roles).intersection(admin_role_codes)),
        sys_code=sys_code,
        auth_source="company",
    )


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
