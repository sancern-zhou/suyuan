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
        try:
            response = await self._client.get(
                self._url,
                params={"isLog": "1", "logType": "4"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "SysCode": self._platform_sys_code,
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
