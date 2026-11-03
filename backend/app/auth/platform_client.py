"""Secret-safe HTTP client for the company authentication service."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
import structlog

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser


_REJECTED_STATES = {100, 130, 131, 132, 133, 134, 401, 403}
_SUCCESS_STATES = {0, 200}


class PlatformAuthClient:
    """Resolve a Bearer token through the existing company auth service."""

    def __init__(
        self,
        *,
        base_url: str,
        current_user_path: str,
        admin_role_codes: set[str],
        platform_sys_code: str = "JCXT",
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: Any | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/{current_user_path.lstrip('/')}"
        self._admin_role_codes = set(admin_role_codes)
        self._platform_sys_code = platform_sys_code
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)
        self._logger = logger or structlog.get_logger(__name__)

    async def get_current_user(self, token: str, sys_code: str) -> CurrentUser:
        fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        self._logger.info(
            "company_auth_lookup_started",
            token_fingerprint=fingerprint,
            sys_code=self._platform_sys_code,
        )
        status, body = await self._fetch(token, self._platform_sys_code, fingerprint)
        # OAuth2.0 授权码换来的 token 绑定业务应用自身，平台要求 SysCode 头等于
        # 业务应用编码；用平台编码(JCXT)查询会得到 403 "未授权的应用访问"(state=131)，
        # 此时以业务编码重试一次（如 SUYUAN）。
        if (
            _is_unregistered_app(body)
            and sys_code
            and sys_code != self._platform_sys_code
        ):
            self._logger.info(
                "company_auth_lookup_retry_business_syscode",
                token_fingerprint=fingerprint,
                sys_code=sys_code,
            )
            status, body = await self._fetch(token, sys_code, fingerprint)

        if status in {401, 403} or 400 <= status < 500:
            raise AuthenticationRejected("company authentication rejected")

        state = _normalized_state(body.get("state")) if body else None
        if body is None:
            raise AuthenticationUnavailable("company authentication unavailable")
        if state in _REJECTED_STATES or body.get("success") is False:
            raise AuthenticationRejected("company authentication rejected")
        if state is not None and state not in _SUCCESS_STATES:
            raise AuthenticationRejected("company authentication rejected")

        payload = body.get("result")
        if not isinstance(payload, dict):
            raise AuthenticationRejected("company authentication rejected: missing user id")
        user = CurrentUser.from_company_payload(
            payload,
            admin_role_codes=self._admin_role_codes,
            sys_code=sys_code,
        )
        self._logger.info(
            "company_auth_lookup_succeeded",
            token_fingerprint=fingerprint,
            user_id=user.id,
        )
        return user

    async def _fetch(
        self, token: str, syscode_header: str, fingerprint: str
    ) -> tuple[int, dict | None]:
        try:
            response = await self._client.get(
                self._url,
                params={"isLog": "1", "logType": "4"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "SysCode": syscode_header,
                },
            )
        except httpx.HTTPError as exc:
            self._logger.warning(
                "company_auth_lookup_unavailable",
                token_fingerprint=fingerprint,
                error_type=type(exc).__name__,
            )
            raise AuthenticationUnavailable(
                "company authentication unavailable"
            ) from exc

        if response.status_code >= 500:
            self._logger.warning(
                "company_auth_lookup_unavailable",
                token_fingerprint=fingerprint,
                status_code=response.status_code,
            )
            raise AuthenticationUnavailable("company authentication unavailable")

        try:
            body = response.json()
        except ValueError:
            if 400 <= response.status_code < 500:
                return response.status_code, None
            raise AuthenticationUnavailable("company authentication unavailable")
        if not isinstance(body, dict):
            raise AuthenticationUnavailable("company authentication unavailable")
        return response.status_code, body

    async def close(self) -> None:
        await self._client.aclose()


def _normalized_state(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_unregistered_app(body: dict | None) -> bool:
    """平台返回 state=131「未授权的应用访问」：SysCode 头不是已注册应用编码。"""
    if not isinstance(body, dict):
        return False
    if _normalized_state(body.get("state")) == 131:
        return True
    return "未授权的应用" in str(body.get("msg") or "")
