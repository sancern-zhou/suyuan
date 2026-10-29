"""Resolve identities from the local ops-platform Forms-authentication cookie."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx
import structlog

from .errors import AuthenticationRejected, AuthenticationUnavailable
from .models import CurrentUser


_OPERATION_ROLE_CODE = "SUYUAN_USER"


class OperationAuthClient:
    """Validate the ops-platform cookie through its identity oracle.

    The Forms ticket itself is never decrypted here: the ops platform stays the
    single authority that decides whether the cookie is genuine and which
    username it belongs to.
    """

    def __init__(
        self,
        *,
        validate_url: str,
        cookie_name: str,
        admin_usernames: set[str],
        timeout_seconds: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
        logger: Any | None = None,
    ) -> None:
        self._validate_url = validate_url.rstrip("/")
        self._cookie_name = cookie_name
        self._admin_usernames = set(admin_usernames)
        self._client = httpx.AsyncClient(timeout=timeout_seconds, transport=transport)
        self._logger = logger or structlog.get_logger(__name__)

    async def get_current_user(self, cookie_value: str, sys_code: str) -> CurrentUser:
        fingerprint = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()[:12]
        try:
            response = await self._client.get(
                self._validate_url,
                headers={"Cookie": f"{self._cookie_name}={cookie_value}"},
            )
        except httpx.HTTPError as exc:
            self._logger.warning(
                "operation_auth_lookup_unavailable",
                cookie_fingerprint=fingerprint,
                error_type=type(exc).__name__,
            )
            raise AuthenticationUnavailable(
                "operation authentication unavailable"
            ) from exc

        if response.status_code >= 500:
            self._logger.warning(
                "operation_auth_lookup_unavailable",
                cookie_fingerprint=fingerprint,
                status_code=response.status_code,
            )
            raise AuthenticationUnavailable("operation authentication unavailable")
        if response.status_code in {401, 403}:
            raise AuthenticationRejected("operation authentication rejected")
        if response.status_code in {301, 302, 303, 307, 308}:
            # Forms authentication bounces anonymous/invalid cookies to the
            # login page instead of answering 401.
            raise AuthenticationRejected("operation authentication rejected")

        try:
            body = response.json()
        except ValueError as exc:
            raise AuthenticationUnavailable(
                "operation authentication unavailable"
            ) from exc
        if not isinstance(body, dict) or body.get("authenticated") is not True:
            raise AuthenticationRejected("operation authentication rejected")

        username = str(body.get("userName") or "").strip()
        if not username:
            raise AuthenticationRejected("operation authentication rejected: missing user")
        if len(username) > 128 or any(character in username for character in "\r\n\"\\"):
            raise AuthenticationRejected("operation authentication rejected: invalid user")

        display_name = str(body.get("displayName") or "").strip() or username
        role_codes: tuple[str, ...] = (_OPERATION_ROLE_CODE,)
        is_admin = username in self._admin_usernames
        if is_admin:
            role_codes = ("SUYUAN_ADMIN", _OPERATION_ROLE_CODE)
        user = CurrentUser(
            id=f"ops-{username}",
            username=username,
            display_name=display_name,
            role_codes=role_codes,
            is_admin=is_admin,
            sys_code=sys_code,
            auth_source="operation",
        )
        self._logger.info(
            "operation_auth_lookup_succeeded",
            cookie_fingerprint=fingerprint,
            user_id=user.id,
        )
        return user

    async def close(self) -> None:
        await self._client.aclose()
