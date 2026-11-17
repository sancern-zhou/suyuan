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
        platform_sys_codes: list[str] | tuple[str, ...] | None = None,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: Any | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/{current_user_path.lstrip('/')}"
        self._admin_role_codes = set(admin_role_codes)
        candidates = [str(value).strip() for value in (platform_sys_codes or []) if str(value).strip()]
        if not candidates and platform_sys_code.strip():
            candidates = [platform_sys_code.strip()]
        self._platform_sys_codes = tuple(dict.fromkeys(candidates))
        self._platform_sys_code = self._platform_sys_codes[0] if self._platform_sys_codes else platform_sys_code
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)
        self._logger = logger or structlog.get_logger(__name__)

    async def get_current_user(self, token: str, sys_code: str) -> CurrentUser:
        """Resolve an identity, trying each configured platform SysCode in order.

        公司认证服务对 SysCode 敏感：同一 token 在 JCXT 下有效、在 NOISE 下可能 401。
        复用外部平台登录态时按配置顺序探测，只有全部候选被拒绝才判定为拒绝；
        任一候选不可用则继续下一个，全部不可用时抛 503。
        """
        last_rejected: AuthenticationRejected | None = None
        unavailable: AuthenticationUnavailable | None = None
        for platform_sys_code in self._platform_sys_codes or ("",):
            try:
                return await self._get_current_user(
                    token, sys_code, platform_sys_code=platform_sys_code
                )
            except AuthenticationRejected as exc:
                last_rejected = exc
            except AuthenticationUnavailable as exc:
                unavailable = exc
        if last_rejected is not None:
            raise last_rejected
        raise unavailable or AuthenticationRejected("company authentication rejected")

    async def _get_current_user(
        self,
        token: str,
        sys_code: str,
        *,
        platform_sys_code: str,
    ) -> CurrentUser:
        fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        self._logger.info(
            "company_auth_lookup_started",
            token_fingerprint=fingerprint,
            sys_code=platform_sys_code,
        )
        try:
            response = await self._client.get(
                self._url,
                params={"isLog": "1", "logType": "4"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "SysCode": platform_sys_code,
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
        if response.status_code in {401, 403} or 400 <= response.status_code < 500:
            raise AuthenticationRejected("company authentication rejected")

        try:
            body = response.json()
        except ValueError as exc:
            raise AuthenticationUnavailable("company authentication unavailable") from exc
        if not isinstance(body, dict):
            raise AuthenticationUnavailable("company authentication unavailable")

        state = _normalized_state(body.get("state"))
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

    async def close(self) -> None:
        await self._client.aclose()


def _normalized_state(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
