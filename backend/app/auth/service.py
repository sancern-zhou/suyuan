"""Resolve normalized users from company credentials or explicit local mock mode."""

from __future__ import annotations

from typing import Any

from config.settings import Settings

from .errors import AuthenticationRejected
from .identity_cache import IdentityCache
from .models import CurrentUser
from .session_tokens import verify_session_token


MOCK_ADMIN_ROLE_CODE = "SUYUAN_ADMIN"


def build_mock_user(settings: Settings, sys_code: str | None = None) -> CurrentUser:
    user_id = settings.auth_mock_user_id.strip() or "local-developer"
    username = settings.auth_mock_username.strip() or user_id
    display_name = settings.auth_mock_display_name.strip() or "本地开发用户"
    roles = [
        role.strip()
        for role in settings.auth_mock_role_codes.split(",")
        if role.strip()
    ]
    if MOCK_ADMIN_ROLE_CODE not in roles:
        roles.insert(0, MOCK_ADMIN_ROLE_CODE)
    return CurrentUser(
        id=user_id,
        username=username,
        display_name=display_name,
        role_codes=tuple(roles),
        is_admin=True,
        sys_code=sys_code or settings.auth_sys_code,
        auth_source="mock",
    )


class AuthenticationService:
    def __init__(
        self,
        *,
        settings: Settings,
        cache: IdentityCache,
        platform_client: Any,
        operation_client: Any = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._platform_client = platform_client
        self._operation_client = operation_client

    async def authenticate(self, token: str, sys_code: str) -> CurrentUser:
        if sys_code != self._settings.auth_sys_code:
            raise AuthenticationRejected("invalid SysCode")

        if self._settings.auth_mode == "mock":
            return build_mock_user(self._settings, sys_code)

        if self._settings.auth_mode == "operation":
            if self._operation_client is None:
                raise AuthenticationUnavailable(
                    "operation authentication is not configured"
                )
            cached = await self._cache.get(token)
            if cached is not None:
                return cached
            user = await self._operation_client.get_current_user(
                token, sys_code
            )
            await self._cache.set(token, user)
            return user

        cached = await self._cache.get(token)
        if cached is not None:
            return cached
        user = await self._platform_client.get_current_user(token, sys_code)
        await self._cache.set(token, user)
        return user

    def resolve_session_token(self, raw: str) -> CurrentUser | None:
        """Verify an agent-issued session token; None when unavailable/invalid.

        Tokens are only meaningful in operation mode and when a signing secret
        is configured; callers fall back to the ops cookie otherwise.
        """
        if self._settings.auth_mode != "operation" or not raw:
            return None
        secret = self._settings.auth_session_token_secret.strip()
        if not secret or self._settings.auth_session_token_ttl_seconds <= 0:
            return None
        try:
            return verify_session_token(
                raw, secret=secret, sys_code=self._settings.auth_sys_code
            )
        except ValueError:
            return None

    async def close(self) -> None:
        await self._platform_client.close()
        if self._operation_client is not None:
            await self._operation_client.close()
